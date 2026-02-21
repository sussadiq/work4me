"""Tests for BehaviorEngine ↔ ActivityMonitor wiring."""
import pytest
from work4me.behavior.engine import BehaviorEngine
from work4me.behavior.activity_monitor import ActivityMonitor, BehaviorAdjustment
from work4me.config import Config


def test_engine_forwards_events_to_monitor():
    config = Config()
    engine = BehaviorEngine(config)
    monitor = ActivityMonitor(config.activity)
    engine.set_activity_monitor(monitor)
    engine._record_event("keyboard")
    assert len(monitor._events) == 1
    assert monitor._events[0][0] == "keyboard"


def test_engine_without_monitor_still_works():
    config = Config()
    engine = BehaviorEngine(config)
    engine._record_event("keyboard")  # Should not raise
    assert len(engine._activity_events) == 1


def test_engine_speed_multiplier_default():
    config = Config()
    engine = BehaviorEngine(config)
    assert engine.speed_multiplier == 1.0


def test_engine_apply_adjustment_slow_down():
    config = Config()
    engine = BehaviorEngine(config)
    engine.apply_adjustment(BehaviorAdjustment.SLOW_DOWN)
    assert engine.speed_multiplier > 1.0


def test_engine_apply_adjustment_speed_up():
    config = Config()
    engine = BehaviorEngine(config)
    engine.speed_multiplier = 2.0
    engine.apply_adjustment(BehaviorAdjustment.SPEED_UP)
    assert engine.speed_multiplier < 2.0


def test_speed_multiplier_clamps():
    config = Config()
    engine = BehaviorEngine(config)
    for _ in range(20):
        engine.apply_adjustment(BehaviorAdjustment.SLOW_DOWN)
    assert engine.speed_multiplier <= 3.0
    for _ in range(40):
        engine.apply_adjustment(BehaviorAdjustment.SPEED_UP)
    assert engine.speed_multiplier >= 0.5


def test_apply_speed_default():
    config = Config()
    engine = BehaviorEngine(config)
    assert engine._apply_speed(1.0) == pytest.approx(1.0, abs=0.001)


def test_apply_speed_slow():
    config = Config()
    engine = BehaviorEngine(config)
    engine.speed_multiplier = 2.0
    assert engine._apply_speed(1.0) == pytest.approx(2.0, abs=0.001)


def test_apply_speed_fast():
    config = Config()
    engine = BehaviorEngine(config)
    engine.speed_multiplier = 0.5
    assert engine._apply_speed(1.0) == pytest.approx(0.5, abs=0.001)


def test_engine_apply_adjustment_add_idle():
    config = Config()
    engine = BehaviorEngine(config)
    original = engine.speed_multiplier
    engine.apply_adjustment(BehaviorAdjustment.ADD_IDLE)
    assert engine.speed_multiplier > original
    assert engine.speed_multiplier == pytest.approx(1.15, abs=0.01)


def test_engine_apply_adjustment_add_variation():
    config = Config()
    engine = BehaviorEngine(config)
    engine.apply_adjustment(BehaviorAdjustment.ADD_VARIATION)
    # Should be nudged somewhere within bounds
    assert 0.5 <= engine.speed_multiplier <= 3.0
