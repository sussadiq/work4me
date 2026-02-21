"""Typed async event bus for internal communication."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)


@dataclass
class Event:
    """Base event class."""
    pass


@dataclass
class StateChanged(Event):
    old_state: str
    new_state: str
    trigger: str = ""


@dataclass
class TaskProgress(Event):
    activity_index: int
    total_activities: int
    description: str = ""


class EventBus:
    """Simple typed async event bus."""

    def __init__(self) -> None:
        self._handlers: dict[type, list[Callable[[Event], Coroutine[Any, Any, None]]]] = {}

    async def emit(self, event: Event) -> None:
        handlers = self._handlers.get(type(event), [])
        for handler in handlers:
            try:
                await handler(event)
            except Exception:
                logger.exception(
                    "Error in event handler for %s", type(event).__name__
                )
