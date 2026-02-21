"""Human-like mouse movement simulation using Bezier curves and Fitts's law."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass


@dataclass
class Point:
    x: float
    y: float

    def distance_to(self, other: "Point") -> float:
        return math.sqrt((self.x - other.x) ** 2 + (self.y - other.y) ** 2)


class HumanMouse:
    """Generate human-like mouse movement paths."""

    def __init__(self, overshoot_probability: float = 0.15):
        self._rng = random.Random()
        self._overshoot_prob = overshoot_probability

    def bezier_path(self, start: Point, end: Point, steps_per_100px: int = 8) -> list[Point]:
        """Generate a cubic Bezier curve path from start to end."""
        dist = start.distance_to(end)
        if dist < 1:
            return [start, end]

        ctrl_points = self._generate_control_points(start, end, dist)

        num_steps = max(5, int(dist / 100 * steps_per_100px))
        path = []
        for i in range(num_steps + 1):
            t = i / num_steps
            p = self._cubic_bezier(t, start, ctrl_points[0], ctrl_points[1], end)
            path.append(p)

        # Add overshoot
        if self._rng.random() < self._overshoot_prob and dist > 50:
            overshoot_dist = self._rng.uniform(5, min(20, dist * 0.05))
            dx = end.x - start.x
            dy = end.y - start.y
            norm = math.sqrt(dx * dx + dy * dy) or 1
            overshoot = Point(end.x + dx / norm * overshoot_dist, end.y + dy / norm * overshoot_dist)
            path.append(overshoot)
            for _ in range(self._rng.randint(1, 3)):
                correction = Point(
                    end.x + self._rng.gauss(0, 2),
                    end.y + self._rng.gauss(0, 2),
                )
                path.append(correction)

        return path

    def fitts_duration(self, distance: float, target_width: float) -> float:
        """Fitts's law: T = a + b * log2(D/W + 1). Returns seconds."""
        a = 0.05
        b = 0.15
        if target_width <= 0:
            target_width = 1
        return a + b * math.log2(distance / target_width + 1)

    def micro_movement(self, current: Point, max_delta: int = 15) -> Point:
        """Small idle mouse movement (anti-idle)."""
        dx = self._rng.gauss(0, max_delta / 3)
        dy = self._rng.gauss(0, max_delta / 3)
        return Point(current.x + dx, current.y + dy)

    def _generate_control_points(self, start: Point, end: Point, dist: float) -> list[Point]:
        """Generate 2 control points for cubic Bezier."""
        dx = end.x - start.x
        dy = end.y - start.y
        norm = math.sqrt(dx * dx + dy * dy) or 1
        perp_x = -dy / norm
        perp_y = dx / norm

        offset_scale = dist * 0.2
        cp1 = Point(
            start.x + dx * 0.3 + perp_x * self._rng.gauss(0, offset_scale),
            start.y + dy * 0.3 + perp_y * self._rng.gauss(0, offset_scale),
        )
        cp2 = Point(
            start.x + dx * 0.7 + perp_x * self._rng.gauss(0, offset_scale),
            start.y + dy * 0.7 + perp_y * self._rng.gauss(0, offset_scale),
        )
        return [cp1, cp2]

    def _cubic_bezier(self, t: float, p0: Point, p1: Point, p2: Point, p3: Point) -> Point:
        """Evaluate cubic Bezier curve at parameter t."""
        u = 1 - t
        x = u**3 * p0.x + 3 * u**2 * t * p1.x + 3 * u * t**2 * p2.x + t**3 * p3.x
        y = u**3 * p0.y + 3 * u**2 * t * p1.y + 3 * u * t**2 * p2.y + t**3 * p3.y
        return Point(x, y)
