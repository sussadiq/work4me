# tests/test_activity_monitor.py
import time
import pytest
from work4me.behavior.activity_monitor import ActivityMonitor, ActivityHealth, BehaviorAdjustment
from work4me.config import ActivityConfig

@pytest.fixture
def monitor():
    return ActivityMonitor(ActivityConfig())

def test_empty_monitor_ratio_is_zero(monitor):
    assert monitor.activity_ratio() == 0.0

def test_record_events_increases_ratio(monitor):
    now = time.time()
    for i in range(30):
        monitor.record_event("keyboard", now - 600 + i * 10)
    ratio = monitor.activity_ratio(window_seconds=600)
    assert 0.0 < ratio < 1.0

def test_variance_requires_data(monitor):
    assert monitor.variance() == 0.0

def test_is_within_bounds_empty(monitor):
    health = monitor.is_within_bounds()
    assert health.activity_ok  # no activity is "ok" (not flagged as too high)
    assert health.variance_ok

def test_keyboard_mouse_balance(monitor):
    now = time.time()
    for i in range(50):
        monitor.record_event("keyboard", now - 3000 + i * 30)
    # All keyboard, no mouse
    kb, mouse = monitor.keyboard_mouse_balance()
    assert kb > 0.9
    assert mouse < 0.1

def test_recommended_adjustment_too_high(monitor):
    now = time.time()
    # Simulate very high activity
    for i in range(580):
        monitor.record_event("keyboard", now - 600 + i)
    adj = monitor.recommended_adjustment()
    assert adj == BehaviorAdjustment.SLOW_DOWN

def test_recommended_adjustment_too_low(monitor):
    now = time.time()
    # Simulate very low activity
    for i in range(5):
        monitor.record_event("keyboard", now - 600 + i * 100)
    adj = monitor.recommended_adjustment()
    assert adj == BehaviorAdjustment.SPEED_UP


def test_recommended_adjustment_uses_config_max():
    """Custom config with lower target_ratio_max should trigger SLOW_DOWN earlier."""
    config = ActivityConfig(target_ratio_max=0.50)
    monitor = ActivityMonitor(config)
    now = time.time()
    # Activity ratio ~0.60 — above 0.50 + 0.10 = 0.60 threshold
    for i in range(370):
        monitor.record_event("keyboard", now - 600 + i)
    adj = monitor.recommended_adjustment()
    assert adj == BehaviorAdjustment.SLOW_DOWN


def test_recommended_adjustment_uses_config_min():
    """Custom config with higher target_ratio_min should trigger SPEED_UP earlier."""
    config = ActivityConfig(target_ratio_min=0.50)
    monitor = ActivityMonitor(config)
    now = time.time()
    # Activity ratio ~0.35 — below 0.50 - 0.10 = 0.40 threshold
    for i in range(3):
        monitor.record_event("keyboard", now - 600 + i * 200)
    adj = monitor.recommended_adjustment()
    assert adj == BehaviorAdjustment.SPEED_UP
