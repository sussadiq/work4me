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
    assert orchestrator._mode in ("sidebar", "manual")


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
    orchestrator._window_mgr = AsyncMock()
    orchestrator._activity_monitor = MagicMock()
    orchestrator._activity_monitor.recommended_adjustment = MagicMock(
        return_value=MagicMock(value="none")
    )

    await orchestrator._execute_activity(activity, working_dir="/tmp")
    call_kwargs = orchestrator._claude.execute.call_args
    assert call_kwargs[1]["working_dir"] == "/tmp" or call_kwargs[0][1] == "/tmp"


@pytest.mark.asyncio
async def test_execute_activity_browser(orchestrator):
    activity = Activity(
        ActivityKind.BROWSER, "Research JWT", 10,
        [], [], ["jwt express middleware"], [],
    )
    orchestrator._browser_ctrl = AsyncMock()
    orchestrator._behavior = AsyncMock()
    orchestrator._window_mgr = AsyncMock()
    orchestrator._activity_monitor = MagicMock()
    orchestrator._activity_monitor.recommended_adjustment = MagicMock(
        return_value=MagicMock(value="none")
    )

    await orchestrator._execute_activity(activity, working_dir="/tmp")
    orchestrator._browser_ctrl.search.assert_called_once_with("jwt express middleware")


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
    snap.task_description = "test task"  # Must match the task being started
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
    assert orch.snapshot.task_description == "test task"
    assert orch.snapshot.current_activity_index == 2


@pytest.mark.asyncio
async def test_default_mode_is_sidebar():
    """Config default mode should be 'sidebar'."""
    config = Config()
    assert config.mode == "sidebar"
    orch = Orchestrator(config)
    assert orch._mode == "sidebar"


@pytest.mark.asyncio
async def test_execute_coding_sidebar_mode():
    """Sidebar mode should use bridge commands for prompt input."""
    config = Config(mode="sidebar")
    orch = Orchestrator(config)
    activity = Activity(
        ActivityKind.CODING, "Write auth", 20,
        ["src/auth.ts"], [], [], [],
    )
    orch._vscode = AsyncMock()
    orch._vscode.check_claude_extension = AsyncMock(return_value={"installed": True, "active": True})
    orch._vscode.configure_claude_permissions = AsyncMock(return_value={"configured": True, "mode": "acceptEdits"})
    orch._vscode.open_claude_sidebar = AsyncMock(return_value={
        "opened": "claude-sidebar", "extensionActive": True, "extensionVersion": "2.1.49",
    })
    orch._vscode.send_claude_prompt = AsyncMock(return_value={"prompted": True, "length": 42})
    orch._vscode.submit_claude_prompt = AsyncMock(return_value={"submitted": True})
    orch._vscode.is_claude_busy = AsyncMock(return_value=False)
    orch._vscode.stop_claude_watch = AsyncMock(return_value={"totalChanges": 3})
    orch._behavior = AsyncMock()
    orch._window_mgr = AsyncMock()
    orch._activity_monitor = MagicMock()
    orch.snapshot.working_dir = "/tmp"

    await orch._execute_coding_sidebar(activity, "/tmp")

    orch._vscode.check_claude_extension.assert_called_once()
    orch._vscode.configure_claude_permissions.assert_called_once_with("acceptEdits")
    orch._vscode.open_claude_sidebar.assert_called_once()
    orch._vscode.new_claude_conversation.assert_called_once()
    orch._vscode.send_claude_prompt.assert_called_once()
    # Submit via bridge (Enter within VS Code process)
    orch._vscode.submit_claude_prompt.assert_called_once()
    orch._vscode.start_claude_watch.assert_called_once()
    orch._vscode.stop_claude_watch.assert_called_once()


@pytest.mark.asyncio
async def test_sidebar_falls_back_to_manual_on_error():
    """When sidebar fails, should fall back to manual mode."""
    config = Config(mode="sidebar")
    orch = Orchestrator(config)
    activity = Activity(
        ActivityKind.CODING, "Write auth", 20,
        ["src/auth.ts"], [], [], [],
    )
    orch._vscode = AsyncMock()
    orch._vscode.check_claude_extension = AsyncMock(return_value={"installed": True, "active": True})
    orch._vscode.open_claude_sidebar = AsyncMock(side_effect=RuntimeError("Extension not available"))
    orch._claude = AsyncMock()
    orch._claude.execute = AsyncMock(return_value=MagicMock(
        actions=[], raw_text="done", exit_code=0, error=None
    ))
    orch._behavior = AsyncMock()
    orch._window_mgr = AsyncMock()
    orch._input_sim = AsyncMock()
    orch._activity_monitor = MagicMock()
    orch.snapshot.working_dir = "/tmp"

    await orch._execute_coding_sidebar(activity, "/tmp")
    # Should have fallen back to manual — Claude headless should be called
    orch._claude.execute.assert_called_once()


@pytest.mark.asyncio
async def test_sidebar_fallback_warning_mentions_extension(caplog):
    """Fallback warning should mention 'anthropic.claude-code' for actionability."""
    import logging
    config = Config(mode="sidebar")
    orch = Orchestrator(config)
    activity = Activity(
        ActivityKind.CODING, "Write auth", 20,
        ["src/auth.ts"], [], [], [],
    )
    orch._vscode = AsyncMock()
    orch._vscode.check_claude_extension = AsyncMock(return_value={"installed": True, "active": True})
    orch._vscode.open_claude_sidebar = AsyncMock(side_effect=RuntimeError("boom"))
    orch._claude = AsyncMock()
    orch._claude.execute = AsyncMock(return_value=MagicMock(
        actions=[], raw_text="done", exit_code=0, error=None
    ))
    orch._behavior = AsyncMock()
    orch._window_mgr = AsyncMock()
    orch._input_sim = AsyncMock()
    orch._activity_monitor = MagicMock()
    orch.snapshot.working_dir = "/tmp"

    with caplog.at_level(logging.WARNING):
        await orch._execute_coding_sidebar(activity, "/tmp")

    assert any("anthropic.claude-code" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_sidebar_precheck_not_installed_falls_back():
    """When checkClaudeExtension reports not installed, should fall back to manual."""
    config = Config(mode="sidebar")
    orch = Orchestrator(config)
    activity = Activity(
        ActivityKind.CODING, "Write auth", 20,
        ["src/auth.ts"], [], [], [],
    )
    orch._vscode = AsyncMock()
    orch._vscode.check_claude_extension = AsyncMock(return_value={"installed": False, "active": False})
    orch._claude = AsyncMock()
    orch._claude.execute = AsyncMock(return_value=MagicMock(
        actions=[], raw_text="done", exit_code=0, error=None
    ))
    orch._behavior = AsyncMock()
    orch._window_mgr = AsyncMock()
    orch._input_sim = AsyncMock()
    orch._activity_monitor = MagicMock()
    orch.snapshot.working_dir = "/tmp"

    await orch._execute_coding_sidebar(activity, "/tmp")
    # Pre-check should have raised, triggering manual fallback
    orch._claude.execute.assert_called_once()
    # open_claude_sidebar should NOT have been called
    orch._vscode.open_claude_sidebar.assert_not_called()


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
async def test_execute_session_skips_completed_activities():
    """When resuming, activities before activity_start_index should be skipped."""
    config = Config(mode="manual")
    orch = Orchestrator(config)
    orch._behavior = AsyncMock()
    orch._activity_monitor = MagicMock()
    orch._activity_monitor.recommended_adjustment = MagicMock(
        return_value=MagicMock(value="none")
    )
    orch.event_bus = AsyncMock()
    orch._time_budget_seconds = 99999
    orch._start_time = 0

    activities = [
        Activity(ActivityKind.THINKING, f"Think {i}", 1, [], [], [], [])
        for i in range(5)
    ]
    session = WorkSession(
        activities=activities, duration_minutes=10,
        break_after_minutes=0, session_number=1,
    )

    executed = []
    original_execute = orch._execute_activity_with_retry
    async def tracking_execute(activity, working_dir, **kwargs):
        executed.append(activity.description)
    orch._execute_activity_with_retry = AsyncMock(side_effect=tracking_execute)
    orch._persist_state = MagicMock()

    await orch._execute_session(session, "/tmp", activity_start_index=3)
    assert len(executed) == 2
    assert executed[0] == "Think 3"
    assert executed[1] == "Think 4"


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


# ------------------------------------------------------------------
# Window focus integration
# ------------------------------------------------------------------


def test_orchestrator_has_window_manager(orchestrator):
    from work4me.desktop.window_mgr import WindowManager
    assert hasattr(orchestrator, "_window_mgr")


@pytest.mark.asyncio
async def test_coding_manual_focuses_vscode_window(orchestrator):
    """_execute_coding_manual should focus the VS Code window."""
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
    orchestrator._window_mgr = AsyncMock()
    orchestrator._activity_monitor = MagicMock()

    orchestrator.snapshot.working_dir = "/tmp"
    await orchestrator._execute_coding_manual(activity, "/tmp")
    orchestrator._window_mgr.focus_window.assert_called_once_with(
        "code", title_hint="tmp",
    )


@pytest.mark.asyncio
async def test_coding_sidebar_focuses_vscode_window(orchestrator):
    """_execute_coding_sidebar should focus the VS Code window."""
    activity = Activity(
        ActivityKind.CODING, "Write auth", 20,
        ["src/auth.ts"], [], [], [],
    )
    orchestrator._mode = "sidebar"
    orchestrator._vscode = AsyncMock()
    orchestrator._vscode.check_claude_extension = AsyncMock(return_value={"installed": True, "active": True})
    orchestrator._vscode.configure_claude_permissions = AsyncMock(return_value={"configured": True, "mode": "acceptEdits"})
    orchestrator._vscode.open_claude_sidebar = AsyncMock(return_value={
        "opened": "claude-sidebar", "extensionActive": True, "extensionVersion": "2.1.49",
    })
    orchestrator._vscode.send_claude_prompt = AsyncMock(return_value={"prompted": True, "length": 42})
    orchestrator._vscode.submit_claude_prompt = AsyncMock(return_value={"submitted": True})
    orchestrator._vscode.is_claude_busy = AsyncMock(return_value=False)
    orchestrator._vscode.stop_claude_watch = AsyncMock(return_value={"totalChanges": 0})
    orchestrator._behavior = AsyncMock()
    orchestrator._window_mgr = AsyncMock()
    orchestrator._activity_monitor = MagicMock()

    orchestrator.snapshot.working_dir = "/tmp"
    await orchestrator._execute_coding_sidebar(activity, "/tmp")
    orchestrator._window_mgr.focus_window.assert_called_once_with(
        "code", title_hint="tmp",
    )


@pytest.mark.asyncio
async def test_browser_activity_focuses_firefox_window(orchestrator):
    """_execute_browser should focus the browser window after health check."""
    activity = Activity(
        ActivityKind.BROWSER, "Research JWT", 10,
        [], [], ["jwt express middleware"], [],
    )
    orchestrator._browser_ctrl = AsyncMock()
    orchestrator._browser_ctrl.health_check = AsyncMock(return_value=True)
    orchestrator._behavior = AsyncMock()
    orchestrator._window_mgr = AsyncMock()
    orchestrator._activity_monitor = MagicMock()

    await orchestrator._execute_browser(activity)
    orchestrator._window_mgr.focus_window.assert_called_once_with(
        "firefox", title_hint="",
    )


@pytest.mark.asyncio
async def test_terminal_activity_focuses_vscode_window(orchestrator):
    """_execute_terminal should focus the VS Code window."""
    activity = Activity(
        ActivityKind.TERMINAL, "Run tests", 5,
        [], ["pytest"], [], [],
    )
    orchestrator._vscode = AsyncMock()
    orchestrator._behavior = AsyncMock()
    orchestrator._window_mgr = AsyncMock()
    orchestrator._activity_monitor = MagicMock()

    orchestrator.snapshot.working_dir = "/tmp"
    await orchestrator._execute_terminal(activity, "/tmp")
    orchestrator._window_mgr.focus_window.assert_called_once_with(
        "code", title_hint="tmp",
    )


@pytest.mark.asyncio
async def test_reading_activity_focuses_vscode_window(orchestrator):
    """_execute_reading should focus the VS Code window."""
    activity = Activity(
        ActivityKind.READING, "Read docs", 5,
        [], [], [], [],
    )
    orchestrator._vscode = AsyncMock()
    orchestrator._behavior = AsyncMock()
    orchestrator._window_mgr = AsyncMock()
    orchestrator._activity_monitor = MagicMock()

    orchestrator.snapshot.working_dir = "/tmp"
    await orchestrator._execute_reading(activity)
    orchestrator._window_mgr.focus_window.assert_called_once_with(
        "code", title_hint="tmp",
    )


@pytest.mark.asyncio
async def test_focus_failure_does_not_block_activity(orchestrator):
    """If window focus fails, the activity should still execute."""
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
    orchestrator._window_mgr = AsyncMock()
    orchestrator._window_mgr.focus_window = AsyncMock(return_value=False)
    orchestrator._activity_monitor = MagicMock()

    await orchestrator._execute_coding_manual(activity, "/tmp")
    # Activity should still proceed — Claude should have been called
    orchestrator._claude.execute.assert_called_once()
    # pause_natural should NOT be called for window focus (focus returned False)
    # but may be called for other reasons — just verify activity completed


# ------------------------------------------------------------------
# Fallback plan on planning failure
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_plan_uses_fallback_on_planner_failure():
    """_plan() should return a fallback schedule when planner.decompose raises."""
    config = Config(mode="manual")
    orch = Orchestrator(config)
    orch._planner = AsyncMock()
    orch._planner.decompose = AsyncMock(side_effect=RuntimeError("planning failed"))

    schedule = await orch._plan("Build auth system", 60, "/tmp")
    # Fallback should still produce a usable schedule
    assert isinstance(schedule, Schedule)
    assert len(schedule.sessions) >= 1


@pytest.mark.asyncio
async def test_fallback_plan_creates_single_activity():
    """_fallback_plan() should create a schedule with 1 CODING activity at 70% budget."""
    config = Config(mode="manual")
    orch = Orchestrator(config)

    schedule = orch._fallback_plan("Build auth system", 100)

    # Collect all activities across sessions
    all_activities = [a for s in schedule.sessions for a in s.activities]
    assert len(all_activities) == 1
    assert all_activities[0].kind == ActivityKind.CODING
    assert all_activities[0].estimated_minutes == 70
    assert all_activities[0].description == "Build auth system"


# ------------------------------------------------------------------
# Enhanced browser interaction tests
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_browser_dismisses_cookies(orchestrator):
    """_execute_browser should dismiss cookie banners after searching."""
    activity = Activity(
        ActivityKind.BROWSER, "Research JWT", 10,
        [], [], ["jwt middleware"], [],
    )
    orchestrator._browser_ctrl = AsyncMock()
    orchestrator._browser_ctrl.health_check = AsyncMock(return_value=True)
    orchestrator._behavior = AsyncMock()
    orchestrator._window_mgr = AsyncMock()
    orchestrator._activity_monitor = MagicMock()

    with patch("work4me.core.orchestrator.asyncio.sleep", new_callable=AsyncMock):
        await orchestrator._execute_browser(activity)

    orchestrator._browser_ctrl.dismiss_cookie_banner.assert_called()


@pytest.mark.asyncio
async def test_execute_browser_handles_captcha(orchestrator):
    """_execute_browser should check for CAPTCHAs after searching."""
    activity = Activity(
        ActivityKind.BROWSER, "Research JWT", 10,
        [], [], ["jwt middleware"], [],
    )
    orchestrator._browser_ctrl = AsyncMock()
    orchestrator._browser_ctrl.health_check = AsyncMock(return_value=True)
    orchestrator._behavior = AsyncMock()
    orchestrator._window_mgr = AsyncMock()
    orchestrator._activity_monitor = MagicMock()

    with patch("work4me.core.orchestrator.asyncio.sleep", new_callable=AsyncMock):
        await orchestrator._execute_browser(activity)

    orchestrator._browser_ctrl.handle_captcha.assert_called()


@pytest.mark.asyncio
async def test_execute_browser_clicks_results(orchestrator):
    """_execute_browser should try to click search result headings."""
    activity = Activity(
        ActivityKind.BROWSER, "Research JWT", 10,
        [], [], ["jwt middleware"], [],
    )
    orchestrator._browser_ctrl = AsyncMock()
    orchestrator._browser_ctrl.health_check = AsyncMock(return_value=True)
    orchestrator._behavior = AsyncMock()
    orchestrator._window_mgr = AsyncMock()
    orchestrator._activity_monitor = MagicMock()

    with patch("work4me.core.orchestrator.asyncio.sleep", new_callable=AsyncMock):
        await orchestrator._execute_browser(activity)

    # Should attempt to click an h3 heading (search result)
    orchestrator._browser_ctrl.click.assert_called()


@pytest.mark.asyncio
async def test_thinking_without_queries_does_idle_think(orchestrator):
    """THINKING with empty search_queries should idle think, not search."""
    activity = Activity(
        ActivityKind.THINKING, "Review the codebase structure and identify patterns", 5,
        [], [], [], [],
    )
    orchestrator._browser_ctrl = AsyncMock()
    orchestrator._browser_ctrl.health_check = AsyncMock(return_value=True)
    orchestrator._behavior = AsyncMock()
    orchestrator._activity_monitor = MagicMock()

    await orchestrator._execute_thinking(activity)

    # Browser search should NOT be called — no queries provided
    orchestrator._browser_ctrl.search.assert_not_called()
    # Should have done idle think instead
    orchestrator._behavior.idle_think.assert_called_once()


@pytest.mark.asyncio
async def test_thinking_with_queries_uses_browser(orchestrator):
    """THINKING with search_queries should use the browser."""
    activity = Activity(
        ActivityKind.THINKING, "Research async patterns", 5,
        [], [], ["python asyncio patterns"], [],
    )
    orchestrator._browser_ctrl = AsyncMock()
    orchestrator._browser_ctrl.health_check = AsyncMock(return_value=True)
    orchestrator._behavior = AsyncMock()
    orchestrator._window_mgr = AsyncMock()
    orchestrator._activity_monitor = MagicMock()

    with patch("work4me.core.orchestrator.asyncio.sleep", new_callable=AsyncMock):
        await orchestrator._execute_thinking(activity)

    orchestrator._browser_ctrl.search.assert_called_once_with("python asyncio patterns")


def test_generate_research_queries_removed(orchestrator):
    """_generate_research_queries should no longer exist."""
    assert not hasattr(orchestrator, "_generate_research_queries")


@pytest.mark.asyncio
async def test_research_with_browser_clicks_and_navigates_back(orchestrator):
    """_research_with_browser should click results and go back."""
    orchestrator._browser_ctrl = AsyncMock()
    orchestrator._behavior = AsyncMock()
    orchestrator._window_mgr = AsyncMock()
    orchestrator._activity_monitor = MagicMock()

    with patch("work4me.core.orchestrator.asyncio.sleep", new_callable=AsyncMock):
        await orchestrator._research_with_browser(["test query"], total_seconds=30.0)

    orchestrator._browser_ctrl.dismiss_cookie_banner.assert_called()
    orchestrator._browser_ctrl.handle_captcha.assert_called()
    orchestrator._browser_ctrl.click.assert_called()
    orchestrator._browser_ctrl.go_back.assert_called()


@pytest.mark.asyncio
async def test_research_with_browser_skips_timed_out_query(orchestrator):
    """_research_with_browser should skip queries that exceed time_per_query."""
    orchestrator._browser_ctrl = AsyncMock()
    orchestrator._behavior = AsyncMock()
    orchestrator._window_mgr = AsyncMock()
    orchestrator._activity_monitor = MagicMock()

    # Make the helper hang indefinitely on the first query
    call_count = 0

    async def slow_then_fast(query):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            await asyncio.sleep(999)  # Will be cancelled by wait_for
        # Second call completes instantly

    orchestrator._research_single_query = AsyncMock(side_effect=slow_then_fast)

    # 2 queries, 2 seconds total → 1 second per query
    await orchestrator._research_with_browser(
        ["slow query", "fast query"], total_seconds=2.0,
    )

    # Both queries should have been attempted
    assert orchestrator._research_single_query.call_count == 2


@pytest.mark.asyncio
async def test_research_with_browser_continues_after_timeout(orchestrator):
    """After a query times out, subsequent queries should still execute."""
    orchestrator._browser_ctrl = AsyncMock()
    orchestrator._behavior = AsyncMock()
    orchestrator._window_mgr = AsyncMock()
    orchestrator._activity_monitor = MagicMock()

    executed_queries = []

    async def track_query(query):
        executed_queries.append(query)
        if query == "slow":
            await asyncio.sleep(999)

    orchestrator._research_single_query = AsyncMock(side_effect=track_query)

    await orchestrator._research_with_browser(
        ["slow", "fast1", "fast2"], total_seconds=3.0,
    )

    # All three should be attempted, even though "slow" timed out
    assert "slow" in executed_queries
    assert "fast1" in executed_queries
    assert "fast2" in executed_queries


# ------------------------------------------------------------------
# Sidebar: permission configuration, zero-change skip, non-fatal failure
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sidebar_skips_diff_review_on_zero_changes():
    """When Claude produces 0 file changes, diff review should be skipped."""
    config = Config(mode="sidebar")
    orch = Orchestrator(config)
    activity = Activity(
        ActivityKind.CODING, "Write auth", 20,
        ["src/auth.ts"], [], [], [],
    )
    orch._vscode = AsyncMock()
    orch._vscode.check_claude_extension = AsyncMock(return_value={"installed": True, "active": True})
    orch._vscode.configure_claude_permissions = AsyncMock(return_value={"configured": True, "mode": "acceptEdits"})
    orch._vscode.open_claude_sidebar = AsyncMock(return_value={
        "opened": "claude-sidebar", "extensionActive": True, "extensionVersion": "2.1.49",
    })
    orch._vscode.send_claude_prompt = AsyncMock(return_value={"prompted": True, "length": 42})
    orch._vscode.submit_claude_prompt = AsyncMock(return_value={"submitted": True})
    orch._vscode.is_claude_busy = AsyncMock(return_value=False)
    orch._vscode.stop_claude_watch = AsyncMock(return_value={"totalChanges": 0})
    orch._behavior = AsyncMock()
    orch._window_mgr = AsyncMock()
    orch._activity_monitor = MagicMock()
    orch.snapshot.working_dir = "/tmp"

    await orch._execute_coding_sidebar(activity, "/tmp")

    # accept_diff should NOT be called when totalChanges is 0
    orch._vscode.accept_diff.assert_not_called()
    orch._vscode.reject_diff.assert_not_called()


@pytest.mark.asyncio
async def test_sidebar_configures_permissions():
    """configure_claude_permissions('acceptEdits') should be called before open_claude_sidebar."""
    config = Config(mode="sidebar")
    orch = Orchestrator(config)
    activity = Activity(
        ActivityKind.CODING, "Write auth", 20,
        ["src/auth.ts"], [], [], [],
    )
    call_order = []
    orch._vscode = AsyncMock()
    orch._vscode.check_claude_extension = AsyncMock(return_value={"installed": True, "active": True})
    orch._vscode.configure_claude_permissions = AsyncMock(
        return_value={"configured": True, "mode": "acceptEdits"},
        side_effect=lambda *a, **kw: call_order.append("configure_permissions"),
    )
    orch._vscode.open_claude_sidebar = AsyncMock(
        return_value={"opened": "claude-sidebar", "extensionActive": True, "extensionVersion": "2.1.49"},
        side_effect=lambda *a, **kw: call_order.append("open_sidebar"),
    )
    orch._vscode.send_claude_prompt = AsyncMock(return_value={"prompted": True, "length": 42})
    orch._vscode.submit_claude_prompt = AsyncMock(return_value={"submitted": True})
    orch._vscode.is_claude_busy = AsyncMock(return_value=False)
    orch._vscode.stop_claude_watch = AsyncMock(return_value={"totalChanges": 0})
    orch._behavior = AsyncMock()
    orch._window_mgr = AsyncMock()
    orch._activity_monitor = MagicMock()
    orch.snapshot.working_dir = "/tmp"

    await orch._execute_coding_sidebar(activity, "/tmp")

    orch._vscode.configure_claude_permissions.assert_called_once_with("acceptEdits")
    # Permissions must be configured BEFORE opening sidebar
    assert call_order.index("configure_permissions") < call_order.index("open_sidebar")


@pytest.mark.asyncio
async def test_sidebar_permission_config_failure_nonfatal():
    """If configure_claude_permissions raises, sidebar should still proceed."""
    config = Config(mode="sidebar")
    orch = Orchestrator(config)
    activity = Activity(
        ActivityKind.CODING, "Write auth", 20,
        ["src/auth.ts"], [], [], [],
    )
    orch._vscode = AsyncMock()
    orch._vscode.check_claude_extension = AsyncMock(return_value={"installed": True, "active": True})
    orch._vscode.configure_claude_permissions = AsyncMock(side_effect=RuntimeError("Setting not found"))
    orch._vscode.open_claude_sidebar = AsyncMock(return_value={
        "opened": "claude-sidebar", "extensionActive": True, "extensionVersion": "2.1.49",
    })
    orch._vscode.send_claude_prompt = AsyncMock(return_value={"prompted": True, "length": 42})
    orch._vscode.submit_claude_prompt = AsyncMock(return_value={"submitted": True})
    orch._vscode.is_claude_busy = AsyncMock(return_value=False)
    orch._vscode.stop_claude_watch = AsyncMock(return_value={"totalChanges": 0})
    orch._behavior = AsyncMock()
    orch._window_mgr = AsyncMock()
    orch._activity_monitor = MagicMock()
    orch.snapshot.working_dir = "/tmp"

    # Should NOT raise — permission config failure is non-fatal
    await orch._execute_coding_sidebar(activity, "/tmp")

    # Sidebar should still have opened despite permission config failure
    orch._vscode.open_claude_sidebar.assert_called_once()
