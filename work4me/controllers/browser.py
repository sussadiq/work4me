"""Browser automation via Chromium CDP/Playwright."""

from __future__ import annotations

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
        self._browser_available: bool = False

    async def launch(self) -> None:
        """Launch Chromium with remote debugging and connect via Playwright.

        Flow:
        1. Pre-flight: try connecting to an existing CDP endpoint on the port.
           If successful, skip spawning a new process.
        2. Spawn Chrome with --remote-debugging-port.
        3. After initial wait, check if the process exited early (Chrome
           singleton behavior — delegated to existing instance and quit).
        4. If singleton detected: terminate existing Chrome, re-spawn.
        5. CDP retry loop to establish Playwright connection.
        """
        # Step 1: Pre-flight — try connecting to existing CDP endpoint
        if await self._try_connect_existing():
            logger.info("Connected to existing Chrome CDP on port %d", self._config.debug_port)
            return

        # Step 2: Spawn Chrome
        self._process = await self._spawn_chrome()
        await asyncio.sleep(self._config.cdp_initial_wait)

        # Step 3: Check for early exit (singleton behavior)
        if self._process.returncode is not None:
            logger.warning(
                "Chrome exited immediately (rc=%d) — singleton detected, "
                "existing Chrome is running without CDP",
                self._process.returncode,
            )
            # Step 4: Terminate existing Chrome and re-spawn
            await self._terminate_existing_chrome()
            self._process = await self._spawn_chrome()
            await asyncio.sleep(self._config.cdp_initial_wait)

        # Step 5: CDP retry loop
        await self._connect_cdp()

    async def _try_connect_existing(self) -> bool:
        """Try connecting to an existing CDP endpoint on the configured port.

        Returns True if connection succeeded and browser is ready.
        """
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return False

        try:
            self._playwright = await async_playwright().__aenter__()
            self._browser = await self._playwright.chromium.connect_over_cdp(
                f"http://localhost:{self._config.debug_port}",
                timeout=3000,
            )
        except Exception:
            # Clean up playwright on failure
            try:
                if hasattr(self, "_playwright") and self._playwright:
                    await self._playwright.stop()
                    self._playwright = None  # type: ignore[assignment]
            except Exception:
                pass
            self._browser = None
            return False

        # Connected — set up context and page
        await self._finalize_connection()
        return True

    async def _spawn_chrome(self) -> asyncio.subprocess.Process:
        """Spawn a Chrome process with remote debugging enabled."""
        cmd = [
            self._config.chromium_path,
            f"--remote-debugging-port={self._config.debug_port}",
            f"--ozone-platform={self._config.ozone_platform}",
            "--no-first-run",
            "--no-default-browser-check",
        ]
        if self._config.user_data_dir:
            cmd.append(f"--user-data-dir={self._config.user_data_dir}")
        if self._config.profile_directory:
            cmd.append(f"--profile-directory={self._config.profile_directory}")
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        logger.info(
            "Chrome spawned (pid=%d) on port %d",
            process.pid,
            self._config.debug_port,
        )
        return process

    async def _terminate_existing_chrome(self) -> None:
        """Terminate existing Chrome processes matching the configured binary."""
        binary = self._config.chromium_path
        logger.info("Terminating existing Chrome (%s) for CDP takeover", binary)

        # Graceful: pkill by binary name
        try:
            proc = await asyncio.create_subprocess_exec(
                "pkill", "-f", binary,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()
        except Exception:
            logger.warning("pkill failed", exc_info=True)
            return

        # Wait up to 5s for graceful shutdown
        for _ in range(10):
            await asyncio.sleep(0.5)
            check = await asyncio.create_subprocess_exec(
                "pgrep", "-f", binary,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            if await check.wait() != 0:
                # No processes found — Chrome is gone
                logger.info("Existing Chrome terminated gracefully")
                await asyncio.sleep(1.0)  # Allow port/lock cleanup
                return

        # Force kill
        logger.warning("Chrome didn't exit gracefully, force killing")
        try:
            proc = await asyncio.create_subprocess_exec(
                "pkill", "-9", "-f", binary,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()
        except Exception:
            logger.warning("Force kill failed", exc_info=True)
        await asyncio.sleep(1.0)  # Allow port/lock cleanup

    async def _connect_cdp(self) -> None:
        """Run the CDP retry loop to connect Playwright to Chrome."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise RuntimeError(
                "playwright required: pip install playwright && playwright install chromium"
            )

        last_exc: Exception | None = None
        for attempt in range(self._config.cdp_max_retries):
            try:
                self._playwright = await async_playwright().__aenter__()
                self._browser = await self._playwright.chromium.connect_over_cdp(
                    f"http://localhost:{self._config.debug_port}"
                )
                break  # success
            except Exception as exc:
                last_exc = exc
                if attempt < self._config.cdp_max_retries - 1:
                    wait = self._config.cdp_retry_base_delay * (2 ** attempt)
                    logger.warning(
                        "CDP connection attempt %d/%d failed, retrying in %.1fs: %s",
                        attempt + 1, self._config.cdp_max_retries, wait, exc,
                    )
                    # Clean up the failed playwright instance before retrying
                    try:
                        if hasattr(self, "_playwright") and self._playwright:
                            await self._playwright.stop()
                    except Exception:
                        pass
                    await asyncio.sleep(wait)
        else:
            raise RuntimeError(
                f"CDP connection failed after {self._config.cdp_max_retries} attempts: {last_exc}"
            )

        await self._finalize_connection()

    async def _finalize_connection(self) -> None:
        """Set up browser context and page after CDP connection."""
        if self._browser.contexts:
            self._context = self._browser.contexts[0]
        else:
            self._context = await self._browser.new_context()
        self._page = (
            self._context.pages[0]
            if self._context.pages
            else await self._context.new_page()
        )
        self._browser_available = True
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
        return str(await self._page.inner_text("body"))

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
        self._browser_available = False
        try:
            if self._browser:
                await self._browser.disconnect()
                self._browser = None
        except Exception:
            logger.warning("Failed to disconnect browser", exc_info=True)
        try:
            if hasattr(self, "_playwright") and self._playwright:
                await self._playwright.stop()
        except Exception:
            logger.warning("Failed to close playwright", exc_info=True)
        if self._process:
            if self._process.returncode is None:
                try:
                    self._process.terminate()
                except ProcessLookupError:
                    pass
                else:
                    try:
                        await asyncio.wait_for(self._process.wait(), timeout=5.0)
                    except (asyncio.TimeoutError, TimeoutError):
                        self._process.kill()
                        await self._process.wait()
            self._process = None
