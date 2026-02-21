"""State machine for the Work4Me agent."""

from __future__ import annotations

import json
import logging
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class State(str, Enum):
    IDLE = "IDLE"
    INITIALIZING = "INITIALIZING"
    PLANNING = "PLANNING"
    WORKING = "WORKING"
    ON_BREAK = "ON_BREAK"
    PAUSED = "PAUSED"
    WRAPPING_UP = "WRAPPING_UP"
    COMPLETED = "COMPLETED"
    INTERRUPTED = "INTERRUPTED"
    ERROR = "ERROR"


# Valid transitions: {current_state: {trigger: next_state}}
TRANSITIONS: dict[State, dict[str, State]] = {
    State.IDLE: {
        "start_task": State.INITIALIZING,
    },
    State.INITIALIZING: {
        "setup_complete": State.PLANNING,
        "setup_failed": State.ERROR,
    },
    State.PLANNING: {
        "plan_ready": State.WORKING,
        "plan_failed": State.ERROR,
        "user_pause": State.PAUSED,
    },
    State.WORKING: {
        "break_scheduled": State.ON_BREAK,
        "time_almost_up": State.WRAPPING_UP,
        "task_complete_early": State.WRAPPING_UP,
        "user_pause": State.PAUSED,
        "user_interrupt": State.INTERRUPTED,
        "error": State.ERROR,
        "replan_needed": State.PLANNING,
    },
    State.ON_BREAK: {
        "break_over": State.WORKING,
        "user_pause": State.PAUSED,
        "time_almost_up": State.WRAPPING_UP,
    },
    State.PAUSED: {
        "user_resume": State.WORKING,
        "user_stop": State.WRAPPING_UP,
    },
    State.WRAPPING_UP: {
        "wrapped_up": State.COMPLETED,
        "error": State.ERROR,
    },
    State.INTERRUPTED: {
        "user_gone": State.WORKING,
        "user_pause": State.PAUSED,
        "timeout": State.PAUSED,
    },
    State.COMPLETED: {
        "start_task": State.INITIALIZING,
    },
    State.ERROR: {
        "retry": State.INITIALIZING,
        "user_fix": State.PLANNING,
    },
}


class StateMachine:
    """Manages state transitions with validation."""

    def __init__(self) -> None:
        self.state = State.IDLE

    def transition(self, trigger: str) -> State:
        """Attempt a state transition.

        Args:
            trigger: The event/trigger name.

        Returns:
            The new state.

        Raises:
            ValueError: If the transition is not valid from the current state.
        """
        valid = TRANSITIONS.get(self.state, {})
        if trigger not in valid:
            raise ValueError(
                f"Invalid transition '{trigger}' from state {self.state}. "
                f"Valid triggers: {list(valid.keys())}"
            )

        old_state = self.state
        self.state = valid[trigger]
        logger.info("State: %s -> %s (trigger: %s)", old_state, self.state, trigger)
        return self.state

    def can_transition(self, trigger: str) -> bool:
        """Check if a transition is valid without executing it."""
        return trigger in TRANSITIONS.get(self.state, {})


class StateSnapshot:
    """Serializable snapshot of agent state for persistence."""

    def __init__(self) -> None:
        self.version: int = 1
        self.state: str = State.IDLE.value
        self.task_description: str = ""
        self.time_budget_minutes: int = 0
        self.started_at: str = ""
        self.elapsed_minutes: float = 0
        self.current_activity_index: int = 0
        self.completed_activities: list[int] = []
        self.skipped_activities: list[int] = []
        self.claude_session_id: str = ""
        self.working_dir: str = ""

    def save(self, path: Path) -> None:
        """Atomically save state to disk."""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        data = {
            "version": self.version,
            "state": self.state,
            "task_description": self.task_description,
            "time_budget_minutes": self.time_budget_minutes,
            "started_at": self.started_at,
            "elapsed_minutes": self.elapsed_minutes,
            "current_activity_index": self.current_activity_index,
            "completed_activities": self.completed_activities,
            "skipped_activities": self.skipped_activities,
            "claude_session_id": self.claude_session_id,
            "working_dir": self.working_dir,
        }
        tmp.write_text(json.dumps(data, indent=2))
        tmp.rename(path)  # Atomic on same filesystem

    @classmethod
    def load(cls, path: Path) -> StateSnapshot:
        """Load state from disk."""
        data = json.loads(path.read_text())
        snap = cls()
        snap.version = data.get("version", 1)
        snap.state = data.get("state", State.IDLE.value)
        snap.task_description = data.get("task_description", "")
        snap.time_budget_minutes = data.get("time_budget_minutes", 0)
        snap.started_at = data.get("started_at", "")
        snap.elapsed_minutes = data.get("elapsed_minutes", 0)
        snap.current_activity_index = data.get("current_activity_index", 0)
        snap.completed_activities = data.get("completed_activities", [])
        snap.skipped_activities = data.get("skipped_activities", [])
        snap.claude_session_id = data.get("claude_session_id", "")
        snap.working_dir = data.get("working_dir", "")
        return snap
