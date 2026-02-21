# tests/test_claude_code.py
"""Tests for ClaudeCodeManager stream parsing and text capture."""

import pytest
from work4me.controllers.claude_code import ClaudeCodeManager, CapturedAction, ActionKind, ClaudeConfig


def test_raw_text_captured_from_assistant_message():
    """Text blocks from assistant messages should populate raw_text."""
    mgr = ClaudeCodeManager(ClaudeConfig())
    event = {
        "type": "assistant",
        "message": {
            "content": [
                {"type": "text", "text": "Here is the plan:\n[{\"kind\": \"CODING\"}]"}
            ]
        },
    }
    texts = mgr._extract_text_blocks(event)
    assert len(texts) == 1
    assert "CODING" in texts[0]


def test_raw_text_captured_from_result_event():
    """Text blocks from result events should populate raw_text."""
    mgr = ClaudeCodeManager(ClaudeConfig())
    event = {
        "type": "result",
        "session_id": "abc",
        "content": [{"type": "text", "text": "Final answer text"}],
    }
    texts = mgr._extract_text_blocks(event)
    assert len(texts) == 1
    assert "Final answer" in texts[0]


def test_raw_text_empty_for_tool_only():
    """Events with only tool_use blocks produce no text."""
    mgr = ClaudeCodeManager(ClaudeConfig())
    event = {
        "type": "assistant",
        "message": {
            "content": [
                {"type": "tool_use", "name": "Edit", "input": {"file_path": "x.py"}}
            ]
        },
    }
    texts = mgr._extract_text_blocks(event)
    assert texts == []


def test_raw_text_result_captures_session_id():
    """Result events should also capture session_id."""
    mgr = ClaudeCodeManager(ClaudeConfig())
    event = {
        "type": "result",
        "session_id": "sess-123",
        "content": [{"type": "text", "text": "done"}],
    }
    mgr._extract_text_blocks(event)
    assert mgr._last_session_id == "sess-123"


def test_raw_text_ignores_system_events():
    """System events should produce no text."""
    mgr = ClaudeCodeManager(ClaudeConfig())
    event = {"type": "system", "data": "init"}
    texts = mgr._extract_text_blocks(event)
    assert texts == []


@pytest.mark.asyncio
async def test_dedup_keeps_edits_with_different_old_string():
    """Two edits with same file+new_string but different old_string must both be yielded."""
    mgr = ClaudeCodeManager(ClaudeConfig())

    event = {
        "type": "assistant",
        "message": {
            "content": [
                {
                    "type": "tool_use",
                    "name": "Edit",
                    "input": {"file_path": "x.py", "old_string": "foo", "new_string": "baz"},
                },
                {
                    "type": "tool_use",
                    "name": "Edit",
                    "input": {"file_path": "x.py", "old_string": "bar", "new_string": "baz"},
                },
            ]
        },
    }

    # Simulate streaming by encoding event as JSON line
    import json
    import asyncio

    line = json.dumps(event).encode() + b"\n"
    reader = asyncio.StreamReader()
    reader.feed_data(line)
    reader.feed_eof()

    actions = [a async for a in mgr._parse_stream(reader)]
    assert len(actions) == 2
    assert actions[0].old_string == "foo"
    assert actions[1].old_string == "bar"


@pytest.mark.asyncio
async def test_execute_raises_if_stdout_pipe_missing():
    """Missing stdout pipe should produce an error, not pass silently under -O."""
    from unittest.mock import AsyncMock, MagicMock, patch
    import asyncio

    mgr = ClaudeCodeManager(ClaudeConfig())

    mock_proc = MagicMock()
    mock_proc.stdout = None
    mock_proc.stderr = MagicMock()

    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_proc):
        result = await mgr.execute("test prompt", "/tmp")
    assert "stdout pipe" in result.error


@pytest.mark.asyncio
async def test_execute_streaming_stderr_devnull():
    """execute_streaming should use DEVNULL for stderr to prevent deadlock."""
    from unittest.mock import AsyncMock, MagicMock, patch, call
    import asyncio

    mgr = ClaudeCodeManager(ClaudeConfig())

    mock_proc = MagicMock()
    mock_proc.stdout = asyncio.StreamReader()
    mock_proc.stdout.feed_eof()
    mock_proc.returncode = 0
    mock_proc.terminate = MagicMock()
    mock_proc.wait = AsyncMock(return_value=0)

    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_proc) as mock_exec:
        actions = []
        async for action in mgr.execute_streaming("test", "/tmp"):
            actions.append(action)

        # Verify stderr=DEVNULL was used
        _, kwargs = mock_exec.call_args
        assert kwargs["stderr"] == asyncio.subprocess.DEVNULL
