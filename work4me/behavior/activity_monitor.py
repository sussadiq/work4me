"""Activity monitoring and anti-detection constraint enforcement."""

import logging
import time
from dataclasses import dataclass
from enum import Enum

from work4me.config import ActivityConfig

logger = logging.getLogger(__name__)


class BehaviorAdjustment(Enum):
    NONE = "none"
    SLOW_DOWN = "slow_down"
    SPEED_UP = "speed_up"
    ADD_IDLE = "add_idle"
    ADD_MOUSE = "add_mouse"
    ADD_VARIATION = "add_variation"


@dataclass
class ActivityHealth:
    activity_ok: bool
    variance_ok: bool
    balance_ok: bool
    details: str = ""


class ActivityMonitor:
    """Tracks activity statistics and enforces human-plausible bounds."""

    def __init__(self, config: ActivityConfig):
        self._config = config
        self._events: list[tuple[str, float]] = []  # (kind, timestamp)
        self._max_history = 7200  # 2 hours

    def record_event(self, kind: str, timestamp: float | None = None) -> None:
        """Record an input event (keyboard or mouse)."""
        ts = timestamp or time.time()
        self._events.append((kind, ts))
        self._prune()

    def _prune(self) -> None:
        """Remove events older than max history."""
        cutoff = time.time() - self._max_history
        self._events = [(k, t) for k, t in self._events if t >= cutoff]

    def activity_ratio(self, window_seconds: int = 600) -> float:
        """Active seconds / window seconds. Target: 0.40-0.70."""
        now = time.time()
        cutoff = now - window_seconds
        active_seconds = set()
        for _, ts in self._events:
            if ts >= cutoff:
                active_seconds.add(int(ts))
        if window_seconds == 0:
            return 0.0
        return len(active_seconds) / window_seconds

    def variance(self, window_seconds: int = 5400) -> float:
        """Activity ratio variance over the window. Must be >0.04."""
        now = time.time()
        sub_window = 600
        ratios = []
        for i in range(0, window_seconds, sub_window):
            start = now - window_seconds + i
            end = start + sub_window
            active = set()
            for _, ts in self._events:
                if start <= ts < end:
                    active.add(int(ts))
            ratios.append(len(active) / sub_window)

        if len(ratios) < 2:
            return 0.0
        mean = sum(ratios) / len(ratios)
        return sum((r - mean) ** 2 for r in ratios) / len(ratios)

    def keyboard_mouse_balance(self, window_seconds: int = 3000) -> tuple[float, float]:
        """(keyboard_ratio, mouse_ratio) of events in window."""
        now = time.time()
        cutoff = now - window_seconds
        kb = sum(1 for k, t in self._events if t >= cutoff and k == "keyboard")
        mouse = sum(1 for k, t in self._events if t >= cutoff and k == "mouse")
        total = kb + mouse
        if total == 0:
            return (0.0, 0.0)
        return (kb / total, mouse / total)

    def is_within_bounds(self) -> ActivityHealth:
        """Check all anti-detection constraints."""
        ratio = self.activity_ratio()
        var = self.variance()
        kb, mouse = self.keyboard_mouse_balance()

        activity_ok = ratio <= 0.85 or len(self._events) == 0
        variance_ok = var >= 0.04 or len(self._events) < 60
        balance_ok = not (kb > 0.95 and mouse < 0.05 and len(self._events) > 100)

        details = f"ratio={ratio:.2f} var={var:.4f} kb={kb:.2f} mouse={mouse:.2f}"
        return ActivityHealth(
            activity_ok=activity_ok,
            variance_ok=variance_ok,
            balance_ok=balance_ok,
            details=details,
        )

    def recommended_adjustment(self) -> BehaviorAdjustment:
        """Suggest behavior adjustment based on current metrics."""
        ratio = self.activity_ratio()
        var = self.variance()
        kb, mouse = self.keyboard_mouse_balance()

        if ratio > 0.80:
            return BehaviorAdjustment.SLOW_DOWN
        if ratio < 0.30 and len(self._events) > 2:
            return BehaviorAdjustment.SPEED_UP
        if var < 0.04 and len(self._events) > 60:
            return BehaviorAdjustment.ADD_VARIATION
        if kb > 0.90 and mouse < 0.10 and len(self._events) > 100:
            return BehaviorAdjustment.ADD_MOUSE
        return BehaviorAdjustment.NONE
