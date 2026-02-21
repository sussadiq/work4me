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


# --- Tests for _extract_actions ---

def test_extract_actions_from_assistant_edit():
    """Edit tool_use blocks in assistant events should be extracted."""
    mgr = ClaudeCodeManager(ClaudeConfig())
    event = {
        "type": "assistant",
        "message": {
            "content": [{
                "type": "tool_use",
                "name": "Edit",
                "input": {"file_path": "foo.py", "old_string": "old", "new_string": "new"},
            }]
        },
    }
    actions = mgr._extract_actions(event)
    assert len(actions) == 1
    assert actions[0].kind == ActionKind.EDIT
    assert actions[0].file_path == "foo.py"


def test_extract_actions_from_assistant_bash():
    """Bash tool_use blocks should be extracted."""
    mgr = ClaudeCodeManager(ClaudeConfig())
    event = {
        "type": "assistant",
        "message": {
            "content": [{
                "type": "tool_use",
                "name": "Bash",
                "input": {"command": "npm test"},
            }]
        },
    }
    actions = mgr._extract_actions(event)
    assert len(actions) == 1
    assert actions[0].kind == ActionKind.BASH
    assert actions[0].command == "npm test"


def test_extract_actions_from_assistant_write():
    """Write tool_use blocks should be extracted."""
    mgr = ClaudeCodeManager(ClaudeConfig())
    event = {
        "type": "assistant",
        "message": {
            "content": [{
                "type": "tool_use",
                "name": "Write",
                "input": {"file_path": "new.py", "content": "print('hi')"},
            }]
        },
    }
    actions = mgr._extract_actions(event)
    assert len(actions) == 1
    assert actions[0].kind == ActionKind.WRITE
    assert actions[0].content == "print('hi')"


def test_extract_actions_from_result_event():
    """tool_use blocks in result events should also be extracted."""
    mgr = ClaudeCodeManager(ClaudeConfig())
    event = {
        "type": "result",
        "session_id": "sess-abc",
        "content": [{
            "type": "tool_use",
            "name": "Edit",
            "input": {"file_path": "r.py", "old_string": "a", "new_string": "b"},
        }],
    }
    actions = mgr._extract_actions(event)
    assert len(actions) == 1
    assert mgr._last_session_id == "sess-abc"


def test_extract_actions_ignores_unknown_tools():
    """Unknown tool names should be silently skipped."""
    mgr = ClaudeCodeManager(ClaudeConfig())
    event = {
        "type": "assistant",
        "message": {
            "content": [{
                "type": "tool_use",
                "name": "UnknownTool",
                "input": {"data": "stuff"},
            }]
        },
    }
    actions = mgr._extract_actions(event)
    assert actions == []


# --- Tests for _parse_tool_use ---

def test_parse_tool_use_edit_fields():
    """_parse_tool_use should extract all Edit fields."""
    mgr = ClaudeCodeManager(ClaudeConfig())
    block = {
        "name": "Edit",
        "input": {"file_path": "x.py", "old_string": "old", "new_string": "new"},
    }
    action = mgr._parse_tool_use(block)
    assert action is not None
    assert action.kind == ActionKind.EDIT
    assert action.file_path == "x.py"
    assert action.old_string == "old"
    assert action.new_string == "new"


def test_parse_tool_use_bash_fields():
    """_parse_tool_use should extract Bash command."""
    mgr = ClaudeCodeManager(ClaudeConfig())
    block = {"name": "Bash", "input": {"command": "ls -la"}}
    action = mgr._parse_tool_use(block)
    assert action is not None
    assert action.kind == ActionKind.BASH
    assert action.command == "ls -la"


def test_parse_tool_use_returns_none_for_unknown():
    """_parse_tool_use should return None for unrecognized tools."""
    mgr = ClaudeCodeManager(ClaudeConfig())
    block = {"name": "Read", "input": {"file_path": "x.py"}}
    assert mgr._parse_tool_use(block) is None


# --- Tests for _build_command ---

def test_build_command_basic():
    """Basic command should include -p, output-format, verbose, model."""
    mgr = ClaudeCodeManager(ClaudeConfig())
    cmd = mgr._build_command("hello world")
    assert "-p" in cmd
    assert "hello world" in cmd
    assert "--output-format" in cmd
    assert "stream-json" in cmd
    assert "--verbose" in cmd
    assert "--model" in cmd


def test_build_command_with_resume():
    """--resume flag should be included when resume_session is set."""
    mgr = ClaudeCodeManager(ClaudeConfig())
    cmd = mgr._build_command("test", resume_session="sess-123")
    assert "--resume" in cmd
    idx = cmd.index("--resume")
    assert cmd[idx + 1] == "sess-123"


def test_build_command_with_max_turns():
    """Custom max_turns should override config default."""
    mgr = ClaudeCodeManager(ClaudeConfig(max_turns=15))
    cmd = mgr._build_command("test", max_turns=5)
    idx = cmd.index("--max-turns")
    assert cmd[idx + 1] == "5"


def test_build_command_skip_permissions():
    """--dangerously-skip-permissions should be included when config says so."""
    mgr = ClaudeCodeManager(ClaudeConfig(dangerously_skip_permissions=True))
    cmd = mgr._build_command("test")
    assert "--dangerously-skip-permissions" in cmd

    mgr2 = ClaudeCodeManager(ClaudeConfig(dangerously_skip_permissions=False))
    cmd2 = mgr2._build_command("test")
    assert "--dangerously-skip-permissions" not in cmd2


def test_build_command_extra_args():
    """Extra args from config should be appended."""
    mgr = ClaudeCodeManager(ClaudeConfig(extra_args=["--foo", "bar"]))
    cmd = mgr._build_command("test")
    assert "--foo" in cmd
    assert "bar" in cmd


def test_build_command_max_budget():
    """Custom max_budget should override config default."""
    mgr = ClaudeCodeManager(ClaudeConfig(max_budget_usd=10.0))
    cmd = mgr._build_command("test", max_budget=2.5)
    idx = cmd.index("--max-budget-usd")
    assert cmd[idx + 1] == "2.5"
