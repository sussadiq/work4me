"""CAPTCHA detection and solving via Claude Code CLI."""

from __future__ import annotations

import asyncio
import json
import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from work4me.config import CaptchaConfig

if TYPE_CHECKING:
    from work4me.controllers.claude_code import ClaudeCodeManager

logger = logging.getLogger(__name__)

CAPTCHA_SELECTORS = [
    "iframe[src*='recaptcha']",
    "iframe[src*='hcaptcha']",
    "#cf-turnstile-container",
    ".g-recaptcha",
    ".h-captcha",
    "[data-sitekey]",
]


@dataclass
class CaptchaInfo:
    """Detected CAPTCHA on a page."""

    kind: str  # "recaptcha", "hcaptcha", "turnstile", "unknown"
    selector: str
    box: dict[str, float]  # {x, y, width, height}


@dataclass
class CaptchaSolution:
    """Structured solution from Claude vision."""

    steps: list[dict[str, Any]]


class CaptchaDetector:
    """Detect CAPTCHAs on a page by checking known selectors."""

    async def detect(self, page: Any) -> CaptchaInfo | None:
        """Check known selectors. Returns CaptchaInfo or None."""
        for selector in CAPTCHA_SELECTORS:
            try:
                locator = page.locator(selector).first
                box = await locator.bounding_box(timeout=1000)
                if box:
                    kind = self._classify(selector)
                    return CaptchaInfo(kind=kind, selector=selector, box=box)
            except Exception:
                continue
        return None

    def _classify(self, selector: str) -> str:
        """Classify CAPTCHA kind from the matched selector."""
        if "recaptcha" in selector or "g-recaptcha" in selector:
            return "recaptcha"
        if "hcaptcha" in selector or "h-captcha" in selector:
            return "hcaptcha"
        if "turnstile" in selector:
            return "turnstile"
        return "unknown"


class CaptchaSolver:
    """Solve CAPTCHAs by screenshotting and asking Claude Code CLI."""

    def __init__(self, config: CaptchaConfig, claude: ClaudeCodeManager) -> None:
        self._config = config
        self._claude = claude

    async def solve(
        self,
        page: Any,
        browser_mouse: Any,
        captcha: CaptchaInfo,
    ) -> bool:
        """Screenshot the CAPTCHA region, ask Claude, execute solution."""
        if not self._config.enabled:
            return False

        for attempt in range(self._config.max_attempts):
            try:
                screenshot_bytes = await page.screenshot(
                    clip=captcha.box,
                    timeout=self._config.screenshot_timeout,
                )
                solution = await self._ask_claude(screenshot_bytes, captcha.kind)
                if solution and await self._execute_solution(
                    page, browser_mouse, solution
                ):
                    logger.info(
                        "CAPTCHA solved on attempt %d/%d",
                        attempt + 1,
                        self._config.max_attempts,
                    )
                    return True
            except Exception:
                logger.warning(
                    "CAPTCHA solve attempt %d failed",
                    attempt + 1,
                    exc_info=True,
                )
        return False

    async def _ask_claude(
        self, screenshot: bytes, kind: str
    ) -> CaptchaSolution | None:
        """Save screenshot to temp file, ask Claude Code CLI to analyze it."""
        tmp_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                suffix=".png", prefix="work4me-captcha-", delete=False
            ) as tmp:
                tmp.write(screenshot)
                tmp_path = tmp.name

            prompt = (
                f"Read the image at {tmp_path} and analyze the {kind} CAPTCHA. "
                "Return a JSON object with a 'steps' array. "
                "Each step should have: 'action' (click/type/select), "
                "and optionally 'x'/'y' (coordinates relative to the image), "
                "'text' (for typing), or 'selector' (CSS selector). "
                "Return ONLY valid JSON, no markdown."
            )

            result = await asyncio.wait_for(
                self._claude.execute(
                    prompt=prompt,
                    working_dir="/tmp",
                    max_turns=3,
                ),
                timeout=60.0,
            )

            if result.error:
                logger.warning("Claude Code CAPTCHA call failed: %s", result.error[:200])
                return None

            return self._parse_solution(result.raw_text)

        except asyncio.TimeoutError:
            logger.warning("Claude CAPTCHA analysis timed out (60s)")
            return None
        except Exception:
            logger.warning("Claude CAPTCHA analysis failed", exc_info=True)
            return None
        finally:
            if tmp_path:
                try:
                    Path(tmp_path).unlink(missing_ok=True)
                except Exception:
                    pass

    def _parse_solution(self, raw_text: str) -> CaptchaSolution | None:
        """Extract JSON solution from Claude's raw text response."""
        # Find the first JSON object containing "steps"
        start = raw_text.find("{")
        if start == -1:
            return None
        # Find matching closing brace
        depth = 0
        for i in range(start, len(raw_text)):
            if raw_text[i] == "{":
                depth += 1
            elif raw_text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        data = json.loads(raw_text[start : i + 1])
                        steps = data.get("steps", [])
                        if isinstance(steps, list):
                            return CaptchaSolution(steps=steps)
                    except json.JSONDecodeError:
                        pass
                    break
        return None

    async def _execute_solution(
        self, page: Any, browser_mouse: Any, solution: CaptchaSolution
    ) -> bool:
        """Execute each step from Claude's solution using human-like mouse."""
        for step in solution.steps:
            action = step.get("action", "")
            try:
                if action == "click":
                    x = float(step.get("x", 0))
                    y = float(step.get("y", 0))
                    await browser_mouse.click_at(page, x, y)
                elif action == "type":
                    text = step.get("text", "")
                    selector = step.get("selector")
                    if selector:
                        await page.type(selector, text, delay=85)
                    else:
                        await page.keyboard.type(text, delay=85)
                elif action == "select":
                    selector = step.get("selector", "")
                    await browser_mouse.click_element(page, selector)
                else:
                    logger.debug("Unknown CAPTCHA step action: %s", action)
            except Exception:
                logger.warning(
                    "CAPTCHA step failed: %s", step, exc_info=True
                )
                return False
        return True
