# tests/test_orchestrator.py
"""Tests for the revised dual-mode orchestrator."""

import asyncio
import shlex
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from work4me.core.orchestrator import Orchestrator
from work4me.config import Config
from work4me.planning.task_planner import Activity, ActivityKind, TaskPlan
from work4me.planning.scheduler import Schedule, WorkSession


@pytest.fixture
def config():
    return Config()


@pytest.fixture
def orchestrator(config):
    return Orchestrator(config)


def test_orchestrator_has_mode(orchestrator):
    assert orchestrator._mode in ("manual", "ai-assisted")


def test_orchestrator_has_vscode_controller(orchestrator):
    from work4me.controllers.vscode import VSCodeController
    assert isinstance(orchestrator._vscode, VSCodeController)


def test_orchestrator_has_browser_controller(orchestrator):
    from work4me.controllers.browser import BrowserController
    assert isinstance(orchestrator._browser_ctrl, BrowserController)


def test_orchestrator_has_activity_monitor(orchestrator):
    from work4me.behavior.activity_monitor import ActivityMonitor
    assert isinstance(orchestrator._activity_monitor, ActivityMonitor)


def test_orchestrator_has_planner(orchestrator):
    from work4me.planning.task_planner import TaskPlanner
    assert isinstance(orchestrator._planner, TaskPlanner)


@pytest.mark.asyncio
async def test_execute_activity_coding_mode_a(orchestrator):
    activity = Activity(
        ActivityKind.CODING, "Write auth", 20,
        ["src/auth.ts"], [], [], [],
    )
    orchestrator._mode = "manual"
    orchestrator._claude = AsyncMock()
    orchestrator._claude.execute = AsyncMock(return_value=MagicMock(
        actions=[], raw_text="done", exit_code=0, error=None
    ))
    orchestrator._vscode = AsyncMock()
    orchestrator._behavior = AsyncMock()
    orchestrator._activity_monitor = MagicMock()
    orchestrator._activity_monitor.recommended_adjustment = MagicMock(
        return_value=MagicMock(value="none")
    )

    await orchestrator._execute_activity(activity, working_dir="/tmp")
    orchestrator._claude.execute.assert_called_once()


@pytest.mark.asyncio
async def test_execute_activity_browser(orchestrator):
    activity = Activity(
        ActivityKind.BROWSER, "Research JWT", 10,
        [], [], ["jwt express middleware"], [],
    )
    orchestrator._browser_ctrl = AsyncMock()
    orchestrator._behavior = AsyncMock()
    orchestrator._activity_monitor = MagicMock()
    orchestrator._activity_monitor.recommended_adjustment = MagicMock(
        return_value=MagicMock(value="none")
    )

    await orchestrator._execute_activity(activity, working_dir="/tmp")
    orchestrator._browser_ctrl.search.assert_called()


@pytest.mark.asyncio
async def test_watchdog_tick_healthy():
    config = Config(mode="manual")
    orch = Orchestrator(config)
    orch._vscode = AsyncMock()
    orch._vscode.health_check = AsyncMock(return_value=True)
    orch._browser_ctrl = AsyncMock()
    orch._browser_ctrl.health_check = AsyncMock(return_value=True)
    await orch._watchdog_tick()
    orch._vscode.restart.assert_not_called()
    orch._browser_ctrl.restart.assert_not_called()


@pytest.mark.asyncio
async def test_watchdog_tick_unhealthy_vscode():
    config = Config(mode="manual")
    orch = Orchestrator(config)
    orch._vscode = AsyncMock()
    orch._vscode.health_check = AsyncMock(return_value=False)
    orch._vscode.restart = AsyncMock()
    orch._browser_ctrl = AsyncMock()
    orch._browser_ctrl.health_check = AsyncMock(return_value=True)
    await orch._watchdog_tick()
    orch._vscode.restart.assert_called_once()


@pytest.mark.asyncio
async def test_retry_succeeds_on_second_attempt():
    config = Config(mode="manual")
    orch = Orchestrator(config)
    orch._behavior = AsyncMock()
    orch._activity_monitor = MagicMock()
    orch._activity_monitor.record_event = MagicMock()

    call_count = 0
    async def flaky_execute(activity, working_dir):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("Temporary failure")

    orch._execute_activity = AsyncMock(side_effect=flaky_execute)
    activity = Activity(ActivityKind.CODING, "test", 5, [], [], [], [])
    # Patch asyncio.sleep to avoid real delays during retry backoff
    with patch("work4me.core.orchestrator.asyncio.sleep", new_callable=AsyncMock):
        await orch._execute_activity_with_retry(activity, "/tmp", max_retries=3)
    assert call_count == 2


@pytest.mark.asyncio
async def test_retry_exhausted_raises():
    config = Config(mode="manual")
    orch = Orchestrator(config)
    orch._behavior = AsyncMock()
    orch._activity_monitor = MagicMock()
    orch._activity_monitor.record_event = MagicMock()

    orch._execute_activity = AsyncMock(side_effect=RuntimeError("Persistent failure"))
    activity = Activity(ActivityKind.CODING, "test", 5, [], [], [], [])
    with patch("work4me.core.orchestrator.asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(RuntimeError, match="Persistent failure"):
            await orch._execute_activity_with_retry(activity, "/tmp", max_retries=2)


@pytest.mark.asyncio
async def test_run_checks_for_recovery():
    """run() should call check_for_recovery at startup."""
    from work4me.core.state import StateSnapshot

    config = Config(mode="manual")
    orch = Orchestrator(config)

    # Mock check_for_recovery to track it was called
    called = []
    def tracking_check():
        called.append(True)
        return None  # No recovery needed
    orch.check_for_recovery = tracking_check

    # Mock everything else to avoid actual execution
    orch._initialize = AsyncMock()
    orch._start_watchdog = AsyncMock()
    orch._stop_watchdog = AsyncMock()
    orch._plan = AsyncMock(return_value=Schedule(sessions=[], total_budget_minutes=60))
    orch._wrap_up = AsyncMock()
    orch._cleanup = AsyncMock()
    orch._persist_state = MagicMock()

    await orch.run("test task", 60, "/tmp")
    assert len(called) == 1


@pytest.mark.asyncio
async def test_run_resumes_from_recovery():
    """run() should restore snapshot when recovering a resumable session."""
    from work4me.core.state import StateSnapshot, State

    config = Config(mode="manual")
    orch = Orchestrator(config)

    # Provide a resumable snapshot
    snap = StateSnapshot()
    snap.state = State.WORKING.value
    snap.task_description = "Recovered task"
    snap.current_activity_index = 2
    orch.check_for_recovery = lambda: snap

    orch._initialize = AsyncMock()
    orch._start_watchdog = AsyncMock()
    orch._stop_watchdog = AsyncMock()
    orch._plan = AsyncMock(return_value=Schedule(sessions=[], total_budget_minutes=60))
    orch._wrap_up = AsyncMock()
    orch._cleanup = AsyncMock()
    orch._persist_state = MagicMock()

    await orch.run("test task", 60, "/tmp")
    assert orch.snapshot.task_description == "Recovered task"
    assert orch.snapshot.current_activity_index == 2


@pytest.mark.asyncio
async def test_ai_assisted_prompt_is_shell_escaped(orchestrator):
    """Shell metacharacters in prompt must be escaped."""
    activity = Activity(
        ActivityKind.CODING, "Write auth", 20,
        ["src/auth.ts"], [], [], [],
    )
    orchestrator._mode = "ai-assisted"
    orchestrator._vscode = AsyncMock()
    orchestrator._behavior = AsyncMock()
    orchestrator._activity_monitor = MagicMock()

    prompt_with_injection = "'; rm -rf / #"
    orchestrator._build_activity_prompt = MagicMock(return_value=prompt_with_injection)

    await orchestrator._execute_coding_ai_assisted(activity, working_dir="/tmp")

    # Find the call to run_terminal_command that has the claude command
    for c in orchestrator._vscode.run_terminal_command.call_args_list:
        cmd_arg = c[0][0]
        if "claude" in cmd_arg:
            # Must contain the shlex-quoted version (safely escaped)
            assert shlex.quote(prompt_with_injection[:200]) in cmd_arg
            # Must NOT use bare double-quote wrapping (the old vulnerable pattern)
            assert f'"{prompt_with_injection[:200]}"' not in cmd_arg
            break
    else:
        pytest.fail("run_terminal_command was not called with a claude command")


@pytest.mark.asyncio
async def test_wrap_up_commit_msg_is_shell_escaped(orchestrator):
    """Shell metacharacters in commit message must be escaped."""
    orchestrator._vscode = AsyncMock()

    orchestrator.snapshot.task_description = 'foo"; echo pwned; "'

    await orchestrator._wrap_up("/tmp")

    # Find the git commit call
    for c in orchestrator._vscode.run_terminal_command.call_args_list:
        cmd_arg = c[0][0]
        if "git commit" in cmd_arg:
            # Must NOT contain unescaped double quotes from injection
            assert 'echo pwned' not in cmd_arg or "'" in cmd_arg
            # Must use shlex.quote
            commit_msg = f"feat: {orchestrator.snapshot.task_description[:50]}"
            assert shlex.quote(commit_msg) in cmd_arg
            break
    else:
        pytest.fail("run_terminal_command was not called with git commit")


@pytest.mark.asyncio
async def test_replay_action_rejects_path_traversal(orchestrator):
    """Path traversal in file_path must be blocked."""
    from work4me.controllers.claude_code import CapturedAction, ActionKind as AK

    orchestrator._vscode = AsyncMock()
    orchestrator._behavior = AsyncMock()
    orchestrator.snapshot.working_dir = "/tmp/project"

    action = CapturedAction(kind=AK.EDIT, file_path="../../../etc/passwd", new_string="hacked")
    await orchestrator._replay_action_in_vscode(action)
    orchestrator._vscode.open_file.assert_not_called()


@pytest.mark.asyncio
async def test_replay_action_allows_valid_path(orchestrator):
    """Valid file paths within working_dir should be opened."""
    from work4me.controllers.claude_code import CapturedAction, ActionKind as AK

    orchestrator._vscode = AsyncMock()
    orchestrator._behavior = AsyncMock()
    orchestrator.snapshot.working_dir = "/tmp/project"

    action = CapturedAction(kind=AK.EDIT, file_path="src/auth.py", new_string="code")
    await orchestrator._replay_action_in_vscode(action)
    orchestrator._vscode.open_file.assert_called_once()


@pytest.mark.asyncio
async def test_retry_zero_raises_runtime_error():
    """max_retries=0 should raise RuntimeError, not TypeError from raise None."""
    config = Config(mode="manual")
    orch = Orchestrator(config)
    orch._behavior = AsyncMock()
    orch._activity_monitor = MagicMock()

    activity = Activity(ActivityKind.CODING, "test", 5, [], [], [], [])
    with pytest.raises(RuntimeError, match="max_retries must be >= 1"):
        await orch._execute_activity_with_retry(activity, "/tmp", max_retries=0)


@pytest.mark.asyncio
async def test_retry_propagates_cancelled_error():
    """CancelledError should not be retried."""
    config = Config(mode="manual")
    orch = Orchestrator(config)
    orch._behavior = AsyncMock()
    orch._activity_monitor = MagicMock()

    orch._execute_activity = AsyncMock(side_effect=asyncio.CancelledError)
    activity = Activity(ActivityKind.CODING, "test", 5, [], [], [], [])
    with pytest.raises(asyncio.CancelledError):
        await orch._execute_activity_with_retry(activity, "/tmp", max_retries=3)
