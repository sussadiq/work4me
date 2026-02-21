# tests/test_state.py
"""Tests for the state machine after ON_BREAK removal."""

import pytest
from work4me.core.state import State, StateMachine, TRANSITIONS, StateSnapshot


def test_on_break_not_in_state_enum():
    """ON_BREAK should not exist in the State enum."""
    state_names = [s.value for s in State]
    assert "ON_BREAK" not in state_names


def test_break_scheduled_trigger_is_invalid():
    """break_scheduled trigger should not be valid from WORKING state."""
    sm = StateMachine()
    sm.state = State.WORKING
    assert not sm.can_transition("break_scheduled")


def test_break_scheduled_raises_value_error():
    """break_scheduled trigger from WORKING should raise ValueError."""
    sm = StateMachine()
    sm.state = State.WORKING
    with pytest.raises(ValueError, match="Invalid transition 'break_scheduled'"):
        sm.transition("break_scheduled")


def test_working_valid_transitions():
    """WORKING state should have the expected transitions (no break)."""
    valid_triggers = set(TRANSITIONS[State.WORKING].keys())
    assert "break_scheduled" not in valid_triggers
    assert "time_almost_up" in valid_triggers
    assert "task_complete_early" in valid_triggers
    assert "user_pause" in valid_triggers
    assert "error" in valid_triggers


def test_no_on_break_in_transitions():
    """No state in TRANSITIONS should reference ON_BREAK."""
    for state, triggers in TRANSITIONS.items():
        for trigger, target in triggers.items():
            assert "ON_BREAK" not in target.value, (
                f"ON_BREAK found as target: {state} --{trigger}--> {target}"
            )


def test_is_resumable_without_on_break():
    """is_resumable should work without ON_BREAK."""
    snap = StateSnapshot()
    snap.task_description = "test"

    snap.state = "WORKING"
    assert snap.is_resumable() is True

    snap.state = "PLANNING"
    assert snap.is_resumable() is True

    snap.state = "PAUSED"
    assert snap.is_resumable() is True

    snap.state = "ON_BREAK"
    assert snap.is_resumable() is False

    snap.state = "COMPLETED"
    assert snap.is_resumable() is False
