"""VS Code controller via WebSocket bridge extension."""

import asyncio
import json
import logging
from typing import Any

from work4me.config import VSCodeConfig

logger = logging.getLogger(__name__)


class VSCodeController:
    """Controls VS Code via the work4me-bridge WebSocket extension."""

    def __init__(self, config: VSCodeConfig):
        self._port = config.websocket_port
        self._executable = config.executable
        self._extension_dir = config.extension_dir
        self._ws: Any = None  # websockets connection
        self._msg_id = 0
        self._launch_on_start = config.launch_on_start

    async def connect(self, retries: int = 5, delay: float = 2.0) -> None:
        """Connect to the VS Code WebSocket bridge."""
        try:
            import websockets
        except ImportError:
            raise RuntimeError("websockets package required: pip install websockets")

        uri = f"ws://localhost:{self._port}"
        for attempt in range(retries):
            try:
                self._ws = await websockets.connect(uri)
                logger.info("Connected to VS Code bridge at %s", uri)
                return
            except (ConnectionRefusedError, OSError):
                if attempt < retries - 1:
                    logger.debug("VS Code bridge not ready, retry %d/%d", attempt + 1, retries)
                    await asyncio.sleep(delay)
        raise ConnectionError(f"Cannot connect to VS Code bridge at {uri} after {retries} attempts")

    async def launch(self, working_dir: str = ".") -> None:
        """Launch VS Code with the bridge extension loaded."""
        cmd = [self._executable, "--new-window", working_dir]
        if self._extension_dir:
            cmd.extend(["--extensions-dir", self._extension_dir])
        logger.info("Launching VS Code: %s", " ".join(cmd))
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        # Don't wait — VS Code runs independently
        logger.info("VS Code launched (pid=%d)", proc.pid)

    async def send_command(self, command: str, timeout: float = 30.0, **kwargs: Any) -> dict:
        """Send a command to the VS Code extension and return the result."""
        if self._ws is None:
            raise ConnectionError("Not connected to VS Code bridge")

        self._msg_id += 1
        msg = {"id": str(self._msg_id), "command": command, **kwargs}
        await self._ws.send(json.dumps(msg))
        try:
            raw = await asyncio.wait_for(self._ws.recv(), timeout=timeout)
        except asyncio.TimeoutError:
            raise TimeoutError(f"VS Code command '{command}' timed out after {timeout}s")
        response = json.loads(raw)

        if not response.get("success"):
            raise RuntimeError(f"VS Code command failed: {response.get('error')}")
        return response.get("result", {})

    async def open_file(self, path: str, line: int = 1) -> None:
        """Open a file in the editor at the given line."""
        await self.send_command("openFile", path=path, line=line)

    async def type_text(self, text: str) -> None:
        """Insert text at the current cursor position."""
        await self.send_command("typeText", text=text)

    async def navigate_to(self, line: int, col: int = 0) -> None:
        """Move cursor to line:col."""
        await self.send_command("navigateTo", line=line, col=col)

    async def save_file(self) -> None:
        """Save the active file."""
        await self.send_command("saveFile")

    async def get_active_file(self) -> dict:
        """Get info about the currently active file."""
        return await self.send_command("getActiveFile")

    async def get_visible_text(self) -> str:
        """Get the currently visible text in the editor."""
        result = await self.send_command("getVisibleText")
        return result.get("text", "")

    async def run_terminal_command(self, cmd: str, name: str = "Work4Me") -> None:
        """Run a command in the VS Code integrated terminal."""
        await self.send_command("runTerminalCommand", cmd=cmd, name=name)

    async def show_terminal(self) -> None:
        """Focus the integrated terminal panel."""
        await self.send_command("showTerminal")

    async def focus_editor(self) -> None:
        """Focus the editor panel."""
        await self.send_command("focusEditor")

    async def new_file(self, path: str) -> None:
        """Create and open a new file."""
        await self.send_command("newFile", path=path)

    async def replace_file_content(self, content: str) -> None:
        """Replace the entire content of the active file."""
        await self.send_command("replaceFileContent", content=content)

    async def health_check(self) -> bool:
        """Check if the VS Code bridge is responsive."""
        if self._ws is None:
            return False
        try:
            result = await self.send_command("ping")
            return result.get("pong", False)
        except Exception:
            return False

    async def cleanup(self) -> None:
        """Close the WebSocket connection."""
        if self._ws:
            await self._ws.close()
            self._ws = None
