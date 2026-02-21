# tests/test_micro_pause.py
"""Tests for micro_pause behavior in the BehaviorEngine."""

import pytest
from unittest.mock import patch, AsyncMock
from work4me.behavior.engine import BehaviorEngine
from work4me.config import Config, MicroPauseConfig


@pytest.mark.asyncio
async def test_micro_pause_uses_config_defaults():
    """micro_pause() should use MicroPauseConfig bounds."""
    config = Config(micro_pause=MicroPauseConfig(min_seconds=15.0, max_seconds=60.0))
    engine = BehaviorEngine(config)

    durations = []
    original_sleep = None

    async def mock_sleep(d):
        durations.append(d)

    with patch("asyncio.sleep", side_effect=mock_sleep):
        await engine.micro_pause()

    total = sum(durations)
    # Total duration (before speed) should be roughly within config bounds
    # (speed_multiplier=1.0 by default, so applied durations == raw durations)
    assert total >= 15.0 * 0.8  # Allow some margin for interval math
    assert total <= 60.0 * 1.5


@pytest.mark.asyncio
async def test_micro_pause_custom_bounds():
    """micro_pause() should respect explicit min/max overrides."""
    config = Config()
    engine = BehaviorEngine(config)

    durations = []

    async def mock_sleep(d):
        durations.append(d)

    with patch("asyncio.sleep", side_effect=mock_sleep):
        await engine.micro_pause(min_sec=5.0, max_sec=10.0)

    total = sum(durations)
    assert total >= 4.0  # Slightly below min due to interval slicing
    assert total <= 15.0


@pytest.mark.asyncio
async def test_micro_pause_records_mouse_micro_events():
    """micro_pause() should record mouse_micro events."""
    config = Config(micro_pause=MicroPauseConfig(min_seconds=20.0, max_seconds=25.0))
    engine = BehaviorEngine(config)

    with patch("asyncio.sleep", new_callable=AsyncMock):
        await engine.micro_pause()

    events = engine.get_recent_events(window_seconds=600)
    mouse_events = [e for e in events if e[1] == "mouse_micro"]
    assert len(mouse_events) >= 1


@pytest.mark.asyncio
async def test_micro_pause_applies_speed_multiplier():
    """micro_pause() should scale sleep by speed_multiplier."""
    config = Config(micro_pause=MicroPauseConfig(min_seconds=20.0, max_seconds=20.0))
    engine = BehaviorEngine(config)
    engine.speed_multiplier = 0.5  # 2x faster

    durations = []

    async def mock_sleep(d):
        durations.append(d)

    with patch("asyncio.sleep", side_effect=mock_sleep):
        await engine.micro_pause()

    total = sum(durations)
    # With 0.5x multiplier, total should be roughly half the raw duration (~10s)
    assert total <= 15.0


@pytest.mark.asyncio
async def test_take_break_delegates_to_micro_pause():
    """take_break() should delegate to micro_pause for backward compat."""
    config = Config()
    engine = BehaviorEngine(config)

    durations = []

    async def mock_sleep(d):
        durations.append(d)

    with patch("asyncio.sleep", side_effect=mock_sleep):
        await engine.take_break(30.0)

    total = sum(durations)
    # Should be roughly in the range of 30*0.8 to 30*1.2
    assert total >= 20.0
    assert total <= 45.0
