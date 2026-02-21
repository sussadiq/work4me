"""Claude Code CLI subprocess manager.

Spawns `claude -p` in non-interactive mode with stream-json output,
parses events in real-time, and extracts tool_use actions (Edit, Bash)
into a structured action queue for the orchestrator to replay visibly.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import AsyncIterator

from work4me.config import ClaudeConfig

logger = logging.getLogger(__name__)


class ActionKind(Enum):
    EDIT = "edit"
    BASH = "bash"
    WRITE = "write"
    TEXT = "text"


@dataclass
class CapturedAction:
    """An action extracted from Claude Code's stream-json output."""

    kind: ActionKind
    file_path: str = ""
    content: str = ""
    command: str = ""
    old_string: str = ""
    new_string: str = ""


@dataclass
class SessionResult:
    """Result of a Claude Code invocation."""

    session_id: str = ""
    actions: list[CapturedAction] = field(default_factory=list)
    raw_text: str = ""
    exit_code: int = 0
    error: str = ""


class ClaudeCodeManager:
    """Manages Claude Code CLI as a subprocess."""

    def __init__(self, config: ClaudeConfig) -> None:
        self.config = config
        self._process: asyncio.subprocess.Process | None = None
        self._last_session_id: str = ""
        self._collected_texts: list[str] = []

    def _build_command(
        self,
        prompt: str,
        *,
        resume_session: str | None = None,
        max_turns: int | None = None,
        max_budget: float | None = None,
    ) -> list[str]:
        cmd = [self.config.cli_path]

        if resume_session:
            cmd.extend(["--resume", resume_session])

        cmd.extend(["-p", prompt])
        cmd.extend(["--output-format", "stream-json"])
        cmd.append("--verbose")

        if self.config.dangerously_skip_permissions:
            cmd.append("--dangerously-skip-permissions")

        turns = max_turns or self.config.max_turns
        cmd.extend(["--max-turns", str(turns)])

        budget = max_budget or self.config.max_budget_usd
        cmd.extend(["--max-budget-usd", str(budget)])

        cmd.extend(["--model", self.config.model])

        cmd.extend(self.config.extra_args)

        return cmd

    async def execute(
        self,
        prompt: str,
        working_dir: str,
        *,
        resume_session: str | None = None,
        max_turns: int | None = None,
        max_budget: float | None = None,
    ) -> SessionResult:
        """Run Claude Code and collect all actions.

        Returns a SessionResult with captured Edit/Bash/Write actions
        and the session_id for future resumption.
        """
        cmd = self._build_command(
            prompt,
            resume_session=resume_session,
            max_turns=max_turns,
            max_budget=max_budget,
        )

        logger.info("Spawning Claude Code: %s", " ".join(cmd[:6]) + " ...")
        logger.debug("Full command: %s", cmd)
        logger.debug("Working dir: %s", working_dir)

        result = SessionResult()

        try:
            self._last_session_id = ""
            self._process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=working_dir,
            )

            assert self._process.stdout is not None
            assert self._process.stderr is not None

            async for action in self._parse_stream(self._process.stdout):
                result.actions.append(action)

            await self._process.wait()
            result.exit_code = self._process.returncode or 0
            result.session_id = self._last_session_id
            result.raw_text = "\n".join(self._collected_texts)

            if result.exit_code != 0:
                stderr_bytes = await self._process.stderr.read()
                result.error = stderr_bytes.decode(errors="replace").strip()
                logger.error(
                    "Claude Code exited with code %d: %s",
                    result.exit_code,
                    result.error[:200],
                )

        except FileNotFoundError:
            result.exit_code = 127
            result.error = f"Claude Code CLI not found at: {self.config.cli_path}"
            logger.error(result.error)
        except Exception as exc:
            result.exit_code = 1
            result.error = str(exc)
            logger.exception("Claude Code execution failed")
        finally:
            self._process = None

        logger.info(
            "Claude Code finished: %d actions captured, exit code %d",
            len(result.actions),
            result.exit_code,
        )
        return result

    async def execute_streaming(
        self,
        prompt: str,
        working_dir: str,
        *,
        resume_session: str | None = None,
        max_turns: int | None = None,
        max_budget: float | None = None,
    ) -> AsyncIterator[CapturedAction]:
        """Run Claude Code and yield actions as they arrive."""
        cmd = self._build_command(
            prompt,
            resume_session=resume_session,
            max_turns=max_turns,
            max_budget=max_budget,
        )

        logger.info("Spawning Claude Code (streaming): %s", " ".join(cmd[:6]) + " ...")

        self._process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=working_dir,
        )

        assert self._process.stdout is not None

        try:
            async for action in self._parse_stream(self._process.stdout):
                yield action
        finally:
            if self._process.returncode is None:
                self._process.terminate()
                await self._process.wait()
            self._process = None

    async def _parse_stream(
        self, stdout: asyncio.StreamReader
    ) -> AsyncIterator[CapturedAction]:
        """Parse newline-delimited JSON from Claude Code stdout.

        Extracts tool_use events where the tool is Edit, Write, or Bash.
        Only captures from complete 'assistant' message events (not partial
        streaming events like content_block_start which have empty input).

        Deduplicates by tracking tool_use IDs already seen.
        """
        seen_tool_ids: set[str] = set()
        self._collected_texts = []

        async for raw_line in stdout:
            line = raw_line.decode(errors="replace").strip()
            if not line:
                continue

            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                logger.debug("Non-JSON line from Claude: %s", line[:100])
                continue

            self._collected_texts.extend(self._extract_text_blocks(event))

            for action in self._extract_actions(event):
                # Deduplicate using a hash of the action content
                action_key = f"{action.kind.value}:{action.file_path}:{action.command}:{hash(action.new_string or action.content)}"
                if action_key not in seen_tool_ids:
                    seen_tool_ids.add(action_key)
                    yield action

    def _extract_text_blocks(self, event: dict) -> list[str]:
        """Extract text content blocks from a stream-json event."""
        texts: list[str] = []
        event_type = event.get("type", "")

        if event_type == "assistant":
            content = event.get("message", {}).get("content", [])
        elif event_type == "result":
            session_id = event.get("session_id", "")
            if session_id:
                self._last_session_id = session_id
            content = event.get("content", [])
        else:
            return texts

        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text = block.get("text", "")
                    if text:
                        texts.append(text)
        return texts

    def _extract_actions(self, event: dict) -> list[CapturedAction]:
        """Extract CapturedActions from a stream-json event.

        Only captures from complete events (assistant messages with full input),
        not from partial streaming events (content_block_start has empty input).
        """
        actions: list[CapturedAction] = []
        event_type = event.get("type", "")

        # Assistant message — contains complete tool_use blocks with full input
        if event_type == "assistant":
            message = event.get("message", {})
            content = message.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        action = self._parse_tool_use(block)
                        if action is not None:
                            actions.append(action)

        # Result event — final message, also has session_id
        if event_type == "result":
            # Extract session_id
            session_id = event.get("session_id", "")
            if session_id:
                self._last_session_id = session_id

            content = event.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        action = self._parse_tool_use(block)
                        if action is not None:
                            actions.append(action)

        return actions

    def _parse_tool_use(self, block: dict) -> CapturedAction | None:
        """Parse a tool_use block into a CapturedAction."""
        tool_name = block.get("name", "")
        tool_input = block.get("input", {})

        if tool_name == "Edit":
            return CapturedAction(
                kind=ActionKind.EDIT,
                file_path=tool_input.get("file_path", ""),
                old_string=tool_input.get("old_string", ""),
                new_string=tool_input.get("new_string", ""),
            )

        if tool_name == "Write":
            return CapturedAction(
                kind=ActionKind.WRITE,
                file_path=tool_input.get("file_path", ""),
                content=tool_input.get("content", ""),
            )

        if tool_name == "Bash":
            return CapturedAction(
                kind=ActionKind.BASH,
                command=tool_input.get("command", ""),
            )

        return None

    async def cancel(self) -> None:
        """Cancel the running Claude Code process."""
        if self._process and self._process.returncode is None:
            logger.info("Cancelling Claude Code process")
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except TimeoutError:
                logger.warning("Claude Code didn't exit, killing")
                self._process.kill()
                await self._process.wait()
