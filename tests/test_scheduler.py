# tests/test_scheduler.py
import pytest
from work4me.planning.scheduler import Scheduler, Schedule, WorkSession
from work4me.planning.task_planner import Activity, ActivityKind, TaskPlan
from work4me.config import SessionConfig

@pytest.fixture
def activities():
    return [
        Activity(ActivityKind.BROWSER, "Research JWT", 10, [], [], ["jwt express middleware"], []),
        Activity(ActivityKind.READING, "Review project", 8, ["src/"], [], [], []),
        Activity(ActivityKind.CODING, "Write auth middleware", 20, ["src/auth.ts"], [], [], ["0", "1"]),
        Activity(ActivityKind.CODING, "Write auth routes", 15, ["src/routes/auth.ts"], [], [], ["2"]),
        Activity(ActivityKind.TERMINAL, "Install deps", 3, [], ["npm install jsonwebtoken"], [], []),
        Activity(ActivityKind.CODING, "Write tests", 15, ["tests/auth.test.ts"], [], [], ["2", "3"]),
        Activity(ActivityKind.TERMINAL, "Run tests", 10, [], ["npm test"], [], ["5"]),
        Activity(ActivityKind.TERMINAL, "Git commit", 3, [], ["git commit"], [], ["6"]),
    ]

@pytest.fixture
def plan(activities):
    return TaskPlan(task_description="Build JWT auth", activities=activities)

@pytest.fixture
def scheduler():
    return Scheduler(SessionConfig())

def test_build_schedule_creates_sessions(scheduler, plan):
    schedule = scheduler.build_schedule(plan, total_minutes=240)
    assert len(schedule.sessions) >= 2
    assert len(schedule.sessions) <= 5

def test_schedule_covers_all_activities(scheduler, plan):
    schedule = scheduler.build_schedule(plan, total_minutes=240)
    all_activities = []
    for session in schedule.sessions:
        all_activities.extend(session.activities)
    assert len(all_activities) == len(plan.activities)

def test_sessions_have_breaks(scheduler, plan):
    schedule = scheduler.build_schedule(plan, total_minutes=240)
    for session in schedule.sessions[:-1]:  # all but last
        assert session.break_after_minutes > 0

def test_schedule_respects_dependencies(scheduler, plan):
    schedule = scheduler.build_schedule(plan, total_minutes=240)
    seen_indices: set[int] = set()
    for session in schedule.sessions:
        for activity in session.activities:
            idx = plan.activities.index(activity)
            for dep in activity.dependencies:
                assert int(dep) in seen_indices, f"Activity {idx} depends on {dep} which hasn't been scheduled yet"
            seen_indices.add(idx)

def test_total_time_within_budget(scheduler, plan):
    schedule = scheduler.build_schedule(plan, total_minutes=240)
    total = sum(s.duration_minutes + s.break_after_minutes for s in schedule.sessions)
    assert total <= 320  # generous slack — schedule is approximate, not exact


def test_schedule_uses_session_config_values(plan):
    """Custom SessionConfig should affect session count and durations."""
    config = SessionConfig(duration_mean=30, duration_sigma=3, break_mean=5,
                           break_sigma=1, sessions_per_4_hours=6)
    scheduler = Scheduler(config)
    schedule = scheduler.build_schedule(plan, total_minutes=240)
    # With sessions_per_4_hours=6, expect ~6 sessions
    assert len(schedule.sessions) >= 4
    assert len(schedule.sessions) <= 6
