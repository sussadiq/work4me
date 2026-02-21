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


@pytest.mark.asyncio
async def test_connect_defaults(controller):
    """connect() should use 10 retries and exponential backoff by default."""
    import inspect
    sig = inspect.signature(controller.connect)
    assert sig.parameters['retries'].default == 10
    assert sig.parameters['delay'].default == 1.0


@pytest.mark.asyncio
async def test_connect_exponential_backoff(controller):
    """connect() should use exponential backoff capped at 5s."""
    mock_ws_module = MagicMock()
    mock_ws_module.connect = AsyncMock(side_effect=ConnectionRefusedError)
    sleep_delays = []
    original_sleep = asyncio.sleep

    async def mock_sleep(duration):
        sleep_delays.append(duration)

    with patch.dict('sys.modules', {'websockets': mock_ws_module}), \
         patch('asyncio.sleep', side_effect=mock_sleep):
        with pytest.raises(ConnectionError, match="after 5 attempts"):
            await controller.connect(retries=5, delay=1.0)

    # Backoff: 1.0, 2.0, 4.0, 5.0 (capped) — 4 sleeps for 5 retries
    assert len(sleep_delays) == 4
    assert sleep_delays[0] == 1.0
    assert sleep_delays[1] == 2.0
    assert sleep_delays[2] == 4.0
    assert sleep_delays[3] == 5.0  # capped at max_delay


@pytest.mark.asyncio
async def test_open_claude_sidebar(controller):
    controller.send_command = AsyncMock(return_value={
        "opened": "claude-sidebar",
        "extensionActive": True,
        "extensionVersion": "2.1.49",
    })
    result = await controller.open_claude_sidebar()
    controller.send_command.assert_called_with("openClaudeCode")
    assert result["opened"] == "claude-sidebar"
    assert result["extensionVersion"] == "2.1.49"


@pytest.mark.asyncio
async def test_check_claude_extension(controller):
    controller.send_command = AsyncMock(return_value={"installed": True, "active": True})
    result = await controller.check_claude_extension()
    controller.send_command.assert_called_with("checkClaudeExtension")
    assert result["installed"] is True
    assert result["active"] is True


@pytest.mark.asyncio
async def test_focus_claude_input(controller):
    controller.send_command = AsyncMock(return_value={"focused": "claude-input"})
    await controller.focus_claude_input()
    controller.send_command.assert_called_with("focusClaudeInput")


@pytest.mark.asyncio
async def test_blur_claude_input(controller):
    controller.send_command = AsyncMock(return_value={"blurred": "claude-input"})
    await controller.blur_claude_input()
    controller.send_command.assert_called_with("blurClaudeInput")


@pytest.mark.asyncio
async def test_new_claude_conversation(controller):
    controller.send_command = AsyncMock(return_value={"newConversation": True})
    await controller.new_claude_conversation()
    controller.send_command.assert_called_with("newClaudeConversation")


@pytest.mark.asyncio
async def test_accept_diff(controller):
    controller.send_command = AsyncMock(return_value={"accepted": True})
    await controller.accept_diff()
    controller.send_command.assert_called_with("acceptDiff")


@pytest.mark.asyncio
async def test_reject_diff(controller):
    controller.send_command = AsyncMock(return_value={"rejected": True})
    await controller.reject_diff()
    controller.send_command.assert_called_with("rejectDiff")


@pytest.mark.asyncio
async def test_start_claude_watch(controller):
    controller.send_command = AsyncMock(return_value={"watching": True})
    await controller.start_claude_watch()
    controller.send_command.assert_called_with("startClaudeWatch")


@pytest.mark.asyncio
async def test_stop_claude_watch(controller):
    controller.send_command = AsyncMock(return_value={"totalChanges": 5, "lastChangeTimestamp": 1234})
    result = await controller.stop_claude_watch()
    controller.send_command.assert_called_with("stopClaudeWatch")
    assert result["totalChanges"] == 5


@pytest.mark.asyncio
async def test_get_claude_status(controller):
    controller.send_command = AsyncMock(return_value={"fileChanges": 3, "idleMs": 2000})
    result = await controller.get_claude_status()
    controller.send_command.assert_called_with("getClaudeStatus")
    assert result["fileChanges"] == 3


@pytest.mark.asyncio
async def test_is_claude_busy_when_active(controller):
    controller.send_command = AsyncMock(return_value={"idleMs": 1000})
    assert await controller.is_claude_busy(idle_threshold_ms=5000) is True


@pytest.mark.asyncio
async def test_is_claude_busy_when_idle(controller):
    controller.send_command = AsyncMock(return_value={"idleMs": 10000})
    assert await controller.is_claude_busy(idle_threshold_ms=5000) is False


@pytest.mark.asyncio
async def test_connect_logs_at_info_level(controller):
    """connect() should log retries at INFO level."""
    mock_ws_module = MagicMock()
    mock_ws_module.connect = AsyncMock(side_effect=ConnectionRefusedError)

    with patch.dict('sys.modules', {'websockets': mock_ws_module}), \
         patch('asyncio.sleep', new_callable=AsyncMock), \
         patch('work4me.controllers.vscode.logger') as mock_logger:
        with pytest.raises(ConnectionError):
            await controller.connect(retries=3, delay=1.0)

    # Should log at INFO (not DEBUG) for each retry except the last
    info_calls = mock_logger.info.call_args_list
    retry_logs = [c for c in info_calls if "not ready" in str(c)]
    assert len(retry_logs) == 2  # 2 retries before final failure
