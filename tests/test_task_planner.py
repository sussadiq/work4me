# tests/test_task_planner.py
import json
import pytest
from unittest.mock import AsyncMock, patch
from work4me.planning.task_planner import TaskPlanner, Activity, ActivityKind, TaskPlan
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

    with patch.object(planner._claude, "execute", new_callable=AsyncMock, return_value=mock_result):
        plan = await planner.decompose("Build JWT auth", time_budget_hours=4, working_dir="/tmp")

    assert len(plan.activities) == 2
    assert plan.activities[0].kind == ActivityKind.CODING
    assert plan.activities[1].dependencies == ["0"]
