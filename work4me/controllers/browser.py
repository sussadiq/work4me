"""Browser automation via Firefox/Playwright."""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any
from urllib.parse import quote_plus

from work4me.config import BrowserConfig

logger = logging.getLogger(__name__)

COOKIE_SELECTORS = [
    "button:has-text('Accept All')",
    "button:has-text('Accept all')",
    "button:has-text('Accept')",
    "button:has-text('I agree')",
    "button:has-text('OK')",
    "[id*='accept']",
    "[class*='accept']",
    "button:has-text('Got it')",
    "button:has-text('Allow')",
]


class BrowserController:
    """Controls a visible Firefox browser via Playwright."""

    def __init__(self, config: BrowserConfig) -> None:
        self._config = config
        self._context: Any = None
        self._page: Any = None
        self._browser_available: bool = False
        self._mouse: Any = None  # BrowserMouse (set in launch)
        self._captcha_detector: Any = None  # CaptchaDetector
        self._captcha_solver: Any = None  # CaptchaSolver

    async def launch(self) -> None:
        """Launch Firefox via Playwright with a persistent context."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise RuntimeError(
                "playwright required: pip install playwright && playwright install firefox"
            )

        self._playwright = await async_playwright().__aenter__()

        self._context = await self._playwright.firefox.launch_persistent_context(
            self._config.user_data_dir or "",
            headless=False,
            timeout=self._config.launch_timeout,
            firefox_user_prefs={
                "dom.webdriver.enabled": False,
            },
        )

        # Mask navigator.webdriver on every page (including future navigations)
        await self._context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        self._page = (
            self._context.pages[0]
            if self._context.pages
            else await self._context.new_page()
        )

        # Register dialog handler (auto-dismiss alerts/confirms)
        self._page.on("dialog", self._on_dialog)

        # Initialize browser mouse bridge
        self._init_mouse_and_captcha()

        self._browser_available = True
        logger.info(
            "Firefox launched (visible, persistent=%s)",
            bool(self._config.user_data_dir),
        )

    def _init_mouse_and_captcha(self) -> None:
        """Initialize BrowserMouse and CAPTCHA components."""
        from work4me.behavior.mouse import HumanMouse
        from work4me.controllers.browser_mouse import BrowserMouse
        from work4me.controllers.captcha import CaptchaDetector, CaptchaSolver

        self._mouse = BrowserMouse(HumanMouse(), self._config.mouse)
        self._captcha_detector = CaptchaDetector()
        self._captcha_solver = CaptchaSolver(self._config.captcha)

    async def _on_dialog(self, dialog: Any) -> None:
        """Handle JS alert/confirm/prompt dialogs."""
        logger.debug("Dialog appeared: type=%s message=%s", dialog.type, dialog.message)
        await dialog.accept()

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    async def navigate(self, url: str) -> None:
        """Navigate to a URL."""
        if not self._page:
            raise RuntimeError("Browser not launched")
        await self._page.goto(url, wait_until="domcontentloaded")
        logger.debug("Navigated to %s", url)

    async def navigate_with_captcha_check(self, url: str) -> None:
        """Navigate, dismiss cookies, and handle CAPTCHA if present."""
        await self.navigate(url)
        await asyncio.sleep(1.0)
        await self.dismiss_cookie_banner()
        await self.handle_captcha()

    async def go_back(self) -> None:
        """Navigate back in browser history."""
        if not self._page:
            raise RuntimeError("Browser not launched")
        await self._page.go_back()

    async def go_forward(self) -> None:
        """Navigate forward in browser history."""
        if not self._page:
            raise RuntimeError("Browser not launched")
        await self._page.go_forward()

    async def current_url(self) -> str:
        """Return the current page URL."""
        if not self._page:
            raise RuntimeError("Browser not launched")
        return str(self._page.url)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    async def search(self, query: str, engine: str = "google") -> None:
        """Perform a web search."""
        if engine == "google":
            await self.navigate(
                f"https://www.google.com/search?q={quote_plus(query)}"
            )
        elif engine == "stackoverflow":
            await self.navigate(
                f"https://stackoverflow.com/search?q={quote_plus(query)}"
            )
        else:
            await self.navigate(
                f"https://www.google.com/search?q={quote_plus(query)}"
            )

    async def type_in_search(
        self, selector: str, query: str, delay_ms: int = 85
    ) -> None:
        """Type a search query character by character with human-like delay."""
        if not self._page:
            raise RuntimeError("Browser not launched")
        await self._page.click(selector)
        await self._page.type(selector, query, delay=delay_ms)

    # ------------------------------------------------------------------
    # Element interaction
    # ------------------------------------------------------------------

    async def click(self, selector: str, timeout: float = 5000) -> None:
        """Click element using BrowserMouse (human-like path)."""
        if not self._page:
            raise RuntimeError("Browser not launched")
        if self._mouse:
            await self._mouse.click_element(self._page, selector, timeout=timeout)
        else:
            await self._page.click(selector, timeout=timeout)

    async def click_link(self, text: str, timeout: float = 5000) -> None:
        """Find link by visible text and click with BrowserMouse."""
        selector = f"a:has-text('{text}')"
        await self.click(selector, timeout=timeout)

    async def fill_field(
        self, selector: str, text: str, delay_ms: int = 85
    ) -> None:
        """Click a form field, clear it, and type with human-like delay."""
        if not self._page:
            raise RuntimeError("Browser not launched")
        if self._mouse:
            await self._mouse.click_element(self._page, selector)
        else:
            await self._page.click(selector)
        await self._page.fill(selector, "")
        await self._page.type(selector, text, delay=delay_ms)

    async def submit_form(self, selector: str | None = None) -> None:
        """Find and click a submit button."""
        if selector:
            await self.click(selector)
        else:
            for sel in [
                "button[type='submit']",
                "input[type='submit']",
                "button:has-text('Submit')",
            ]:
                try:
                    await self.click(sel, timeout=2000)
                    return
                except Exception:
                    continue
            logger.warning("No submit button found")

    # ------------------------------------------------------------------
    # Element queries
    # ------------------------------------------------------------------

    async def wait_for(self, selector: str, timeout: float = 10000) -> None:
        """Wait for an element to appear."""
        if not self._page:
            raise RuntimeError("Browser not launched")
        await self._page.wait_for_selector(selector, timeout=timeout)

    async def get_element_text(self, selector: str) -> str:
        """Get text content of an element."""
        if not self._page:
            raise RuntimeError("Browser not launched")
        return str(await self._page.locator(selector).first.inner_text())

    async def get_attribute(self, selector: str, attr: str) -> str | None:
        """Get an attribute value from an element."""
        if not self._page:
            raise RuntimeError("Browser not launched")
        return await self._page.locator(selector).first.get_attribute(attr)

    async def is_visible(self, selector: str) -> bool:
        """Check if an element is visible on the page."""
        if not self._page:
            raise RuntimeError("Browser not launched")
        return bool(await self._page.locator(selector).first.is_visible())

    # ------------------------------------------------------------------
    # Scrolling and screenshots
    # ------------------------------------------------------------------

    async def scroll_down(self, pixels: int = 300) -> None:
        """Scroll down with natural variation."""
        if not self._page:
            raise RuntimeError("Browser not launched")
        steps = max(1, pixels // 100)
        for _ in range(steps):
            delta = random.randint(80, 150)
            await self._page.mouse.wheel(0, delta)
            await asyncio.sleep(random.uniform(0.2, 0.5))

    async def screenshot(
        self,
        path: str | None = None,
        clip: dict[str, float] | None = None,
    ) -> bytes:
        """Take a screenshot (full page or clipped region)."""
        if not self._page:
            raise RuntimeError("Browser not launched")
        kwargs: dict[str, Any] = {}
        if path:
            kwargs["path"] = path
        if clip:
            kwargs["clip"] = clip
        result: bytes = await self._page.screenshot(**kwargs)
        return result

    # ------------------------------------------------------------------
    # Page content
    # ------------------------------------------------------------------

    async def get_page_text(self) -> str:
        """Get the visible text content of the page."""
        if not self._page:
            raise RuntimeError("Browser not launched")
        return str(await self._page.inner_text("body"))

    # ------------------------------------------------------------------
    # Cookie banner dismissal
    # ------------------------------------------------------------------

    async def dismiss_cookie_banner(self) -> bool:
        """Try common cookie banner selectors to dismiss. Returns True if dismissed."""
        if not self._page:
            return False
        for selector in COOKIE_SELECTORS:
            try:
                locator = self._page.locator(selector).first
                if await locator.is_visible(timeout=500):
                    if self._mouse:
                        await self._mouse.click_element(
                            self._page, selector, timeout=1000
                        )
                    else:
                        await locator.click(timeout=1000)
                    logger.debug("Dismissed cookie banner via: %s", selector)
                    return True
            except Exception:
                continue
        return False

    # ------------------------------------------------------------------
    # CAPTCHA handling
    # ------------------------------------------------------------------

    async def handle_captcha(self) -> bool:
        """Detect and solve CAPTCHA if present. Returns True if solved."""
        if not self._page or not self._captcha_detector:
            return False
        captcha = await self._captcha_detector.detect(self._page)
        if not captcha:
            return False
        logger.info("CAPTCHA detected: %s", captcha.kind)
        if self._captcha_solver and self._mouse:
            return bool(
                await self._captcha_solver.solve(
                    self._page, self._mouse, captcha
                )
            )
        return False

    # ------------------------------------------------------------------
    # Tab management
    # ------------------------------------------------------------------

    async def new_tab(self, url: str = "about:blank") -> None:
        """Open a new tab."""
        if not self._context:
            raise RuntimeError("Browser not launched")
        self._page = await self._context.new_page()
        if url != "about:blank":
            await self.navigate(url)

    async def close_tab(self) -> None:
        """Close the current tab and switch to the previous one."""
        if self._page:
            await self._page.close()
        pages = self._context.pages if self._context else []
        self._page = pages[-1] if pages else None

    # ------------------------------------------------------------------
    # Cookie management
    # ------------------------------------------------------------------

    async def get_cookies(self) -> list[dict[str, Any]]:
        """Get all cookies from the browser context."""
        if not self._context:
            raise RuntimeError("Browser not launched")
        result: list[dict[str, Any]] = await self._context.cookies()
        return result

    async def set_cookies(self, cookies: list[dict[str, Any]]) -> None:
        """Set cookies on the browser context."""
        if not self._context:
            raise RuntimeError("Browser not launched")
        await self._context.add_cookies(cookies)

    # ------------------------------------------------------------------
    # Health and lifecycle
    # ------------------------------------------------------------------

    async def health_check(self) -> bool:
        """Check if the browser is responsive."""
        if not self._page:
            return False
        try:
            await self._page.evaluate("1 + 1")
            return True
        except Exception:
            return False

    async def restart(self) -> None:
        """Cleanup and relaunch browser."""
        logger.info("Restarting browser...")
        await self.cleanup()
        await self.launch()

    async def cleanup(self) -> None:
        """Close browser and stop Playwright."""
        self._browser_available = False
        try:
            if self._context:
                await self._context.close()
                self._context = None
        except Exception:
            logger.warning("Failed to close browser context", exc_info=True)
        try:
            if hasattr(self, "_playwright") and self._playwright:
                await self._playwright.stop()
        except Exception:
            logger.warning("Failed to stop playwright", exc_info=True)
