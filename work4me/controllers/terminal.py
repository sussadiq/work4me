"""[STAGED] Terminal controller using tmux.

Planned for future Sway compositor target (see docs/05-compositor.md).
Not currently imported by the main application — VS Code terminal is used instead.

Creates and manages a tmux session with split panes for shell and editor.
Provides methods to send keystrokes, read output, and manage panes.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from dataclasses import dataclass

logger = logging.getLogger(__name__)

TMUX_SESSION = "work4me"
NVIM_SOCKET = "/tmp/work4me-nvim.sock"


@dataclass
class PaneInfo:
    pane_id: str
    pane_index: int
    width: int
    height: int
    current_command: str


class TerminalController:
    """Controls a tmux session for visible terminal work."""

    def __init__(self, session_name: str = TMUX_SESSION) -> None:
        self.session_name = session_name
        self._shell_pane = f"{session_name}:0.0"
        self._editor_pane = f"{session_name}:0.1"
        self._ready = False

    async def setup(self) -> None:
        """Create tmux session with shell + editor panes."""
        if not shutil.which("tmux"):
            raise RuntimeError("tmux not found. Install with: apt install tmux")

        # Kill any existing session
        await self._tmux("kill-session", "-t", self.session_name, check=False)

        # Create new detached session
        await self._tmux(
            "new-session", "-d",
            "-s", self.session_name,
            "-x", "200", "-y", "50",
        )

        # Split horizontally — left shell, right editor
        await self._tmux(
            "split-window", "-t", self.session_name, "-h",
        )

        # Focus shell pane
        await self._tmux("select-pane", "-t", self._shell_pane)

        self._ready = True
        logger.info("tmux session '%s' created with shell + editor panes", self.session_name)

    async def launch_editor(self, nvim_socket: str = NVIM_SOCKET) -> None:
        """Launch Neovim in the editor pane."""
        # Clean up stale socket
        import os
        if os.path.exists(nvim_socket):
            os.unlink(nvim_socket)

        await self.send_keys(
            self._editor_pane,
            f"nvim --listen {nvim_socket}",
            enter=True,
        )
        # Wait for nvim to start
        await asyncio.sleep(1.0)
        logger.info("Neovim launched in editor pane, socket: %s", nvim_socket)

    async def send_keys(
        self, target: str | None = None, keys: str = "", *, enter: bool = False
    ) -> None:
        """Send keystrokes to a tmux pane.

        Args:
            target: Pane target (e.g. "work4me:0.0"). Defaults to shell pane.
            keys: Text or key names to send.
            enter: Whether to append Enter keystroke.
        """
        target = target or self._shell_pane
        args = ["send-keys", "-t", target, keys]
        if enter:
            args.append("Enter")
        await self._tmux(*args)

    async def send_keys_slowly(
        self, target: str | None = None, text: str = "", *, char_delay: float = 0.08
    ) -> None:
        """Send text character by character with delay (for visible typing).

        Note: For proper human-like typing, use BehaviorEngine.type_text() instead.
        This method provides basic character-by-character sending.
        """
        target = target or self._shell_pane
        for char in text:
            # Escape special tmux characters
            if char == ";":
                await self._tmux("send-keys", "-t", target, "-l", char)
            elif char == "\n":
                await self._tmux("send-keys", "-t", target, "Enter")
            else:
                await self._tmux("send-keys", "-t", target, "-l", char)
            await asyncio.sleep(char_delay)

    async def capture_pane(self, target: str | None = None, lines: int = 50) -> str:
        """Read visible content from a tmux pane."""
        target = target or self._shell_pane
        result = await self._tmux(
            "capture-pane", "-t", target, "-p",
            "-S", str(-lines),
            capture=True,
        )
        return result

    async def run_command(self, command: str, *, wait_seconds: float = 2.0) -> str:
        """Send a command to the shell pane and capture output.

        Args:
            command: Shell command to execute.
            wait_seconds: How long to wait for output.

        Returns:
            Captured pane content after command execution.
        """
        await self.send_keys(self._shell_pane, command, enter=True)
        await asyncio.sleep(wait_seconds)
        return await self.capture_pane(self._shell_pane)

    async def focus_pane(self, target: str | None = None) -> None:
        """Focus a specific pane."""
        target = target or self._shell_pane
        await self._tmux("select-pane", "-t", target)

    @property
    def shell_pane(self) -> str:
        return self._shell_pane

    @property
    def editor_pane(self) -> str:
        return self._editor_pane

    async def health_check(self) -> bool:
        """Check if the tmux session is alive."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "tmux", "has-session", "-t", self.session_name,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()
            return proc.returncode == 0
        except Exception:
            return False

    async def restart(self) -> None:
        """Restart the tmux session."""
        logger.warning("Restarting tmux session")
        await self.cleanup()
        await self.setup()

    async def cleanup(self) -> None:
        """Kill the tmux session."""
        await self._tmux("kill-session", "-t", self.session_name, check=False)
        self._ready = False
        logger.info("tmux session '%s' killed", self.session_name)

    async def _tmux(
        self, *args: str, check: bool = True, capture: bool = False
    ) -> str:
        """Run a tmux command."""
        cmd = ["tmux"] + list(args)
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE if capture else asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await proc.communicate()

        if check and proc.returncode != 0:
            stderr_text = (stderr_bytes or b"").decode(errors="replace").strip()
            raise RuntimeError(f"tmux command failed: {' '.join(args)}: {stderr_text}")

        if capture and stdout_bytes:
            return stdout_bytes.decode(errors="replace")
        return ""
