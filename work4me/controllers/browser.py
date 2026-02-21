"""Browser automation via Chromium CDP/Playwright."""

import asyncio
import logging
import random
from typing import Any, Optional
from urllib.parse import quote_plus

from work4me.config import BrowserConfig

logger = logging.getLogger(__name__)


class BrowserController:
    """Controls a visible Chromium browser via Playwright/CDP."""

    def __init__(self, config: BrowserConfig):
        self._config = config
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None
        self._process: Optional[asyncio.subprocess.Process] = None

    async def launch(self) -> None:
        """Launch Chromium with remote debugging and connect via Playwright."""
        cmd = [
            self._config.chromium_path,
            f"--remote-debugging-port={self._config.debug_port}",
            f"--ozone-platform={self._config.ozone_platform}",
            "--no-first-run",
            "--no-default-browser-check",
        ]
        self._process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        logger.info(
            "Chromium launched (pid=%d) on port %d",
            self._process.pid,
            self._config.debug_port,
        )
        await asyncio.sleep(2)

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise RuntimeError(
                "playwright required: pip install playwright && playwright install chromium"
            )

        self._playwright = await async_playwright().__aenter__()
        self._browser = await self._playwright.chromium.connect_over_cdp(
            f"http://localhost:{self._config.debug_port}"
        )
        self._context = self._browser.contexts[0]
        self._page = (
            self._context.pages[0]
            if self._context.pages
            else await self._context.new_page()
        )
        logger.info("Connected to Chromium via CDP")

    async def navigate(self, url: str) -> None:
        """Navigate to a URL."""
        if not self._page:
            raise RuntimeError("Browser not launched")
        await self._page.goto(url, wait_until="domcontentloaded")
        logger.debug("Navigated to %s", url)

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

    async def scroll_down(self, pixels: int = 300) -> None:
        """Scroll down with natural variation."""
        if not self._page:
            raise RuntimeError("Browser not launched")
        steps = max(1, pixels // 100)
        for _ in range(steps):
            delta = random.randint(80, 150)
            await self._page.mouse.wheel(0, delta)
            await asyncio.sleep(random.uniform(0.2, 0.5))

    async def get_page_text(self) -> str:
        """Get the visible text content of the page."""
        if not self._page:
            raise RuntimeError("Browser not launched")
        return await self._page.inner_text("body")

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
        """Disconnect from browser (don't close it)."""
        try:
            if self._browser:
                await self._browser.disconnect()
                self._browser = None
        except Exception:
            logger.warning("Failed to disconnect browser", exc_info=True)
        try:
            if hasattr(self, "_playwright") and self._playwright:
                await self._playwright.__aexit__(None, None, None)
        except Exception:
            logger.warning("Failed to close playwright", exc_info=True)
        if self._process:
            self._process.terminate()
            self._process = None
