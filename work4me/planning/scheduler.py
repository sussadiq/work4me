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


# Session templates: (mean_duration, sigma, min, max)
SESSION_TEMPLATES = [
    (52, 5, 35, 75),
    (45, 5, 30, 60),
    (48, 5, 35, 65),
    (38, 5, 25, 50),
]

# Break templates: (mean, sigma, min, max)
BREAK_TEMPLATES = [
    (6.5, 1.5, 3, 12),
    (5.0, 1.5, 3, 8),
    (12.0, 2.0, 8, 18),
    (0, 0, 0, 0),  # no break after last session
]


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
        """Generate session durations from SessionConfig with Gaussian noise."""
        # Derive number of sessions from config, scaled to budget
        num_sessions = max(2, min(6, round(
            self._config.sessions_per_4_hours * (total_minutes / 240.0)
        )))
        scale = total_minutes / (num_sessions * self._config.duration_mean)
        results = []
        for i in range(num_sessions):
            # Per-session variation from config
            dur = self._rng.gauss(self._config.duration_mean, self._config.duration_sigma)
            dur = max(self._config.duration_mean * 0.5, min(self._config.duration_mean * 1.5, dur))
            dur *= scale

            # No break after last session
            if i == num_sessions - 1:
                brk = 0.0
            else:
                brk = self._rng.gauss(self._config.break_mean, self._config.break_sigma)
                brk = max(self._config.break_mean * 0.5, min(self._config.break_mean * 2.0, brk))
                brk *= scale

            results.append((dur, brk))
        return results

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
