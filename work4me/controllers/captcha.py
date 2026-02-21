"""CAPTCHA detection and solving via Claude vision API."""

from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass
from typing import Any

from work4me.config import CaptchaConfig

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
    """Solve CAPTCHAs by screenshotting and asking Claude vision."""

    def __init__(self, config: CaptchaConfig) -> None:
        self._config = config
        self._client: Any = None  # lazy anthropic.AsyncAnthropic

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
        """Send screenshot to Claude API, get structured solution back."""
        client = self._get_client()
        if client is None:
            return None

        b64 = base64.b64encode(screenshot).decode("ascii")
        prompt = (
            f"This is a screenshot of a {kind} CAPTCHA on a web page. "
            "Analyze it and return a JSON object with a 'steps' array. "
            "Each step should have: 'action' (click/type/select), "
            "and optionally 'x'/'y' (coordinates relative to the image), "
            "'text' (for typing), or 'selector' (CSS selector). "
            "Return ONLY valid JSON, no markdown."
        )

        try:
            response = await client.messages.create(
                model=self._config.anthropic_model,
                max_tokens=1024,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": b64,
                                },
                            },
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
            )
            text = response.content[0].text
            data = json.loads(text)
            return CaptchaSolution(steps=data.get("steps", []))
        except Exception:
            logger.warning("Claude CAPTCHA API call failed", exc_info=True)
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

    def _get_client(self) -> Any:
        """Lazy-init the Anthropic async client."""
        if self._client is not None:
            return self._client
        try:
            import anthropic

            self._client = anthropic.AsyncAnthropic()
            return self._client
        except ImportError:
            logger.warning(
                "anthropic package not installed — CAPTCHA solving disabled"
            )
            return None
