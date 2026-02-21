# tests/test_orchestrator.py
"""Tests for the revised dual-mode orchestrator."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
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
