"""[STAGED] Input simulation layer for Wayland.

Planned for future Sway compositor target (see docs/05-compositor.md).
Not currently imported by the main application — VS Code extension handles input.

Provides an abstraction over input methods:
- ydotool/dotool (universal, kernel uinput)
- RemoteDesktop portal (GNOME/KDE, future)

For MVP, uses ydotool/dotool as the primary backend.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from typing import Protocol

logger = logging.getLogger(__name__)


class InputMethod(Protocol):
    """Protocol for input simulation backends."""

    async def type_char(self, char: str) -> None: ...
    async def type_key(self, key_name: str) -> None: ...
    async def type_text(self, text: str) -> None: ...
    async def move_mouse(self, x: int, y: int, *, absolute: bool = True) -> None: ...
    async def click_mouse(self, button: int = 1) -> None: ...
    async def health_check(self) -> bool: ...


class DotoolInput:
    """Input simulation via dotool (uinput-based, works on all Wayland compositors).

    dotool reads commands from stdin, supports key names directly.
    Requires dotoold daemon running and /dev/uinput access.
    """

    def __init__(self) -> None:
        self._dotool_path = shutil.which("dotool")
        self._ydotool_path = shutil.which("ydotool")

    async def type_char(self, char: str) -> None:
        """Type a single character."""
        if char == "\n":
            await self._run_dotool("key Return")
        elif char == "\t":
            await self._run_dotool("key Tab")
        elif char == " ":
            await self._run_dotool("key space")
        else:
            await self._run_dotool(f"type {char}")

    async def type_key(self, key_name: str) -> None:
        """Press a named key (e.g., 'Return', 'BackSpace', 'Escape')."""
        await self._run_dotool(f"key {key_name}")

    async def type_text(self, text: str) -> None:
        """Type a string of text at once (fast, no human timing)."""
        await self._run_dotool(f"type {text}")

    async def move_mouse(self, x: int, y: int, *, absolute: bool = True) -> None:
        """Move mouse cursor."""
        if absolute:
            await self._run_dotool(f"mouseto {x} {y}")
        else:
            await self._run_dotool(f"mousemove {x} {y}")

    async def click_mouse(self, button: int = 1) -> None:
        """Click a mouse button (1=left, 2=middle, 3=right)."""
        await self._run_dotool(f"click {button}")

    async def health_check(self) -> bool:
        """Check if dotool/ydotool is available and functional."""
        if self._dotool_path:
            return True  # dotool doesn't need a daemon
        if not self._ydotool_path:
            return False
        # Verify ydotoold daemon is reachable by running a no-op type
        try:
            proc = await asyncio.create_subprocess_exec(
                self._ydotool_path, "type", "--key-delay", "0", "--", "",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            return b"ydotoold backend unavailable" not in stderr
        except Exception:
            return False

    async def _run_dotool(self, command: str) -> None:
        """Execute a dotool command by piping to stdin."""
        if self._dotool_path:
            proc = await asyncio.create_subprocess_exec(
                self._dotool_path,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate(input=command.encode())
            if proc.returncode != 0:
                logger.warning("dotool command failed: %s", command)
        elif self._ydotool_path:
            await self._run_ydotool(command)
        else:
            logger.error("No input simulation tool available (dotool or ydotool)")

    async def _run_ydotool(self, dotool_command: str) -> None:
        """Translate dotool command to ydotool equivalent."""
        if self._ydotool_path is None:
            return
        parts = dotool_command.split(maxsplit=1)
        action = parts[0]
        arg = parts[1] if len(parts) > 1 else ""

        if action == "type":
            cmd = [self._ydotool_path, "type", "--", arg]
        elif action == "key":
            cmd = [self._ydotool_path, "key", arg]
        elif action == "mouseto":
            coords = arg.split()
            cmd = [self._ydotool_path, "mousemove", "--absolute", "-x", coords[0], "-y", coords[1]]
        elif action == "mousemove":
            coords = arg.split()
            cmd = [self._ydotool_path, "mousemove", "-x", coords[0], "-y", coords[1]]
        elif action == "click":
            # ydotool click: button codes differ
            cmd = [self._ydotool_path, "click", arg]
        else:
            logger.warning("Unknown dotool command for ydotool translation: %s", action)
            return

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            logger.warning("ydotool failed: %s", stderr.decode(errors="replace").strip())


class TmuxInput:
    """Input simulation via tmux send-keys.

    Sends keystrokes to a specific tmux pane. This is visible in the terminal
    but doesn't generate system-level keyboard events (won't register with
    time trackers that monitor /dev/input). Best used alongside DotoolInput.
    """

    def __init__(self, pane_target: str = "work4me:0.0") -> None:
        self.pane_target = pane_target

    async def type_char(self, char: str) -> None:
        if char == "\n":
            await self._send_keys("Enter")
        elif char == "\t":
            await self._send_keys("Tab")
        else:
            await self._send_keys_literal(char)

    async def type_key(self, key_name: str) -> None:
        await self._send_keys(key_name)

    async def type_text(self, text: str) -> None:
        await self._send_keys_literal(text)

    async def send_backspace(self) -> None:
        await self._send_keys("BSpace")

    async def move_mouse(self, x: int, y: int, *, absolute: bool = True) -> None:
        pass  # tmux doesn't support mouse movement

    async def click_mouse(self, button: int = 1) -> None:
        pass  # tmux doesn't support mouse clicks

    async def health_check(self) -> bool:
        return shutil.which("tmux") is not None

    async def _send_keys(self, keys: str) -> None:
        proc = await asyncio.create_subprocess_exec(
            "tmux", "send-keys", "-t", self.pane_target, keys,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()

    async def _send_keys_literal(self, text: str) -> None:
        proc = await asyncio.create_subprocess_exec(
            "tmux", "send-keys", "-t", self.pane_target, "-l", text,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()


def detect_input_method() -> DotoolInput:
    """Detect available input simulation method.

    For MVP, returns DotoolInput which supports both dotool and ydotool.
    """
    method = DotoolInput()
    if method._dotool_path:
        logger.info("Using dotool for input simulation")
    elif method._ydotool_path:
        logger.info("Using ydotool for input simulation")
    else:
        logger.warning("No input simulation tool found. Install dotool or ydotool.")
    return method
