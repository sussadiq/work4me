"""Tests for crash recovery."""
import pytest
from pathlib import Path
from work4me.core.state import StateSnapshot, State


def test_is_resumable_working():
    snap = StateSnapshot()
    snap.state = State.WORKING.value
    snap.task_description = "Test task"
    snap.current_activity_index = 2
    assert snap.is_resumable()


def test_is_resumable_completed():
    snap = StateSnapshot()
    snap.state = State.COMPLETED.value
    assert not snap.is_resumable()


def test_is_resumable_idle():
    snap = StateSnapshot()
    snap.state = State.IDLE.value
    assert not snap.is_resumable()


def test_is_resumable_planning():
    snap = StateSnapshot()
    snap.state = State.PLANNING.value
    snap.task_description = "Test task"
    assert snap.is_resumable()


def test_is_resumable_no_task():
    snap = StateSnapshot()
    snap.state = State.WORKING.value
    snap.task_description = ""
    assert not snap.is_resumable()


def test_round_trip_save_load(tmp_path):
    snap = StateSnapshot()
    snap.state = State.WORKING.value
    snap.task_description = "Build feature"
    snap.current_activity_index = 3
    snap.working_dir = "/tmp/project"
    path = tmp_path / "state.json"
    snap.save(path)

    loaded = StateSnapshot.load(path)
    assert loaded.state == State.WORKING.value
    assert loaded.task_description == "Build feature"
    assert loaded.current_activity_index == 3
    assert loaded.working_dir == "/tmp/project"
