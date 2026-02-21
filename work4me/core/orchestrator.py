"""Main orchestrator — the executive brain of Work4Me.

Coordinates dual-mode execution, VS Code integration, browser automation,
Claude Code invocations, and behavior simulation to produce visible,
human-paced work.

Dual-Mode Architecture
----------------------
Mode A (Manual Developer):
  Claude Code runs headless per-activity, Work4Me replays actions visibly
  in VS Code at human speed. The work is real; the pacing is simulated.

Mode B (AI-Assisted Developer):
  Work4Me types prompts into a visible Claude Code terminal session,
  reviews output in VS Code. Imitates how developers use AI tools.

Both modes use interleaved execution — Claude Code runs per-activity
(not batch), enabling real debugging and adaptive behavior.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

from work4me.behavior.activity_monitor import ActivityMonitor, BehaviorAdjustment
from work4me.behavior.engine import BehaviorEngine
from work4me.config import Config
from work4me.controllers.browser import BrowserController
from work4me.controllers.claude_code import ActionKind, ClaudeCodeManager
from work4me.controllers.vscode import VSCodeController
from work4me.core.events import EventBus, StateChanged, TaskProgress
from work4me.core.state import State, StateMachine, StateSnapshot
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
        self._browser_ctrl = BrowserController(config.browser)
        self._claude = ClaudeCodeManager(config.claude)
        self._behavior = BehaviorEngine(config)

        # Planning
        self._planner = TaskPlanner(config.claude)
        self._scheduler = Scheduler(config.session)

        # Activity monitor
        self._activity_monitor = ActivityMonitor(config.activity)
        self._behavior.set_activity_monitor(self._activity_monitor)

        # Timing
        self._start_time: float = 0
        self._time_budget_seconds: float = 0

        # Watchdog
        self._watchdog_task: asyncio.Task | None = None

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

            # PLANNING
            self._transition("setup_complete")
            schedule = await self._plan(task_description, time_budget_minutes, working_dir)

            # WORKING — per-activity interleaved execution
            self._transition("plan_ready")
            for session in schedule.sessions:
                await self._execute_session(session, working_dir)

                # Break between sessions
                if session.break_after_minutes > 0:
                    self._transition("break_scheduled")
                    await self._take_break(session.break_after_minutes)
                    self._transition("break_over")

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
            await asyncio.sleep(3.0)  # Wait for VS Code to start

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
                logger.warning("Could not launch browser — continuing without it")

        logger.info("Desktop environment ready")

    # ------------------------------------------------------------------
    # Planning
    # ------------------------------------------------------------------

    async def _plan(
        self,
        task_description: str,
        time_budget_minutes: int,
        working_dir: str,
    ) -> Schedule:
        """Decompose task into activities and build schedule."""
        logger.info("Planning task decomposition...")

        plan = await self._planner.decompose(
            task_description=task_description,
            time_budget_hours=time_budget_minutes / 60.0,
            working_dir=working_dir,
        )

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

    # ------------------------------------------------------------------
    # Session and activity execution
    # ------------------------------------------------------------------

    async def _execute_session(self, session: WorkSession, working_dir: str) -> None:
        """Execute all activities in a work session."""
        logger.info(
            "Starting session %d: %d activities, %.0f min",
            session.session_number, len(session.activities), session.duration_minutes,
        )

        for i, activity in enumerate(session.activities):
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

            await self._execute_activity(activity, working_dir)

            # Persist state after each activity
            self.snapshot.current_activity_index = i + 1
            self._persist_state()

            # Check activity health between activities
            await self._check_activity_health()

            # Natural pause between activities
            await self._behavior.pause_natural(2.0, 6.0)

    async def _execute_activity(self, activity: Activity, working_dir: str) -> None:
        """Dispatch activity based on kind and mode."""
        logger.info(
            "Executing [%s] %s: %s",
            self._mode, activity.kind.value, activity.description[:60],
        )

        if activity.kind == ActivityKind.CODING:
            if self._mode == "manual":
                await self._execute_coding_manual(activity, working_dir)
            else:
                await self._execute_coding_ai_assisted(activity, working_dir)
        elif activity.kind == ActivityKind.BROWSER:
            await self._execute_browser(activity)
        elif activity.kind == ActivityKind.TERMINAL:
            await self._execute_terminal(activity, working_dir)
        elif activity.kind == ActivityKind.READING:
            await self._execute_reading(activity)
        elif activity.kind == ActivityKind.THINKING:
            await self._behavior.idle_think(activity.estimated_minutes * 60)

        self._activity_monitor.record_event("keyboard")

    # ------------------------------------------------------------------
    # Mode A: Manual Developer
    # ------------------------------------------------------------------

    async def _execute_coding_manual(self, activity: Activity, working_dir: str) -> None:
        """Mode A: headless Claude Code → replay edits in VS Code."""
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

    async def _replay_action_in_vscode(self, action) -> None:
        """Replay a Claude Code action visibly in VS Code."""
        if action.kind == ActionKind.EDIT or action.kind == ActionKind.WRITE:
            file_path = action.file_path
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
    # Mode B: AI-Assisted Developer
    # ------------------------------------------------------------------

    async def _execute_coding_ai_assisted(self, activity: Activity, working_dir: str) -> None:
        """Mode B: type prompts into visible Claude Code terminal session."""
        prompt = self._build_activity_prompt(activity)

        # Type the prompt into the VS Code terminal (visible Claude Code session)
        await self._vscode.show_terminal()
        await asyncio.sleep(0.5)

        # Type "claude" command to invoke Claude Code visibly
        claude_cmd = f"claude -p \"{prompt[:200]}\""
        await self._vscode.run_terminal_command(claude_cmd)

        # Wait for Claude to work (estimated time for the activity)
        wait_seconds = min(activity.estimated_minutes * 60 * 0.5, 120)
        await self._behavior.idle_think(wait_seconds)

        # Review output in editor
        await self._vscode.focus_editor()
        await asyncio.sleep(1.0)

        # Open files that were involved
        for file_path in activity.files_involved[:3]:
            await self._vscode.open_file(file_path)
            await asyncio.sleep(2.0)

    # ------------------------------------------------------------------
    # Browser activity
    # ------------------------------------------------------------------

    async def _execute_browser(self, activity: Activity) -> None:
        """Browse URLs from activity search queries."""
        for query in activity.search_queries:
            await self._browser_ctrl.search(query)
            await asyncio.sleep(2.0)

            # Scroll and read
            await self._browser_ctrl.scroll_down(pixels=400)
            await asyncio.sleep(3.0)

            self._activity_monitor.record_event("mouse")

    # ------------------------------------------------------------------
    # Terminal activity
    # ------------------------------------------------------------------

    async def _execute_terminal(self, activity: Activity, working_dir: str) -> None:
        """Run commands in VS Code integrated terminal."""
        await self._vscode.show_terminal()
        await asyncio.sleep(0.5)

        for command in activity.commands:
            await self._vscode.run_terminal_command(command)
            wait_time = self._estimate_command_wait(command)
            await asyncio.sleep(wait_time)

            self._activity_monitor.record_event("keyboard")

    # ------------------------------------------------------------------
    # Reading activity
    # ------------------------------------------------------------------

    async def _execute_reading(self, activity: Activity) -> None:
        """Open and scroll through files in VS Code."""
        await self._vscode.focus_editor()

        for file_path in activity.files_involved[:5]:
            await self._vscode.open_file(file_path)
            await asyncio.sleep(2.0)
            await self._behavior.idle_think(10.0)

            self._activity_monitor.record_event("keyboard")

    # ------------------------------------------------------------------
    # Break and wrap-up
    # ------------------------------------------------------------------

    async def _take_break(self, duration_minutes: float) -> None:
        """Simulate break with minimal activity."""
        await self._behavior.take_break(duration_minutes * 60)

    async def _wrap_up(self, working_dir: str) -> None:
        """Git commit and final cleanup."""
        logger.info("Wrapping up session...")

        await self._vscode.show_terminal()
        await asyncio.sleep(0.5)

        await self._vscode.run_terminal_command("git status")
        await asyncio.sleep(2.0)

        await self._vscode.run_terminal_command("git add -u")
        await asyncio.sleep(1.0)

        await self._vscode.run_terminal_command("git add .")
        await asyncio.sleep(1.0)

        commit_msg = f"feat: {self.snapshot.task_description[:50]}"
        await self._vscode.run_terminal_command(f'git commit -m "{commit_msg}"')
        await asyncio.sleep(2.0)

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
        await self._vscode.cleanup()
        await self._browser_ctrl.cleanup()
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
