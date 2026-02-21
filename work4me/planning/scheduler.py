"""Session scheduling with human-like time distribution."""

import logging
import random
from dataclasses import dataclass, field

from work4me.config import SessionConfig
from work4me.planning.task_planner import Activity, TaskPlan

logger = logging.getLogger(__name__)


@dataclass
class WorkSession:
    activities: list[Activity]
    duration_minutes: float
    break_after_minutes: float
    session_number: int


@dataclass
class Schedule:
    sessions: list[WorkSession]
    total_budget_minutes: float


class Scheduler:
    """Maps activities onto work sessions with breaks."""

    def __init__(self, config: SessionConfig):
        self._config = config
        self._rng = random.Random()

    def build_schedule(self, plan: TaskPlan, total_minutes: float) -> Schedule:
        """Create a schedule of work sessions from a task plan."""
        session_durations = self._generate_session_durations(total_minutes)
        num_sessions = len(session_durations)

        ordered = self._topological_sort(plan.activities)

        sessions: list[WorkSession] = []
        activity_idx = 0

        for i, (dur, brk) in enumerate(session_durations):
            session_activities: list[Activity] = []
            session_time = 0.0

            while activity_idx < len(ordered) and session_time + ordered[activity_idx].estimated_minutes <= dur * 1.2:
                session_activities.append(ordered[activity_idx])
                session_time += ordered[activity_idx].estimated_minutes
                activity_idx += 1

            if i == num_sessions - 1:
                while activity_idx < len(ordered):
                    session_activities.append(ordered[activity_idx])
                    session_time += ordered[activity_idx].estimated_minutes
                    activity_idx += 1

            sessions.append(WorkSession(
                activities=session_activities,
                duration_minutes=max(dur, session_time),
                break_after_minutes=brk,
                session_number=i + 1,
            ))

        logger.info("Scheduled %d activities across %d sessions (%.0f min total)",
                     len(plan.activities), len(sessions), total_minutes)
        return Schedule(sessions=sessions, total_budget_minutes=total_minutes)

    def _generate_session_durations(self, total_minutes: float) -> list[tuple[float, float]]:
        """Generate a single continuous session with no formal break."""
        return [(total_minutes, 0.0)]

    def _topological_sort(self, activities: list[Activity]) -> list[Activity]:
        """Sort activities respecting dependencies."""
        n = len(activities)
        visited = [False] * n
        result: list[Activity] = []

        def visit(i: int) -> None:
            if visited[i]:
                return
            visited[i] = True
            for dep_str in activities[i].dependencies:
                dep = int(dep_str)
                if 0 <= dep < n:
                    visit(dep)
            result.append(activities[i])

        for i in range(n):
            visit(i)
        return result
