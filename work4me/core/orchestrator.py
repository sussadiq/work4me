"""Main orchestrator — the executive brain of Work4Me.

Coordinates the state machine, Claude Code integration, terminal/editor
controllers, and behavior engine to produce visible, human-paced work.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

from work4me.behavior.engine import BehaviorEngine
from work4me.config import Config
from work4me.controllers.claude_code import ActionKind, ClaudeCodeManager, SessionResult
from work4me.controllers.editor import EditorController
from work4me.controllers.terminal import TerminalController
from work4me.core.events import EventBus, StateChanged, TaskProgress
from work4me.core.state import State, StateMachine, StateSnapshot
from work4me.desktop.input_sim import TmuxInput

logger = logging.getLogger(__name__)


class Orchestrator:
    """The executive brain — decides what to do and when."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.state_machine = StateMachine()
        self.event_bus = EventBus()
        self.behavior = BehaviorEngine(config)
        self.claude = ClaudeCodeManager(config.claude)
        self.terminal = TerminalController()
        self.editor = EditorController()
        self.snapshot = StateSnapshot()

        self._start_time: float = 0
        self._time_budget_seconds: float = 0

    async def run(self, task_description: str, time_budget_minutes: int) -> None:
        """Main entry point. Plans, schedules, executes.

        This is the top-level async loop that drives the entire session.
        """
        self._start_time = time.monotonic()
        self._time_budget_seconds = time_budget_minutes * 60.0

        # Save initial state
        self.snapshot.task_description = task_description
        self.snapshot.time_budget_minutes = time_budget_minutes
        self.snapshot.started_at = datetime.now(timezone.utc).isoformat()
        self.snapshot.working_dir = self.config.working_dir

        logger.info(
            "Starting Work4Me: task='%s', budget=%d min",
            task_description[:80],
            time_budget_minutes,
        )

        try:
            # INITIALIZING — set up desktop environment
            self._transition("start_task")
            await self._initialize()

            # PLANNING — decompose task via Claude Code
            self._transition("setup_complete")
            actions = await self._plan_and_execute(task_description)

            # WORKING — replay actions visibly
            self._transition("plan_ready")
            await self._work(actions)

            # WRAPPING_UP
            if self.state_machine.can_transition("task_complete_early"):
                self._transition("task_complete_early")
            elif self.state_machine.can_transition("time_almost_up"):
                self._transition("time_almost_up")
            await self._wrap_up()

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
            await self._cleanup()
            self._persist_state()

    async def _initialize(self) -> None:
        """Set up tmux session and Neovim."""
        logger.info("Initializing desktop environment...")

        # Create tmux session
        await self.terminal.setup()

        # Launch Neovim in editor pane
        await self.terminal.launch_editor()

        # Connect to Neovim RPC
        await asyncio.sleep(1.5)  # Wait for nvim to be ready
        await self.editor.connect()

        # Navigate to working directory
        await self.terminal.send_keys(
            self.terminal.shell_pane,
            f"cd {self.config.working_dir}",
            enter=True,
        )
        await asyncio.sleep(0.5)

        logger.info("Desktop environment ready")

    async def _plan_and_execute(self, task_description: str) -> SessionResult:
        """Use Claude Code to do the actual engineering work.

        Claude runs headlessly at full speed. We capture its actions
        (Edit, Bash, Write) to replay them visibly later.
        """
        logger.info("Sending task to Claude Code...")

        prompt = self._build_engineering_prompt(task_description)

        result = await self.claude.execute(
            prompt=prompt,
            working_dir=self.config.working_dir,
        )

        if result.exit_code != 0:
            logger.error("Claude Code failed: %s", result.error)
            raise RuntimeError(f"Claude Code failed: {result.error}")

        logger.info("Claude Code completed: %d actions captured", len(result.actions))

        if result.session_id:
            self.snapshot.claude_session_id = result.session_id

        return result

    async def _work(self, result: SessionResult) -> None:
        """Replay captured actions visibly at human speed."""
        actions = result.actions
        if not actions:
            logger.warning("No actions to replay — Claude produced no tool calls")
            await self.behavior.idle_think(30)
            return

        total = len(actions)
        shell_input = TmuxInput(self.terminal.shell_pane)
        editor_input = TmuxInput(self.terminal.editor_pane)

        for i, action in enumerate(actions):
            # Check time budget
            elapsed = time.monotonic() - self._start_time
            remaining = self._time_budget_seconds - elapsed
            if remaining < 60:
                logger.info("Time budget nearly exhausted, stopping replay")
                break

            await self.event_bus.emit(
                TaskProgress(
                    activity_index=i,
                    total_activities=total,
                    description=f"Action {i + 1}/{total}: {action.kind.value}",
                )
            )

            logger.info(
                "Replaying action %d/%d: %s %s",
                i + 1, total, action.kind.value,
                action.file_path or action.command[:40] if action.command else "",
            )

            if action.kind == ActionKind.EDIT:
                await self._replay_edit(action, editor_input)
            elif action.kind == ActionKind.WRITE:
                await self._replay_write(action, editor_input)
            elif action.kind == ActionKind.BASH:
                await self._replay_bash(action, shell_input)

            # Natural pause between actions
            await self.behavior.pause_natural(2.0, 8.0)

            # Occasional think pause (simulate reading/reviewing)
            if i < total - 1 and i % 3 == 2:
                think_time = 10.0 + (remaining / total) * 0.3
                think_time = min(think_time, 45.0)
                logger.debug("Thinking for %.0f seconds...", think_time)
                await self.behavior.idle_think(think_time)

            self.snapshot.current_activity_index = i + 1
            self.snapshot.completed_activities.append(i)
            self._persist_state()

    async def _replay_edit(self, action, editor_input: TmuxInput) -> None:
        """Replay an Edit action visibly in Neovim."""
        # Focus editor pane
        await self.terminal.focus_pane(self.terminal.editor_pane)
        await asyncio.sleep(0.5)

        # Open the file
        open_cmd = f":e {action.file_path}"
        await self.behavior.type_command(
            open_cmd,
            editor_input.type_char,
            lambda: editor_input.type_key("Enter"),
        )
        await asyncio.sleep(1.0)

        # If it's a replacement (old_string -> new_string), simulate editing
        content = action.new_string or action.content
        if content:
            # Enter insert mode
            await editor_input.type_key("i")
            await asyncio.sleep(0.3)

            # Type the content with human timing
            # Limit how much we type to keep things reasonable
            text_to_type = content[:2000] if len(content) > 2000 else content
            await self.behavior.type_text(
                text_to_type,
                editor_input.type_char,
                editor_input.send_backspace,
                is_code=True,
            )

            # Exit insert mode
            await asyncio.sleep(0.3)
            await editor_input.type_key("Escape")
            await asyncio.sleep(0.3)

        # Save
        await self.behavior.type_command(
            ":w",
            editor_input.type_char,
            lambda: editor_input.type_key("Enter"),
        )
        await asyncio.sleep(0.5)

    async def _replay_write(self, action, editor_input: TmuxInput) -> None:
        """Replay a Write action (new file) visibly in Neovim."""
        # Same as edit but for a new file
        await self._replay_edit(action, editor_input)

    async def _replay_bash(self, action, shell_input: TmuxInput) -> None:
        """Replay a Bash command visibly in the terminal."""
        # Focus shell pane
        await self.terminal.focus_pane(self.terminal.shell_pane)
        await asyncio.sleep(0.5)

        # Type the command
        await self.behavior.type_command(
            action.command,
            shell_input.type_char,
            lambda: shell_input.type_key("Enter"),
        )

        # Wait for command to finish (rough heuristic based on command)
        wait_time = self._estimate_command_wait(action.command)
        await asyncio.sleep(wait_time)

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

    async def _wrap_up(self) -> None:
        """Final wrap-up: git commit and status."""
        logger.info("Wrapping up session...")

        shell_input = TmuxInput(self.terminal.shell_pane)
        await self.terminal.focus_pane(self.terminal.shell_pane)
        await asyncio.sleep(0.5)

        # git status
        await self.behavior.type_command(
            "git status",
            shell_input.type_char,
            lambda: shell_input.type_key("Enter"),
        )
        await asyncio.sleep(2.0)

        # git add and commit
        await self.behavior.type_command(
            "git add -A",
            shell_input.type_char,
            lambda: shell_input.type_key("Enter"),
        )
        await asyncio.sleep(1.0)

        commit_msg = f"feat: {self.snapshot.task_description[:50]}"
        await self.behavior.type_command(
            f'git commit -m "{commit_msg}"',
            shell_input.type_char,
            lambda: shell_input.type_key("Enter"),
        )
        await asyncio.sleep(2.0)

        logger.info("Wrap-up complete")

    async def _cleanup(self) -> None:
        """Clean up resources."""
        await self.editor.cleanup()
        # Don't kill tmux — leave it for the user to inspect
        logger.info("Cleanup done. tmux session '%s' left open.", self.terminal.session_name)

    def _transition(self, trigger: str) -> None:
        """Execute a state transition and emit event."""
        old = self.state_machine.state
        new = self.state_machine.transition(trigger)
        self.snapshot.state = new.value
        # Fire and forget the event
        asyncio.get_event_loop().create_task(
            self.event_bus.emit(StateChanged(old.value, new.value, trigger))
        )

    def _persist_state(self) -> None:
        """Save current state to disk."""
        elapsed = time.monotonic() - self._start_time if self._start_time else 0
        self.snapshot.elapsed_minutes = elapsed / 60.0
        state_path = self.config.runtime_dir / "state.json"
        try:
            self.snapshot.save(state_path)
        except Exception:
            logger.warning("Failed to persist state", exc_info=True)

    def _build_engineering_prompt(self, task_description: str) -> str:
        """Build the prompt sent to Claude Code for actual engineering work."""
        return (
            f"Complete the following software engineering task:\n\n"
            f"{task_description}\n\n"
            f"Work in the current directory. Use Edit/Write tools for file changes "
            f"and Bash tool for terminal commands. Follow existing project conventions. "
            f"Write clean, working code with appropriate error handling."
        )
