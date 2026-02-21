"""[STAGED] Editor controller for Neovim.

Planned for future Sway compositor target (see docs/05-compositor.md).
Not currently imported by the main application — VS Code is used instead.

Requires pynvim (not in pyproject.toml — install manually when activating this module).
Provides programmatic control over Neovim via RPC socket for querying state,
while visible typing goes through tmux send-keys (via BehaviorEngine).
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

NVIM_SOCKET = "/tmp/work4me-nvim.sock"


class EditorController:
    """Controls Neovim via RPC for state queries and tmux for visible actions."""

    def __init__(self, nvim_socket: str = NVIM_SOCKET) -> None:
        self.nvim_socket = nvim_socket
        self._nvim: Any = None

    async def connect(self) -> None:
        """Connect to Neovim RPC socket."""
        try:
            import pynvim  # type: ignore[import-untyped]

            self._nvim = await asyncio.to_thread(
                pynvim.attach, "socket", path=self.nvim_socket
            )
            logger.info("Connected to Neovim at %s", self.nvim_socket)
        except Exception as exc:
            logger.warning("Could not connect to Neovim: %s", exc)
            self._nvim = None

    async def open_file(self, file_path: str, line: int = 1) -> None:
        """Open a file in Neovim via RPC.

        For visible opening (typing :e filename), use tmux send-keys instead.
        """
        if self._nvim is None:
            await self.connect()
        if self._nvim:
            try:
                await asyncio.to_thread(self._nvim.command, f":e {file_path}")
                if line > 1:
                    await asyncio.to_thread(self._nvim.command, f":{line}")
                logger.debug("Opened %s at line %d", file_path, line)
            except Exception as exc:
                logger.warning("Failed to open file in Neovim: %s", exc)

    async def get_cursor_position(self) -> tuple[int, int]:
        """Get current cursor position (row, col)."""
        if self._nvim:
            try:
                cursor = await asyncio.to_thread(
                    lambda: self._nvim.current.window.cursor
                )
                return (cursor[0], cursor[1])
            except Exception:
                pass
        return (1, 0)

    async def get_buffer_content(self) -> list[str]:
        """Get current buffer content as list of lines."""
        if self._nvim:
            try:
                return await asyncio.to_thread(
                    lambda: list(self._nvim.current.buffer[:])
                )
            except Exception:
                pass
        return []

    async def get_current_file(self) -> str:
        """Get the path of the currently open file."""
        if self._nvim:
            try:
                return await asyncio.to_thread(
                    lambda: str(self._nvim.current.buffer.name)
                )
            except Exception:
                pass
        return ""

    async def health_check(self) -> bool:
        """Check if Neovim is responsive."""
        if self._nvim is None:
            return False
        try:
            await asyncio.to_thread(self._nvim.command, "echo ''")
            return True
        except Exception:
            return False

    async def restart(self) -> None:
        """Reconnect to Neovim."""
        self._nvim = None
        await asyncio.sleep(0.5)
        await self.connect()

    async def cleanup(self) -> None:
        """Close Neovim connection."""
        if self._nvim:
            try:
                await asyncio.to_thread(self._nvim.close)
            except Exception:
                pass
            self._nvim = None
