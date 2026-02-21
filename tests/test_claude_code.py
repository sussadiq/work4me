# tests/test_claude_code.py
"""Tests for ClaudeCodeManager stream parsing and text capture."""

from work4me.controllers.claude_code import ClaudeCodeManager, ClaudeConfig


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
