# tests/test_vscode_controller.py
import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch  # noqa: F811
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


@pytest.mark.asyncio
async def test_restart_reconnects(controller):
    controller._ws = MagicMock()
    controller._ws.close = AsyncMock()
    with patch.object(controller, 'connect', new_callable=AsyncMock) as mock_connect:
        await controller.restart()
        mock_connect.assert_called_once()
    assert controller._ws is None or mock_connect.called


@pytest.mark.asyncio
async def test_send_command_validates_response_id(controller):
    """send_command should verify response ID matches request."""
    mock_ws = AsyncMock()
    # First recv returns wrong ID, second returns correct ID
    mock_ws.recv = AsyncMock(side_effect=[
        json.dumps({"id": "999", "success": True, "result": {"wrong": True}}),
        json.dumps({"id": "1", "success": True, "result": {"correct": True}}),
    ])
    controller._ws = mock_ws
    controller._msg_id = 0

    result = await controller.send_command("test")
    assert result["correct"] is True


@pytest.mark.asyncio
async def test_send_command_retries_on_wrong_id(controller):
    """send_command should retry recv when response ID doesn't match."""
    mock_ws = AsyncMock()
    # Three wrong IDs → should raise RuntimeError
    mock_ws.recv = AsyncMock(side_effect=[
        json.dumps({"id": "wrong1", "success": True, "result": {}}),
        json.dumps({"id": "wrong2", "success": True, "result": {}}),
        json.dumps({"id": "wrong3", "success": True, "result": {}}),
    ])
    controller._ws = mock_ws
    controller._msg_id = 0

    with pytest.raises(RuntimeError, match="response ID mismatch"):
        await controller.send_command("test")
