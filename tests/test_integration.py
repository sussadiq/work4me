"""Integration test: verify full orchestration flow with mocked externals."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from work4me.config import Config
from work4me.core.orchestrator import Orchestrator
from work4me.core.state import StateSnapshot, State
from work4me.planning.task_planner import Activity, ActivityKind, TaskPlan
from work4me.planning.scheduler import Schedule, WorkSession


@pytest.fixture
def mock_schedule():
    activities = [
        Activity(ActivityKind.BROWSER, "Research", 5, [], [], ["test query"], []),
        Activity(ActivityKind.CODING, "Write code", 10, ["test.py"], [], [], ["0"]),
        Activity(ActivityKind.TERMINAL, "Run tests", 3, [], ["pytest"], [], ["1"]),
    ]
    session = WorkSession(
        activities=activities,
        duration_minutes=20,
        break_after_minutes=0,
        session_number=1,
    )
    return Schedule(sessions=[session], total_budget_minutes=30)


@pytest.mark.asyncio
async def test_full_flow_mode_a(mock_schedule):
    config = Config(mode="manual")
    orch = Orchestrator(config)

    # Mock all external controllers
    orch._vscode = AsyncMock()
    orch._browser_ctrl = AsyncMock()
    behavior_mock = AsyncMock()
    behavior_mock.apply_adjustment = MagicMock()  # sync method
    orch._behavior = behavior_mock
    orch._claude = AsyncMock()
    orch._claude.execute = AsyncMock(return_value=MagicMock(
        actions=[], raw_text="done", exit_code=0, error=None, session_id="test"
    ))
    orch._planner = AsyncMock()
    orch._planner.decompose = AsyncMock(return_value=TaskPlan(
        "Test task", mock_schedule.sessions[0].activities
    ))
    orch._scheduler = MagicMock()
    orch._scheduler.build_schedule = MagicMock(return_value=mock_schedule)
    orch._activity_monitor = MagicMock()
    orch._activity_monitor.recommended_adjustment = MagicMock(
        return_value=MagicMock(value="none")
    )
    orch._activity_monitor.is_within_bounds = MagicMock(return_value=MagicMock(
        activity_ok=True, variance_ok=True, balance_ok=True
    ))
    orch._activity_monitor.record_event = MagicMock()

    # Mock initialization and cleanup
    orch._initialize = AsyncMock()
    orch._wrap_up = AsyncMock()
    orch._cleanup = AsyncMock()

    await orch.run("Test task", time_budget_minutes=30, working_dir="/tmp")

    orch._initialize.assert_called_once()
    orch._planner.decompose.assert_called_once()
    orch._wrap_up.assert_called_once()
    orch._cleanup.assert_called_once()


@pytest.mark.asyncio
async def test_full_flow_mode_b(mock_schedule):
    config = Config(mode="ai-assisted")
    orch = Orchestrator(config)

    # Mock all external controllers
    orch._vscode = AsyncMock()
    orch._browser_ctrl = AsyncMock()
    behavior_mock = AsyncMock()
    behavior_mock.apply_adjustment = MagicMock()  # sync method
    orch._behavior = behavior_mock
    orch._claude = AsyncMock()
    orch._planner = AsyncMock()
    orch._planner.decompose = AsyncMock(return_value=TaskPlan(
        "Test task", mock_schedule.sessions[0].activities
    ))
    orch._scheduler = MagicMock()
    orch._scheduler.build_schedule = MagicMock(return_value=mock_schedule)
    orch._activity_monitor = MagicMock()
    orch._activity_monitor.recommended_adjustment = MagicMock(
        return_value=MagicMock(value="none")
    )
    orch._activity_monitor.record_event = MagicMock()

    orch._initialize = AsyncMock()
    orch._wrap_up = AsyncMock()
    orch._cleanup = AsyncMock()

    await orch.run("Test task", time_budget_minutes=30, working_dir="/tmp")

    orch._initialize.assert_called_once()
    # Mode B should use VS Code terminal, not headless Claude
    orch._vscode.show_terminal.assert_called()
    orch._cleanup.assert_called_once()


@pytest.mark.asyncio
async def test_engine_monitor_integration():
    """Verify engine events flow to monitor during orchestration."""
    config = Config(mode="manual")
    orch = Orchestrator(config)
    # Verify wiring happened in constructor
    assert orch._behavior._activity_monitor is orch._activity_monitor


@pytest.mark.asyncio
async def test_recovery_flow(tmp_path):
    """Verify crash recovery detects resumable state."""
    config = Config(mode="manual")
    orch = Orchestrator(config)

    # Simulate a crashed session
    snap = StateSnapshot()
    snap.state = State.WORKING.value
    snap.task_description = "Build feature"
    snap.current_activity_index = 2
    snap.save(tmp_path / "state.json")

    with patch.object(type(config), 'runtime_dir', new_callable=lambda: property(lambda self: tmp_path)):
        recovered = orch.check_for_recovery()
    assert recovered is not None
    assert recovered.current_activity_index == 2
