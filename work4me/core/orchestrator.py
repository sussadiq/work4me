"""Main orchestrator — the executive brain of Work4Me.

Coordinates dual-mode execution, VS Code integration, browser automation,
Claude Code invocations, and behavior simulation to produce visible,
human-paced work.

Dual-Mode Architecture
----------------------
Sidebar mode (primary):
  Opens the Claude Code VS Code extension sidebar, types prompts with
  human-like timing via dotool, monitors file changes for completion
  detection, and reviews/accepts diffs. Falls back to manual mode on
  error.

Manual mode (fallback):
  Claude Code runs headless per-activity, Work4Me replays actions visibly
  in VS Code at human speed. The work is real; the pacing is simulated.

Both modes use interleaved execution — Claude Code runs per-activity
(not batch), enabling real debugging and adaptive behavior.
"""

from __future__ import annotations

import asyncio
import logging
import random
import shlex
import time
from datetime import datetime, timezone
from pathlib import Path

from work4me.behavior.activity_monitor import ActivityMonitor, BehaviorAdjustment
from work4me.behavior.engine import BehaviorEngine
from work4me.config import Config
from work4me.controllers.browser import BrowserController
from work4me.controllers.claude_code import ActionKind, CapturedAction, ClaudeCodeManager
from work4me.controllers.vscode import VSCodeController
from work4me.core.events import EventBus, StateChanged, TaskProgress
from work4me.core.state import State, StateMachine, StateSnapshot
from work4me.desktop.input_sim import DotoolInput, detect_input_method
from work4me.desktop.window_mgr import detect_window_manager
from work4me.planning.scheduler import Schedule, Scheduler, WorkSession
from work4me.planning.task_planner import Activity, ActivityKind, TaskPlan, TaskPlanner

logger = logging.getLogger(__name__)


class Orchestrator:
    """The executive brain — decides what to do and when."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.state_machine = StateMachine()
        self.event_bus = EventBus()
        self.snapshot = StateSnapshot()

        # Mode
        self._mode: str = config.mode

        # Controllers
        self._vscode = VSCodeController(config.vscode)
        self._claude = ClaudeCodeManager(config.claude)
        self._browser_ctrl = BrowserController(config.browser, claude=self._claude)
        self._behavior = BehaviorEngine(config)

        # Planning
        self._planner = TaskPlanner(config.claude)
        self._scheduler = Scheduler(config.session)

        # Window management
        self._window_mgr = detect_window_manager()

        # Input simulation (dotool/ydotool for real keystrokes)
        self._input_sim: DotoolInput = detect_input_method()

        # Activity monitor
        self._activity_monitor = ActivityMonitor(config.activity)
        self._behavior.set_activity_monitor(self._activity_monitor)

        # Timing
        self._start_time: float = 0
        self._time_budget_seconds: float = 0

        # Watchdog
        self._watchdog_task: asyncio.Task[None] | None = None

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def run(
        self,
        task_description: str,
        time_budget_minutes: int,
        working_dir: str = ".",
    ) -> None:
        """Main entry point. Plans, schedules, executes per-activity."""
        self._start_time = time.monotonic()
        self._time_budget_seconds = time_budget_minutes * 60.0

        self.snapshot.task_description = task_description
        self.snapshot.time_budget_minutes = time_budget_minutes
        self.snapshot.started_at = datetime.now(timezone.utc).isoformat()
        self.snapshot.working_dir = working_dir

        logger.info(
            "Starting Work4Me [%s]: task='%s', budget=%d min",
            self._mode, task_description[:80], time_budget_minutes,
        )

        try:
            # INITIALIZING
            self._transition("start_task")
            await self._initialize(working_dir)
            await self._start_watchdog()

            # Check for crash recovery — only if same task
            recovered = self.check_for_recovery()
            if recovered and recovered.task_description == task_description:
                logger.info(
                    "Recovering previous session at activity %d: %s",
                    recovered.current_activity_index,
                    recovered.task_description[:60],
                )
                self.snapshot = recovered
            else:
                recovered = None
                # Clear stale state from a different task
                self._clear_stale_state()

            # PLANNING
            self._transition("setup_complete")
            schedule = await self._plan(task_description, time_budget_minutes, working_dir)

            # WORKING — per-activity interleaved execution
            self._transition("plan_ready")
            for si, session in enumerate(schedule.sessions):
                start_idx = self.snapshot.current_activity_index if (recovered and si == 0) else 0
                await self._execute_session(session, working_dir, activity_start_index=start_idx)

                # Micro-pause between sessions (no formal breaks)
                if si < len(schedule.sessions) - 1:
                    await self._behavior.micro_pause()

            # WRAPPING_UP
            if self.state_machine.can_transition("task_complete_early"):
                self._transition("task_complete_early")
            elif self.state_machine.can_transition("time_almost_up"):
                self._transition("time_almost_up")
            await self._wrap_up(working_dir)

            # COMPLETED
            self._transition("wrapped_up")
            logger.info("Session completed successfully")

        except KeyboardInterrupt:
            logger.info("Session interrupted by user")
            if self.state_machine.can_transition("user_pause"):
                self._transition("user_pause")
        except Exception as exc:
            logger.exception("Session failed: %s", exc)
            if self.state_machine.can_transition("error"):
                self._transition("error")
        finally:
            await self._stop_watchdog()
            await self._cleanup()
            self._persist_state()

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    async def _initialize(self, working_dir: str) -> None:
        """Launch VS Code and browser, connect controllers."""
        logger.info("Initializing desktop environment...")

        # Launch VS Code
        if self.config.vscode.launch_on_start:
            await self._vscode.launch(working_dir)
            await asyncio.sleep(5.0)  # Wait for VS Code + onStartupFinished

        # Connect to VS Code WebSocket bridge
        try:
            await self._vscode.connect()
        except ConnectionError:
            logger.warning("Could not connect to VS Code bridge — continuing without it")

        # Launch browser if enabled
        if self.config.browser.enabled:
            try:
                await self._browser_ctrl.launch()
            except Exception:
                logger.warning("Could not launch browser — continuing without it", exc_info=True)

        # Auto-install GNOME focus extension if needed
        await self._ensure_gnome_extension()

        logger.info("Desktop environment ready")

    async def _ensure_gnome_extension(self) -> None:
        """Install the bundled GNOME Shell focus extension if on GNOME."""
        import os
        desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").upper()
        if "GNOME" not in desktop:
            return

        from work4me.doctor import DoctorChecks
        dc = DoctorChecks()
        check = dc.check_gnome_extension()
        if check.passed:
            return

        logger.info("Installing work4me-focus GNOME extension...")
        result = DoctorChecks.install_gnome_extension()
        if result.passed and "needs_restart" in result.detail:
            logger.warning(
                "GNOME extension installed but requires session restart "
                "(log out and back in) — window switching disabled this session"
            )
        elif result.passed:
            logger.info("GNOME extension installed: %s", result.detail)
        else:
            logger.warning("GNOME extension install failed: %s", result.detail)

    # ------------------------------------------------------------------
    # Planning
    # ------------------------------------------------------------------

    async def _plan(
        self,
        task_description: str,
        time_budget_minutes: int,
        working_dir: str,
    ) -> Schedule:
        """Decompose task into activities and build schedule.

        Falls back to a minimal single-activity plan if the planner
        fails after all retries, so one transient failure never kills
        the entire session.
        """
        logger.info("Planning task decomposition...")

        try:
            plan = await self._planner.decompose(
                task_description=task_description,
                time_budget_hours=time_budget_minutes / 60.0,
                working_dir=working_dir,
            )
        except Exception as exc:
            logger.error("Planning failed, using fallback plan: %s", exc)
            return self._fallback_plan(task_description, time_budget_minutes)

        logger.info(
            "Task decomposed into %d activities (%.0f min estimated)",
            len(plan.activities), plan.total_estimated_minutes,
        )

        schedule = self._scheduler.build_schedule(plan, total_minutes=time_budget_minutes)

        logger.info(
            "Scheduled %d sessions with breaks",
            len(schedule.sessions),
        )

        return schedule

    def _fallback_plan(
        self,
        task_description: str,
        time_budget_minutes: int,
    ) -> Schedule:
        """Create a minimal fallback schedule with a single CODING activity."""
        coding_minutes = int(time_budget_minutes * 0.70)
        activity = Activity(
            kind=ActivityKind.CODING,
            description=task_description,
            estimated_minutes=coding_minutes,
            files_involved=[],
            commands=[],
            search_queries=[],
            dependencies=[],
        )
        plan = TaskPlan(task_description=task_description, activities=[activity])
        schedule = self._scheduler.build_schedule(plan, total_minutes=time_budget_minutes)
        logger.info(
            "Fallback plan: 1 CODING activity, %d min", coding_minutes,
        )
        return schedule

    # ------------------------------------------------------------------
    # Session and activity execution
    # ------------------------------------------------------------------

    async def _execute_session(
        self, session: WorkSession, working_dir: str, activity_start_index: int = 0,
    ) -> None:
        """Execute all activities in a work session."""
        logger.info(
            "Starting session %d: %d activities, %.0f min (start_idx=%d)",
            session.session_number, len(session.activities), session.duration_minutes,
            activity_start_index,
        )

        for i, activity in enumerate(session.activities):
            if i < activity_start_index:
                logger.info("Skipping already-completed activity %d", i)
                continue
            # Check time budget
            elapsed = time.monotonic() - self._start_time
            remaining = self._time_budget_seconds - elapsed
            if remaining < 60:
                logger.info("Time budget nearly exhausted, stopping")
                break

            await self.event_bus.emit(
                TaskProgress(
                    activity_index=i,
                    total_activities=len(session.activities),
                    description=f"{activity.kind.value}: {activity.description[:60]}",
                )
            )

            try:
                await self._execute_activity_with_retry(activity, working_dir)
            except Exception as exc:
                logger.error(
                    "Activity %d failed after retries, skipping: %s",
                    i, exc,
                )
                self.snapshot.skipped_activities.append(i)

            # Persist state after each activity
            self.snapshot.current_activity_index = i + 1
            self._persist_state()

            # Check activity health between activities
            await self._check_activity_health()

            # Natural pause between activities
            await self._behavior.pause_natural(2.0, 6.0)

    async def _execute_activity_with_retry(
        self, activity: Activity, working_dir: str, max_retries: int = 3
    ) -> None:
        """Execute an activity with exponential backoff retry."""
        if max_retries <= 0:
            raise RuntimeError("max_retries must be >= 1")
        last_exc: Exception | None = None
        for attempt in range(max_retries):
            try:
                await self._execute_activity(activity, working_dir)
                return
            except asyncio.CancelledError:
                raise  # Never retry cancellation
            except Exception as exc:
                last_exc = exc
                if attempt < max_retries - 1:
                    wait = 2 ** attempt * 2  # 2s, 4s, 8s
                    logger.warning(
                        "Activity failed (attempt %d/%d), retrying in %ds: %s",
                        attempt + 1, max_retries, wait, exc,
                    )
                    await asyncio.sleep(wait)
        assert last_exc is not None
        raise last_exc

    async def _execute_activity(self, activity: Activity, working_dir: str) -> None:
        """Dispatch activity based on kind and mode."""
        logger.info(
            "Executing [%s] %s: %s",
            self._mode, activity.kind.value, activity.description[:60],
        )

        if activity.kind == ActivityKind.CODING:
            if self._mode == "sidebar":
                await self._execute_coding_sidebar(activity, working_dir)
            else:  # "manual" fallback
                await self._execute_coding_manual(activity, working_dir)
        elif activity.kind == ActivityKind.BROWSER:
            await self._execute_browser(activity)
        elif activity.kind == ActivityKind.TERMINAL:
            await self._execute_terminal(activity, working_dir)
        elif activity.kind == ActivityKind.READING:
            await self._execute_reading(activity)
        elif activity.kind == ActivityKind.THINKING:
            await self._execute_thinking(activity)

        self._activity_monitor.record_event("keyboard")

    # ------------------------------------------------------------------
    # Window focus
    # ------------------------------------------------------------------

    def _vscode_title_hint(self) -> str:
        """Return the project directory name for VS Code window matching."""
        return Path(self.snapshot.working_dir).resolve().name

    async def _focus_app_window(
        self, window_class: str, *, title_hint: str = "",
    ) -> None:
        """Raise the OS window for the given WM_CLASS."""
        focused = await self._window_mgr.focus_window(
            window_class, title_hint=title_hint,
        )
        if focused:
            await self._behavior.pause_natural(0.3, 0.8)

    # ------------------------------------------------------------------
    # Mode A: Manual Developer
    # ------------------------------------------------------------------

    async def _execute_coding_manual(self, activity: Activity, working_dir: str) -> None:
        """Mode A: headless Claude Code → replay edits in VS Code."""
        await self._focus_app_window(
            self.config.vscode.window_class, title_hint=self._vscode_title_hint(),
        )
        prompt = self._build_activity_prompt(activity)

        result = await self._claude.execute(
            prompt=prompt,
            working_dir=working_dir,
            max_turns=self.config.claude.max_turns,
        )

        if result.error:
            logger.error("Claude Code failed for activity: %s", result.error[:200])
            return

        # Replay actions visibly in VS Code
        for action in result.actions:
            await self._replay_action_in_vscode(action)
            await self._behavior.pause_natural(1.0, 4.0)

    def _resolve_activity_path(self, file_path: str) -> str | None:
        """Resolve a relative file path against working_dir, blocking traversal."""
        working = Path(self.snapshot.working_dir).resolve()
        # Handle already-absolute paths
        if Path(file_path).is_absolute():
            resolved = Path(file_path).resolve()
        else:
            resolved = (working / file_path).resolve()
        if not str(resolved).startswith(str(working)):
            logger.warning("Path traversal blocked: %s", file_path)
            return None
        return str(resolved)

    async def _replay_action_in_vscode(self, action: CapturedAction) -> None:
        """Replay a Claude Code action visibly in VS Code."""
        if action.kind == ActionKind.EDIT or action.kind == ActionKind.WRITE:
            file_path = self._resolve_activity_path(action.file_path) if action.file_path else None
            if file_path:
                await self._vscode.open_file(file_path)
                await asyncio.sleep(1.0)

                # For new files (WRITE), create first
                if action.kind == ActionKind.WRITE:
                    await self._vscode.new_file(file_path)
                    await asyncio.sleep(0.5)

                # Type visible content (limited to avoid extreme delays)
                content = action.new_string or action.content
                if content:
                    visible_text = content[:1500]
                    await self._vscode.type_text(visible_text)
                    await asyncio.sleep(0.5)

                await self._vscode.save_file()

        elif action.kind == ActionKind.BASH:
            if action.command:
                await self._vscode.run_terminal_command(action.command)
                await asyncio.sleep(2.0)

    # ------------------------------------------------------------------
    # Sidebar mode: Claude Code VS Code extension
    # ------------------------------------------------------------------

    async def _execute_coding_sidebar(self, activity: Activity, working_dir: str) -> None:
        """Sidebar mode: drive the Claude Code VS Code extension sidebar.

        Opens the sidebar, types the prompt with human-like timing,
        monitors file changes for completion, and reviews/accepts diffs.
        Falls back to manual mode on any error.
        """
        try:
            await self._execute_coding_sidebar_inner(activity, working_dir)
        except Exception as exc:
            logger.warning(
                "Sidebar mode failed, falling back to manual: %s", exc,
            )
            await self._execute_coding_manual(activity, working_dir)

    async def _execute_coding_sidebar_inner(
        self, activity: Activity, working_dir: str,
    ) -> None:
        """Inner sidebar execution (raises on failure for fallback)."""
        await self._focus_app_window(
            self.config.vscode.window_class, title_hint=self._vscode_title_hint(),
        )
        prompt = self._build_activity_prompt(activity)

        # 1. Open Claude Code sidebar and start a new conversation
        await self._vscode.open_claude_sidebar()
        await asyncio.sleep(1.0)
        await self._vscode.new_claude_conversation()
        await asyncio.sleep(0.5)

        # 2. Focus input and type prompt with human-like timing
        await self._vscode.focus_claude_input()
        await asyncio.sleep(0.3)
        await self._type_prompt_human_like(prompt)

        # 3. Start file change monitoring
        await self._vscode.start_claude_watch()

        # 4. Press Enter to submit the prompt
        if await self._input_sim.health_check():
            await self._input_sim.type_key("Return")
        else:
            # Fallback: use bridge to type a newline
            await self._vscode.type_text("\n")

        # 5. Wait for Claude to finish (poll file change quiescence)
        await self._wait_for_claude_completion(activity)

        # 6. Stop monitoring and log results
        watch_result = await self._vscode.stop_claude_watch()
        total_changes = watch_result.get("totalChanges", 0)
        logger.info("Claude sidebar completed: %d file changes", total_changes)

        # 7. Review and accept diffs
        await self._review_and_accept_diffs()

        # 8. Open changed files for visual review
        for file_path in activity.files_involved[:3]:
            resolved = self._resolve_activity_path(file_path)
            if resolved is None or not Path(resolved).exists():
                continue
            try:
                await self._vscode.open_file(resolved)
                await asyncio.sleep(2.0)
            except Exception as exc:
                logger.warning("Failed to open file %s: %s", resolved, exc)

    async def _type_prompt_human_like(self, prompt: str) -> None:
        """Type prompt using dotool for real keystrokes, or bridge as fallback."""
        if await self._input_sim.health_check():
            await self._behavior.type_text(
                prompt,
                send_char_fn=self._input_sim.type_char,
                is_code=False,
            )
        else:
            await self._vscode.type_text(prompt)

    async def _wait_for_claude_completion(self, activity: Activity) -> None:
        """Poll file change status until Claude appears idle."""
        max_wait = min(activity.estimated_minutes * 60 * 0.8, 300)
        idle_threshold_ms = 5000
        poll_interval = 3.0
        elapsed = 0.0

        logger.info(
            "Waiting for Claude completion (max %.0fs, idle threshold %dms)",
            max_wait, idle_threshold_ms,
        )

        while elapsed < max_wait:
            await self._behavior.idle_think(poll_interval)
            elapsed += poll_interval

            try:
                busy = await self._vscode.is_claude_busy(
                    idle_threshold_ms=idle_threshold_ms,
                )
                if not busy:
                    logger.info("Claude appears idle after %.0fs", elapsed)
                    return
            except Exception:
                pass  # Connection hiccup, keep waiting

        logger.info("Claude wait timed out after %.0fs", max_wait)

    async def _review_and_accept_diffs(self) -> None:
        """Simulate human diff review: pause, then accept (95%) or reject (5%)."""
        review_pause = random.uniform(2.0, 8.0)
        await self._behavior.idle_think(review_pause)

        try:
            if random.random() < 0.95:
                await self._vscode.accept_diff()
                logger.info("Accepted diff after %.1fs review", review_pause)
            else:
                await self._vscode.reject_diff()
                logger.info("Rejected diff after %.1fs review (realism)", review_pause)
        except Exception as exc:
            # No pending diff is fine — Claude may not have proposed one
            logger.debug("Diff action failed (likely no pending diff): %s", exc)

    # ------------------------------------------------------------------
    # Browser activity
    # ------------------------------------------------------------------

    async def _execute_browser(self, activity: Activity) -> None:
        """Browse URLs from activity search queries with clicking and interaction."""
        if not await self._browser_ctrl.health_check():
            logger.warning("Browser not available, skipping browser activity: %s", activity.description[:60])
            # Fall back to a thinking pause instead
            await self._behavior.idle_think(activity.estimated_minutes * 60 * 0.5)
            return

        await self._focus_app_window(self.config.browser.window_class)

        for query in activity.search_queries:
            try:
                await self._browser_ctrl.search(query)
                await asyncio.sleep(2.0)
                await self._browser_ctrl.dismiss_cookie_banner()
                await self._browser_ctrl.handle_captcha()

                # Click on a search result heading
                try:
                    await self._browser_ctrl.click("h3", timeout=3000)
                    await asyncio.sleep(2.0)
                    await self._browser_ctrl.dismiss_cookie_banner()
                except Exception:
                    pass  # No matching link — fall through to scroll

                # Scroll and read content
                for _ in range(random.randint(2, 3)):
                    await self._browser_ctrl.scroll_down(pixels=random.randint(200, 500))
                    await asyncio.sleep(random.uniform(2.0, 5.0))

                self._activity_monitor.record_event("mouse")
            except Exception as exc:
                logger.warning("Browser action failed, skipping: %s", exc)

    # ------------------------------------------------------------------
    # Terminal activity
    # ------------------------------------------------------------------

    async def _execute_terminal(self, activity: Activity, working_dir: str) -> None:
        """Run commands in VS Code integrated terminal."""
        await self._focus_app_window(
            self.config.vscode.window_class, title_hint=self._vscode_title_hint(),
        )
        try:
            await self._vscode.show_terminal()
        except Exception as exc:
            logger.warning("Cannot show terminal: %s", exc)
            return
        await asyncio.sleep(0.5)

        for command in activity.commands:
            try:
                await self._vscode.run_terminal_command(command)
                wait_time = self._estimate_command_wait(command)
                await asyncio.sleep(wait_time)
                self._activity_monitor.record_event("keyboard")
            except Exception as exc:
                logger.warning("Terminal command failed (%s): %s", command[:40], exc)

    # ------------------------------------------------------------------
    # Reading activity
    # ------------------------------------------------------------------

    async def _execute_reading(self, activity: Activity) -> None:
        """Open and scroll through files in VS Code."""
        await self._focus_app_window(
            self.config.vscode.window_class, title_hint=self._vscode_title_hint(),
        )
        await self._vscode.focus_editor()

        for file_path in activity.files_involved[:5]:
            resolved = self._resolve_activity_path(file_path)
            if resolved is None:
                logger.warning("Skipping unresolvable path: %s", file_path)
                continue
            if not Path(resolved).exists():
                logger.warning("Skipping non-existent file: %s", resolved)
                continue
            try:
                await self._vscode.open_file(resolved)
                await asyncio.sleep(2.0)
                await self._behavior.idle_think(10.0)
                self._activity_monitor.record_event("keyboard")
            except Exception as exc:
                logger.warning("Failed to open file %s: %s", resolved, exc)

    # ------------------------------------------------------------------
    # Thinking activity (browser research)
    # ------------------------------------------------------------------

    async def _execute_thinking(self, activity: Activity) -> None:
        """Think by researching in the browser — docs, Stack Overflow, etc."""
        total_seconds = activity.estimated_minutes * 60

        # Try browser research first
        if await self._browser_ctrl.health_check():
            queries = activity.search_queries or self._generate_research_queries(activity)
            if queries:
                await self._research_with_browser(queries, total_seconds)
                return

        # Fallback: pure thinking with micro-movements
        logger.info("No browser available — thinking for %.0f seconds", total_seconds)
        await self._behavior.idle_think(total_seconds)

    async def _research_with_browser(self, queries: list[str], total_seconds: float) -> None:
        """Browse research queries with clicking, cookie dismissal, and reading."""
        await self._focus_app_window(self.config.browser.window_class)
        time_per_query = total_seconds / max(len(queries), 1)

        for query in queries:
            logger.info("Researching: %s", query)
            try:
                await self._browser_ctrl.search(query)
                await asyncio.sleep(2.0)
                await self._browser_ctrl.dismiss_cookie_banner()
                await self._browser_ctrl.handle_captcha()

                # Click first 2-3 organic result links
                result_links = ["h3", "a h3", "[data-header-feature] a"]
                clicked = 0
                for link_sel in result_links:
                    if clicked >= 2:
                        break
                    try:
                        await self._browser_ctrl.click(link_sel, timeout=2000)
                        clicked += 1
                        await asyncio.sleep(2.0)
                        await self._browser_ctrl.dismiss_cookie_banner()

                        # Read the page
                        for _ in range(random.randint(2, 4)):
                            await self._browser_ctrl.scroll_down(
                                pixels=random.randint(200, 500)
                            )
                            await asyncio.sleep(random.uniform(3.0, 8.0))
                            self._activity_monitor.record_event("mouse")

                        await self._browser_ctrl.go_back()
                        await asyncio.sleep(1.0)
                    except Exception:
                        continue

                # Think pause between queries
                think_pause = random.uniform(5.0, 15.0)
                await asyncio.sleep(think_pause)
                self._activity_monitor.record_event("keyboard")

            except Exception as exc:
                logger.warning("Research query failed (%s): %s", query[:40], exc)
                await self._behavior.idle_think(min(time_per_query, 30.0))

    def _generate_research_queries(self, activity: Activity) -> list[str]:
        """Generate search queries from activity description."""
        desc = activity.description.lower()
        queries: list[str] = []
        # Use the description directly as a search query (trimmed)
        if len(desc) > 10:
            queries.append(activity.description[:80])
        # Add a "best practices" query if it's about code
        if any(w in desc for w in ("code", "implement", "fix", "refactor", "review")):
            queries.append(f"{activity.description[:50]} best practices")
        return queries[:3]

    # ------------------------------------------------------------------
    # Break and wrap-up
    # ------------------------------------------------------------------

    async def _wrap_up(self, working_dir: str) -> None:
        """Git commit and final cleanup."""
        logger.info("Wrapping up session...")

        try:
            await self._vscode.show_terminal()
            await asyncio.sleep(0.5)

            await self._vscode.run_terminal_command("git status")
            await asyncio.sleep(2.0)

            await self._vscode.run_terminal_command("git add -u")
            await asyncio.sleep(1.0)

            await self._vscode.run_terminal_command("git add .")
            await asyncio.sleep(1.0)

            commit_msg = f"feat: {self.snapshot.task_description[:50]}"
            await self._vscode.run_terminal_command(f"git commit -m {shlex.quote(commit_msg)}")
            await asyncio.sleep(2.0)
        except Exception as exc:
            logger.warning("Wrap-up git commands failed: %s", exc)

        logger.info("Wrap-up complete")

    # ------------------------------------------------------------------
    # Activity health monitoring
    # ------------------------------------------------------------------

    async def _check_activity_health(self) -> None:
        """Consult ActivityMonitor and adjust behavior if needed."""
        adjustment = self._activity_monitor.recommended_adjustment()
        self._behavior.apply_adjustment(adjustment)

        if adjustment == BehaviorAdjustment.SLOW_DOWN:
            logger.debug("Activity too high — inserting idle pause")
            await self._behavior.idle_think(15.0)
        elif adjustment == BehaviorAdjustment.ADD_MOUSE:
            self._activity_monitor.record_event("mouse")
        elif adjustment == BehaviorAdjustment.ADD_IDLE:
            logger.debug("Adding idle period for variation")
            await self._behavior.idle_think(10.0)
        elif adjustment == BehaviorAdjustment.ADD_VARIATION:
            logger.debug("Adding timing variation")
            await self._behavior.pause_natural(1.0, 5.0)

    # ------------------------------------------------------------------
    # Controller watchdog
    # ------------------------------------------------------------------

    async def _start_watchdog(self) -> None:
        self._watchdog_task = asyncio.create_task(self._watchdog_loop())

    async def _stop_watchdog(self) -> None:
        if self._watchdog_task and not self._watchdog_task.done():
            self._watchdog_task.cancel()
            try:
                await self._watchdog_task
            except asyncio.CancelledError:
                pass
        self._watchdog_task = None

    async def _watchdog_loop(self) -> None:
        while True:
            await asyncio.sleep(60)
            try:
                await self._watchdog_tick()
            except Exception:
                logger.warning("Watchdog tick failed", exc_info=True)

    async def _watchdog_tick(self) -> None:
        """Check controller health and restart if needed."""
        try:
            vs_ok = await self._vscode.health_check()
        except Exception:
            vs_ok = False
        if not vs_ok:
            logger.warning("VS Code unhealthy, restarting...")
            try:
                await self._vscode.restart()
            except Exception:
                logger.error("VS Code restart failed", exc_info=True)

        if self._browser_ctrl._browser_available:
            try:
                br_ok = await self._browser_ctrl.health_check()
            except Exception:
                br_ok = False
            if not br_ok:
                logger.warning("Browser unhealthy, restarting...")
                try:
                    await self._browser_ctrl.restart()
                except Exception:
                    logger.error("Browser restart failed", exc_info=True)

    # ------------------------------------------------------------------
    # Cleanup and state management
    # ------------------------------------------------------------------

    async def _cleanup(self) -> None:
        """Close all connections."""
        controllers: list[tuple[str, VSCodeController | BrowserController]] = [
            ("vscode", self._vscode), ("browser", self._browser_ctrl),
        ]
        for name, ctrl in controllers:
            try:
                await ctrl.cleanup()
            except Exception:
                logger.warning("Cleanup failed for %s", name, exc_info=True)
        logger.info("Cleanup done")

    def _transition(self, trigger: str) -> None:
        """Execute a state transition and emit event."""
        old = self.state_machine.state
        new = self.state_machine.transition(trigger)
        self.snapshot.state = new.value
        try:
            asyncio.create_task(
                self.event_bus.emit(StateChanged(old.value, new.value, trigger))
            )
        except RuntimeError:
            pass

    def _persist_state(self) -> None:
        """Save current state to disk."""
        elapsed = time.monotonic() - self._start_time if self._start_time else 0
        self.snapshot.elapsed_minutes = elapsed / 60.0
        state_path = self.config.runtime_dir / "state.json"
        try:
            self.snapshot.save(state_path)
        except Exception:
            logger.warning("Failed to persist state", exc_info=True)

    # ------------------------------------------------------------------
    # Crash recovery
    # ------------------------------------------------------------------

    def check_for_recovery(self) -> StateSnapshot | None:
        """Check if there's a recoverable session state on disk."""
        state_path = self.config.runtime_dir / "state.json"
        if not state_path.exists():
            return None
        try:
            snap = StateSnapshot.load(state_path)
            if snap.is_resumable():
                return snap
        except Exception:
            logger.warning("Failed to load recovery state", exc_info=True)
        return None

    def _clear_stale_state(self) -> None:
        """Remove stale state file from a previous session."""
        state_path = self.config.runtime_dir / "state.json"
        if state_path.exists():
            try:
                state_path.unlink()
                logger.debug("Cleared stale state file")
            except Exception:
                logger.warning("Failed to clear stale state", exc_info=True)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_activity_prompt(self, activity: Activity) -> str:
        """Build prompt for a single activity."""
        parts = [f"Complete this specific task:\n\n{activity.description}\n"]

        if activity.files_involved:
            parts.append(f"Files: {', '.join(activity.files_involved)}")

        if activity.commands:
            parts.append(f"Commands to run: {', '.join(activity.commands)}")

        parts.append(
            "Work in the current directory. Use Edit/Write tools for file changes "
            "and Bash tool for terminal commands. Follow existing project conventions."
        )

        return "\n\n".join(parts)

    def _estimate_command_wait(self, command: str) -> float:
        """Estimate how long to wait for a command to finish."""
        cmd_lower = command.lower().strip()
        if any(kw in cmd_lower for kw in ["npm test", "pytest", "cargo test", "make test"]):
            return 8.0
        if any(kw in cmd_lower for kw in ["npm install", "pip install", "cargo build", "make"]):
            return 10.0
        if any(kw in cmd_lower for kw in ["npm run build", "tsc", "webpack"]):
            return 8.0
        if cmd_lower.startswith("git "):
            return 2.0
        if cmd_lower.startswith(("ls", "cat", "echo", "pwd")):
            return 1.0
        return 3.0
