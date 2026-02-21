"""Bridge between HumanMouse (Bezier + Fitts's law) and Playwright page.mouse."""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any

from work4me.behavior.mouse import HumanMouse, Point
from work4me.config import BrowserMouseConfig

logger = logging.getLogger(__name__)


class BrowserMouse:
    """Human-like mouse movements routed through Playwright's page.mouse API."""

    def __init__(self, human_mouse: HumanMouse, config: BrowserMouseConfig) -> None:
        self._human = human_mouse
        self._config = config
        self._pos = Point(0.0, 0.0)

    @property
    def position(self) -> Point:
        """Current tracked mouse position."""
        return self._pos

    async def move_to(self, page: Any, x: float, y: float) -> None:
        """Move mouse to (x, y) along a Bezier curve with Fitts's law timing."""
        target = Point(x, y)
        path = self._human.bezier_path(self._pos, target)
        dist = self._pos.distance_to(target)
        total_time = self._human.fitts_duration(dist, target_width=20.0)
        step_time = total_time / max(len(path) - 1, 1)

        for point in path[1:]:
            await page.mouse.move(point.x, point.y)
            interval = random.uniform(
                self._config.step_interval_min, self._config.step_interval_max
            )
            await asyncio.sleep(max(step_time, interval))

        self._pos = target

    async def click_at(
        self, page: Any, x: float, y: float, button: str = "left"
    ) -> None:
        """Move to position and click with human-like pre/post-click delays."""
        await self.move_to(page, x, y)
        await asyncio.sleep(
            random.uniform(self._config.click_delay_min, self._config.click_delay_max)
        )
        await page.mouse.click(x, y, button=button)
        await asyncio.sleep(random.uniform(0.05, 0.1))

    async def click_element(
        self, page: Any, selector: str, timeout: float = 5000
    ) -> None:
        """Locate element by selector, compute center, move + click humanly."""
        el = page.locator(selector).first
        box = await el.bounding_box(timeout=timeout)
        if not box:
            raise ValueError(f"Element not visible: {selector}")

        cx = box["x"] + box["width"] / 2 + random.uniform(-3, 3)
        cy = box["y"] + box["height"] / 2 + random.uniform(-3, 3)
        await self.click_at(page, cx, cy)

    async def micro_movement(self, page: Any) -> None:
        """Small idle mouse jitter (anti-idle)."""
        new_pos = self._human.micro_movement(self._pos)
        await page.mouse.move(new_pos.x, new_pos.y)
        self._pos = new_pos
