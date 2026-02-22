# tests/test_task_planner.py
import json
import pytest
from unittest.mock import AsyncMock, patch
from work4me.planning.task_planner import (
    TaskPlanner, Activity, ActivityKind, TaskPlan, DECOMPOSITION_PROMPT,
)
from work4me.config import ClaudeConfig

@pytest.fixture
def planner():
    return TaskPlanner(ClaudeConfig())

def test_activity_kind_values():
    assert ActivityKind.CODING.value == "CODING"
    assert ActivityKind.BROWSER.value == "BROWSER"
    assert ActivityKind.TERMINAL.value == "TERMINAL"
    assert ActivityKind.READING.value == "READING"
    assert ActivityKind.THINKING.value == "THINKING"

def test_activity_dataclass():
    a = Activity(
        kind=ActivityKind.CODING,
        description="Write auth middleware",
        estimated_minutes=20,
        files_involved=["src/auth.ts"],
        commands=["npm test"],
        search_queries=[],
        dependencies=[],
    )
    assert a.kind == ActivityKind.CODING
    assert a.estimated_minutes == 20

def test_task_plan_total_minutes():
    plan = TaskPlan(
        task_description="Build API",
        activities=[
            Activity(ActivityKind.CODING, "Write code", 30, [], [], [], []),
            Activity(ActivityKind.TERMINAL, "Run tests", 10, [], [], [], []),
        ],
    )
    assert plan.total_estimated_minutes == 40

@pytest.mark.asyncio
async def test_decompose_parses_claude_json(planner):
    fake_json = json.dumps([
        {
            "kind": "CODING",
            "description": "Implement auth",
            "estimated_minutes": 25,
            "files_involved": ["src/auth.ts"],
            "commands": [],
            "search_queries": [],
            "dependencies": [],
        },
        {
            "kind": "TERMINAL",
            "description": "Run tests",
            "estimated_minutes": 10,
            "files_involved": [],
            "commands": ["npm test"],
            "search_queries": [],
            "dependencies": ["0"],
        },
    ])
    mock_result = type("R", (), {"raw_text": fake_json, "exit_code": 0, "error": None, "actions": []})()

    with patch.object(planner._claude, "execute", new_callable=AsyncMock, return_value=mock_result) as mock_exec:
        plan = await planner.decompose("Build JWT auth", time_budget_hours=4, working_dir="/tmp")

    assert len(plan.activities) == 2
    assert plan.activities[0].kind == ActivityKind.CODING
    assert plan.activities[1].dependencies == ["0"]

    # Verify max_turns uses config default (no disallowed_tools)
    call_kwargs = mock_exec.call_args
    assert call_kwargs.kwargs["max_turns"] == 10
    assert "disallowed_tools" not in call_kwargs.kwargs


@pytest.mark.asyncio
async def test_decompose_retries_on_execute_error(planner):
    """decompose() should retry when Claude Code returns an error."""
    fake_json = json.dumps([
        {"kind": "CODING", "description": "Write code", "estimated_minutes": 20,
         "files_involved": [], "commands": [], "search_queries": [], "dependencies": []},
    ])
    error_result = type("R", (), {"raw_text": "", "exit_code": 1, "error": "stream failed", "actions": []})()
    ok_result = type("R", (), {"raw_text": fake_json, "exit_code": 0, "error": None, "actions": []})()

    call_count = 0
    async def flaky_execute(**kwargs):
        nonlocal call_count
        call_count += 1
        return error_result if call_count == 1 else ok_result

    with patch.object(planner._claude, "execute", side_effect=flaky_execute), \
         patch("work4me.planning.task_planner.asyncio.sleep", new_callable=AsyncMock):
        plan = await planner.decompose("Test task", time_budget_hours=1, working_dir="/tmp")

    assert call_count == 2
    assert len(plan.activities) == 1


@pytest.mark.asyncio
async def test_decompose_retries_on_parse_failure(planner):
    """decompose() should retry when _parse_plan raises ValueError."""
    bad_result = type("R", (), {"raw_text": "not json at all", "exit_code": 0, "error": None, "actions": []})()
    good_json = json.dumps([
        {"kind": "CODING", "description": "Write code", "estimated_minutes": 20,
         "files_involved": [], "commands": [], "search_queries": [], "dependencies": []},
    ])
    ok_result = type("R", (), {"raw_text": good_json, "exit_code": 0, "error": None, "actions": []})()

    call_count = 0
    async def flaky_execute(**kwargs):
        nonlocal call_count
        call_count += 1
        return bad_result if call_count == 1 else ok_result

    with patch.object(planner._claude, "execute", side_effect=flaky_execute), \
         patch("work4me.planning.task_planner.asyncio.sleep", new_callable=AsyncMock):
        plan = await planner.decompose("Test task", time_budget_hours=1, working_dir="/tmp")

    assert call_count == 2
    assert len(plan.activities) == 1


@pytest.mark.asyncio
async def test_decompose_raises_after_all_retries_exhausted(planner):
    """decompose() should raise RuntimeError after exhausting retries."""
    error_result = type("R", (), {"raw_text": "", "exit_code": 1, "error": "persistent error", "actions": []})()

    with patch.object(planner._claude, "execute", new_callable=AsyncMock, return_value=error_result), \
         patch("work4me.planning.task_planner.asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(RuntimeError, match="failed after 3 attempts"):
            await planner.decompose("Test task", time_budget_hours=1, working_dir="/tmp")


def test_decomposition_prompt_has_time_allocation_guidance():
    """DECOMPOSITION_PROMPT should instruct 80% CODING/TERMINAL, 20% research."""
    assert "80%" in DECOMPOSITION_PROMPT
    assert "CODING and TERMINAL" in DECOMPOSITION_PROMPT
    assert "BROWSER, READING, and THINKING" in DECOMPOSITION_PROMPT


def test_planner_uses_planning_model():
    """TaskPlanner should create its ClaudeCodeManager with the planning_model."""
    config = ClaudeConfig(model="opus", planning_model="haiku")
    planner = TaskPlanner(config)
    assert planner._claude.config.model == "haiku"


def test_planner_uses_default_planning_model():
    """TaskPlanner with default config should use sonnet for planning."""
    config = ClaudeConfig()
    planner = TaskPlanner(config)
    assert planner._claude.config.model == "sonnet"
    assert config.model == "sonnet"  # Original config unchanged
