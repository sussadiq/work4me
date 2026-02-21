"""Central behavior engine.

Every desktop interaction passes through this module to ensure
human-like timing characteristics. Coordinates typing, mouse,
idle patterns, and activity recording.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable

from work4me.behavior.activity_monitor import ActivityMonitor, BehaviorAdjustment
from work4me.behavior.typing import HumanTyper, TypedChar
from work4me.config import Config

logger = logging.getLogger(__name__)


class BehaviorEngine:
    """Coordinates all human-like behavior simulation."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.typer = HumanTyper(config.typing)
        self._activity_events: list[tuple[float, str]] = []
        self._activity_monitor: ActivityMonitor | None = None
        self.speed_multiplier: float = 1.0

    def set_activity_monitor(self, monitor: ActivityMonitor) -> None:
        self._activity_monitor = monitor

    def _apply_speed(self, delay: float) -> float:
        """Scale a delay by the current speed_multiplier."""
        return delay * self.speed_multiplier

    def apply_adjustment(self, adjustment: BehaviorAdjustment) -> None:
        if adjustment == BehaviorAdjustment.SLOW_DOWN:
            self.speed_multiplier = min(3.0, self.speed_multiplier * 1.3)
        elif adjustment == BehaviorAdjustment.SPEED_UP:
            self.speed_multiplier = max(0.5, self.speed_multiplier * 0.8)
        elif adjustment == BehaviorAdjustment.ADD_IDLE:
            self.speed_multiplier = min(3.0, self.speed_multiplier * 1.15)
        elif adjustment == BehaviorAdjustment.ADD_VARIATION:
            nudge = random.uniform(-0.15, 0.15)
            self.speed_multiplier = max(0.5, min(3.0, self.speed_multiplier + nudge))
        elif adjustment == BehaviorAdjustment.NONE:
            self.speed_multiplier += (1.0 - self.speed_multiplier) * 0.1

    async def type_text(
        self,
        text: str,
        send_char_fn: Callable[[str], Awaitable[None]],
        send_backspace_fn: Callable[[], Awaitable[None]] | None = None,
        *,
        is_code: bool = True,
    ) -> None:
        """Type text with human-like characteristics.

        Args:
            text: The text to type.
            send_char_fn: Async callable(char: str) to send a single character.
            send_backspace_fn: Async callable() to send a backspace. If None,
                errors are skipped.
            is_code: Whether this is code (slower) or prose (faster).
        """
        sequence = self.typer.generate_sequence(text, is_code=is_code)

        for typed_char in sequence:
            # Wait the computed delay
            if typed_char.delay_before > 0:
                await asyncio.sleep(self._apply_speed(typed_char.delay_before))

            if typed_char.is_error and send_backspace_fn is not None:
                # Type wrong character
                typo = self.typer.get_typo_char(typed_char.char)
                await send_char_fn(typo)
                self._record_event("keyboard")

                # Brief pause (noticing the error)
                await asyncio.sleep(self._apply_speed(random.uniform(0.2, 0.6)))

                # Backspace
                await send_backspace_fn()
                self._record_event("keyboard")

                # Brief pause before correction
                await asyncio.sleep(self._apply_speed(random.uniform(0.05, 0.15)))

            # Type the correct character
            await send_char_fn(typed_char.char)
            self._record_event("keyboard")

    async def type_command(
        self,
        command: str,
        send_char_fn: Callable[[str], Awaitable[None]],
        send_enter_fn: Callable[[], Awaitable[None]],
    ) -> None:
        """Type a terminal command with human-like timing, then press Enter.

        Commands are typed slightly faster than code (more muscle memory).
        No error injection for commands (too risky — wrong command could run).
        """
        for i, char in enumerate(command):
            delay = random.uniform(0.04, 0.10)
            # Slight pause at spaces (between arguments)
            if char == " ":
                delay += random.uniform(0.05, 0.15)
            await asyncio.sleep(self._apply_speed(delay))
            await send_char_fn(char)
            self._record_event("keyboard")

        # Brief pause before pressing Enter (reviewing command)
        await asyncio.sleep(self._apply_speed(random.uniform(0.3, 1.0)))
        await send_enter_fn()
        self._record_event("keyboard")

    async def idle_think(self, duration_seconds: float) -> None:
        """Simulate thinking/reading — minimal activity with micro-movements.

        Generates a small input event every 45-90 seconds to avoid
        triggering time tracker idle detection.
        """
        cfg = self.config.activity
        elapsed = 0.0
        interval = random.uniform(
            cfg.idle_micro_movement_min,
            cfg.idle_micro_movement_max,
        )

        logger.debug("Thinking for %.1f seconds", duration_seconds)

        while elapsed < duration_seconds:
            wait = min(interval, duration_seconds - elapsed)
            await asyncio.sleep(self._apply_speed(wait))
            elapsed += wait

            if elapsed < duration_seconds:
                # Micro-movement: just record it. Actual mouse movement
                # would go through input_sim when available.
                self._record_event("mouse_micro")
                interval = random.uniform(
                    cfg.idle_micro_movement_min,
                    cfg.idle_micro_movement_max,
                )

    async def take_break(self, duration_seconds: float) -> None:
        """Simulate a break — very minimal activity.

        Occasional tiny mouse movement every 3-4 minutes to avoid
        triggering 5-minute idle thresholds.
        """
        logger.info("Taking break for %.0f seconds", duration_seconds)
        elapsed = 0.0

        while elapsed < duration_seconds:
            # Wait 3-4 minutes between micro-movements during break
            interval = random.uniform(180, 240)
            wait = min(interval, duration_seconds - elapsed)
            await asyncio.sleep(wait)
            elapsed += wait

            if elapsed < duration_seconds:
                self._record_event("mouse_micro")

    async def pause_natural(self, min_sec: float = 0.5, max_sec: float = 3.0) -> None:
        """Insert a natural pause between actions."""
        await asyncio.sleep(self._apply_speed(random.uniform(min_sec, max_sec)))

    def _record_event(self, kind: str) -> None:
        """Record an activity event for the activity monitor."""
        self._activity_events.append((time.monotonic(), kind))
        if self._activity_monitor is not None:
            self._activity_monitor.record_event(kind)
        # Keep only last 2 hours of events to prevent memory growth
        cutoff = time.monotonic() - 7200
        if len(self._activity_events) > 10000:
            self._activity_events = [
                e for e in self._activity_events if e[0] > cutoff
            ]

    def get_recent_events(self, window_seconds: float = 600) -> list[tuple[float, str]]:
        """Get activity events within the last N seconds."""
        cutoff = time.monotonic() - window_seconds
        return [(t, k) for t, k in self._activity_events if t > cutoff]

    def activity_ratio(self, window_seconds: float = 600) -> float:
        """Calculate activity ratio for the given window.

        Returns fraction of seconds that had at least one event.
        """
        events = self.get_recent_events(window_seconds)
        if not events:
            return 0.0

        now = time.monotonic()
        window_start = now - window_seconds

        # Count unique seconds with activity
        active_seconds = set()
        for t, _ in events:
            second = int(t - window_start)
            active_seconds.add(second)

        return len(active_seconds) / window_seconds
