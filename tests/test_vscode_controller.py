# tests/test_vscode_controller.py
import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from work4me.controllers.vscode import VSCodeController
from work4me.config import VSCodeConfig

@pytest.fixture
def config():
    return VSCodeConfig(websocket_port=9876)

@pytest.fixture
def controller(config):
    return VSCodeController(config)

def test_controller_init(controller):
    assert controller._ws is None
    assert controller._port == 9876

@pytest.mark.asyncio
async def test_send_command_returns_result(controller):
    mock_ws = AsyncMock()
    mock_ws.recv = AsyncMock(return_value=json.dumps({
        "id": "1", "success": True, "result": {"opened": "test.py"}
    }))
    controller._ws = mock_ws
    controller._msg_id = 0

    result = await controller.send_command("openFile", path="test.py")
    assert result["opened"] == "test.py"
    mock_ws.send.assert_called_once()

@pytest.mark.asyncio
async def test_open_file(controller):
    controller.send_command = AsyncMock(return_value={"opened": "test.py", "line": 1})
    await controller.open_file("test.py", line=1)
    controller.send_command.assert_called_with("openFile", path="test.py", line=1)

@pytest.mark.asyncio
async def test_type_text(controller):
    controller.send_command = AsyncMock(return_value={"typed": 5})
    await controller.type_text("hello")
    controller.send_command.assert_called_with("typeText", text="hello")

@pytest.mark.asyncio
async def test_save_file(controller):
    controller.send_command = AsyncMock(return_value={"saved": "test.py"})
    await controller.save_file()
    controller.send_command.assert_called_with("saveFile")

@pytest.mark.asyncio
async def test_run_terminal_command(controller):
    controller.send_command = AsyncMock(return_value={"sent": "npm test"})
    await controller.run_terminal_command("npm test")
    controller.send_command.assert_called_with("runTerminalCommand", cmd="npm test", name="Work4Me")

@pytest.mark.asyncio
async def test_health_check_no_connection(controller):
    assert await controller.health_check() is False

@pytest.mark.asyncio
async def test_health_check_with_connection(controller):
    controller.send_command = AsyncMock(return_value={"pong": True})
    controller._ws = MagicMock()
    assert await controller.health_check() is True
