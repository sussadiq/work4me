"""Task decomposition via Claude Code."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from work4me.config import ClaudeConfig
from work4me.controllers.claude_code import ClaudeCodeManager

logger = logging.getLogger(__name__)


class ActivityKind(Enum):
    CODING = "CODING"
    READING = "READING"
    TERMINAL = "TERMINAL"
    BROWSER = "BROWSER"
    THINKING = "THINKING"


@dataclass
class Activity:
    kind: ActivityKind
    description: str
    estimated_minutes: float
    files_involved: list[str]
    commands: list[str]
    search_queries: list[str]
    dependencies: list[str]


@dataclass
class TaskPlan:
    task_description: str
    activities: list[Activity]

    @property
    def total_estimated_minutes(self) -> float:
        return sum(a.estimated_minutes for a in self.activities)


DECOMPOSITION_PROMPT = """You are a senior software engineer planning a coding task. Decompose the following task into a sequence of developer activities. Each activity should represent a natural unit of work (15-45 minutes).

Task: {task_description}
Time Budget: {hours} hours
Working Directory: {working_dir}

For each activity, specify:
1. kind: one of CODING, READING, TERMINAL, BROWSER, THINKING
2. description: what the developer does
3. estimated_minutes: how long it should take
4. files_involved: which files will be created/modified/read
5. commands: any terminal commands to run
6. search_queries: any web searches needed (for BROWSER activities)
7. dependencies: indices (as strings) of activities that must complete first

Return ONLY a JSON array. No explanation. The total estimated_minutes should equal approximately {target_minutes} (70% of budget — rest is breaks/transitions/thinking)."""


class TaskPlanner:
    """Decomposes a high-level task into structured activities using Claude Code."""

    def __init__(self, config: ClaudeConfig):
        self._config = config
        self._claude = ClaudeCodeManager(config)

    async def decompose(
        self,
        task_description: str,
        time_budget_hours: float,
        working_dir: str,
        project_context: str = "",
    ) -> TaskPlan:
        """Ask Claude Code to decompose a task into activities.

        Retries on transient failures (stream errors, malformed output)
        up to config.plan_max_retries times with exponential backoff.
        """
        target_minutes = int(time_budget_hours * 60 * 0.70)
        prompt = DECOMPOSITION_PROMPT.format(
            task_description=task_description,
            hours=time_budget_hours,
            working_dir=working_dir,
            target_minutes=target_minutes,
        )
        if project_context:
            prompt += f"\n\nProject context:\n{project_context}"

        max_retries = self._config.plan_max_retries
        base_delay = self._config.plan_retry_base_delay
        last_exc: Exception | None = None

        for attempt in range(max_retries):
            try:
                result = await self._claude.execute(
                    prompt=prompt,
                    working_dir=working_dir,
                    max_turns=3,
                )

                if result.error:
                    raise RuntimeError(f"Task decomposition failed: {result.error}")

                return self._parse_plan(task_description, result.raw_text)
            except (RuntimeError, ValueError, json.JSONDecodeError) as exc:
                last_exc = exc
                if attempt < max_retries - 1:
                    wait = base_delay * (2 ** attempt)
                    logger.warning(
                        "Task decomposition attempt %d/%d failed, retrying in %.1fs: %s",
                        attempt + 1, max_retries, wait, exc,
                    )
                    await asyncio.sleep(wait)

        raise RuntimeError(
            f"Task decomposition failed after {max_retries} attempts: {last_exc}"
        )

    def _parse_plan(self, task_description: str, raw_text: str) -> TaskPlan:
        """Parse Claude's JSON response into a TaskPlan."""
        text = raw_text.strip()
        start = text.find("[")
        if start == -1:
            raise ValueError(f"No JSON array found in Claude response: {text[:200]}")

        # Find matching closing bracket by tracking depth
        depth = 0
        end = -1
        in_string = False
        escape_next = False
        for i in range(start, len(text)):
            ch = text[i]
            if escape_next:
                escape_next = False
                continue
            if ch == "\\":
                escape_next = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break

        if end == -1:
            raise ValueError(f"Unmatched JSON array in Claude response: {text[:200]}")

        json_str = text[start:end]
        logger.debug("Extracted JSON (%d chars) from raw_text (%d chars)", len(json_str), len(text))
        data = json.loads(json_str)
        activities = []
        for item in data:
            kind_str = item.get("kind", "CODING").upper()
            try:
                kind = ActivityKind(kind_str)
            except ValueError:
                logger.warning("Unknown activity kind %r, defaulting to CODING", kind_str)
                kind = ActivityKind.CODING

            activities.append(Activity(
                kind=kind,
                description=item.get("description", ""),
                estimated_minutes=float(item.get("estimated_minutes", 15)),
                files_involved=item.get("files_involved", []),
                commands=item.get("commands", []),
                search_queries=item.get("search_queries", []),
                dependencies=[str(d) for d in item.get("dependencies", [])],
            ))

        logger.info("Decomposed task into %d activities (%.0f min total)",
                     len(activities), sum(a.estimated_minutes for a in activities))
        return TaskPlan(task_description=task_description, activities=activities)
