"""Typed async event bus for internal communication."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
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
class ClaudeActionCaptured(Event):
    action_kind: str  # "edit", "bash", "write"
    file_path: str = ""
    content: str = ""
    command: str = ""


@dataclass
class ActivityRecorded(Event):
    kind: str  # "keyboard", "mouse", "mouse_micro", "idle"
    timestamp: float = 0.0


@dataclass
class HealthWarning(Event):
    metric: str
    value: float
    threshold: float
    recommendation: str = ""


@dataclass
class TaskProgress(Event):
    activity_index: int
    total_activities: int
    description: str = ""


EventHandler = Callable[[Event], Coroutine[Any, Any, None]]


class EventBus:
    """Simple typed async event bus."""

    def __init__(self) -> None:
        self._handlers: dict[type, list[EventHandler]] = {}

    def subscribe(self, event_type: type[Event], handler: EventHandler) -> None:
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    async def emit(self, event: Event) -> None:
        handlers = self._handlers.get(type(event), [])
        for handler in handlers:
            try:
                await handler(event)
            except Exception:
                logger.exception(
                    "Error in event handler for %s", type(event).__name__
                )
