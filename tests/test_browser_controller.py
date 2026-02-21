# tests/test_browser_controller.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import quote_plus
from work4me.controllers.browser import BrowserController, COOKIE_SELECTORS
from work4me.config import BrowserConfig

@pytest.fixture
def config():
    return BrowserConfig()

@pytest.fixture
def controller(config):
    return BrowserController(config)

def test_controller_init(controller):
    assert controller._context is None
    assert controller._page is None


@pytest.mark.asyncio
async def test_navigate_calls_goto(controller):
    mock_page = AsyncMock()
    controller._page = mock_page
    await controller.navigate("https://example.com")
    mock_page.goto.assert_called_with(
        "https://example.com", wait_until="domcontentloaded", timeout=15000.0,
    )

@pytest.mark.asyncio
async def test_search_types_query(controller):
    mock_page = AsyncMock()
    mock_page.url = "https://www.google.com"
    controller._page = mock_page
    controller.navigate = AsyncMock()
    await controller.search("jwt middleware express")
    url_arg = controller.navigate.call_args[0][0]
    assert "google.com/search" in url_arg
    assert quote_plus("jwt middleware express") in url_arg

@pytest.mark.asyncio
async def test_scroll_down(controller):
    mock_page = AsyncMock()
    controller._page = mock_page
    await controller.scroll_down(pixels=300)
    mock_page.mouse.wheel.assert_called()

@pytest.mark.asyncio
async def test_get_page_text(controller):
    mock_page = AsyncMock()
    mock_page.inner_text = AsyncMock(return_value="Hello world content")
    controller._page = mock_page
    text = await controller.get_page_text()
    assert "Hello" in text

@pytest.mark.asyncio
async def test_health_check_no_browser(controller):
    assert await controller.health_check() is False


@pytest.mark.asyncio
async def test_restart_relaunches(controller):
    with patch.object(controller, 'cleanup', new_callable=AsyncMock) as mock_cleanup, \
         patch.object(controller, 'launch', new_callable=AsyncMock) as mock_launch:
        await controller.restart()
        mock_cleanup.assert_called_once()
        mock_launch.assert_called_once()


@pytest.mark.asyncio
async def test_search_url_encodes_special_chars(controller):
    """Special characters in search query must be URL-encoded."""
    controller._page = AsyncMock()
    controller.navigate = AsyncMock()
    await controller.search("C++ & generics")
    url_arg = controller.navigate.call_args[0][0]
    assert quote_plus("C++ & generics") in url_arg


def test_browser_available_flag_defaults_false(controller):
    """_browser_available defaults to False."""
    assert controller._browser_available is False


# --- Firefox / Playwright launch tests ---


@pytest.mark.asyncio
async def test_launch_uses_persistent_context():
    """launch() should use firefox.launch_persistent_context(headless=False)."""
    config = BrowserConfig()
    ctrl = BrowserController(config)

    mock_page = AsyncMock()
    mock_context = AsyncMock()
    mock_context.pages = [mock_page]

    mock_pw_instance = AsyncMock()
    mock_pw_instance.firefox.launch_persistent_context = AsyncMock(
        return_value=mock_context
    )

    mock_pw_cm = AsyncMock()
    mock_pw_cm.__aenter__ = AsyncMock(return_value=mock_pw_instance)

    with patch.dict(
        "sys.modules",
        {
            "playwright": MagicMock(),
            "playwright.async_api": MagicMock(async_playwright=lambda: mock_pw_cm),
        },
    ):
        await ctrl.launch()

    mock_pw_instance.firefox.launch_persistent_context.assert_called_once_with(
        "", headless=False, no_viewport=True, timeout=30000.0,
        firefox_user_prefs={"dom.webdriver.enabled": False},
    )
    assert ctrl._browser_available is True
    assert ctrl._page is mock_page


@pytest.mark.asyncio
async def test_launch_with_user_data_dir():
    """launch() should pass user_data_dir to launch_persistent_context."""
    config = BrowserConfig(user_data_dir="/home/user/.firefox-profile")
    ctrl = BrowserController(config)

    mock_page = AsyncMock()
    mock_context = AsyncMock()
    mock_context.pages = [mock_page]

    mock_pw_instance = AsyncMock()
    mock_pw_instance.firefox.launch_persistent_context = AsyncMock(
        return_value=mock_context
    )

    mock_pw_cm = AsyncMock()
    mock_pw_cm.__aenter__ = AsyncMock(return_value=mock_pw_instance)

    with patch.dict(
        "sys.modules",
        {
            "playwright": MagicMock(),
            "playwright.async_api": MagicMock(async_playwright=lambda: mock_pw_cm),
        },
    ):
        await ctrl.launch()

    call_args = mock_pw_instance.firefox.launch_persistent_context.call_args
    assert call_args[0][0] == "/home/user/.firefox-profile"


@pytest.mark.asyncio
async def test_launch_without_user_data_dir():
    """launch() should pass empty string when user_data_dir is empty."""
    config = BrowserConfig(user_data_dir="")
    ctrl = BrowserController(config)

    mock_page = AsyncMock()
    mock_context = AsyncMock()
    mock_context.pages = [mock_page]

    mock_pw_instance = AsyncMock()
    mock_pw_instance.firefox.launch_persistent_context = AsyncMock(
        return_value=mock_context
    )

    mock_pw_cm = AsyncMock()
    mock_pw_cm.__aenter__ = AsyncMock(return_value=mock_pw_instance)

    with patch.dict(
        "sys.modules",
        {
            "playwright": MagicMock(),
            "playwright.async_api": MagicMock(async_playwright=lambda: mock_pw_cm),
        },
    ):
        await ctrl.launch()

    call_args = mock_pw_instance.firefox.launch_persistent_context.call_args
    assert call_args[0][0] == ""


@pytest.mark.asyncio
async def test_launch_creates_page_when_context_empty():
    """When context has no pages, launch() should call new_page()."""
    config = BrowserConfig()
    ctrl = BrowserController(config)

    mock_new_page = AsyncMock()
    mock_context = AsyncMock()
    mock_context.pages = []
    mock_context.new_page = AsyncMock(return_value=mock_new_page)

    mock_pw_instance = AsyncMock()
    mock_pw_instance.firefox.launch_persistent_context = AsyncMock(
        return_value=mock_context
    )

    mock_pw_cm = AsyncMock()
    mock_pw_cm.__aenter__ = AsyncMock(return_value=mock_pw_instance)

    with patch.dict(
        "sys.modules",
        {
            "playwright": MagicMock(),
            "playwright.async_api": MagicMock(async_playwright=lambda: mock_pw_cm),
        },
    ):
        await ctrl.launch()

    mock_context.new_page.assert_called_once()
    assert ctrl._page is mock_new_page


@pytest.mark.asyncio
async def test_launch_injects_webdriver_stealth_script():
    """launch() should inject an init script that masks navigator.webdriver."""
    config = BrowserConfig()
    ctrl = BrowserController(config)

    mock_page = AsyncMock()
    mock_context = AsyncMock()
    mock_context.pages = [mock_page]

    mock_pw_instance = AsyncMock()
    mock_pw_instance.firefox.launch_persistent_context = AsyncMock(
        return_value=mock_context
    )

    mock_pw_cm = AsyncMock()
    mock_pw_cm.__aenter__ = AsyncMock(return_value=mock_pw_instance)

    with patch.dict(
        "sys.modules",
        {
            "playwright": MagicMock(),
            "playwright.async_api": MagicMock(async_playwright=lambda: mock_pw_cm),
        },
    ):
        await ctrl.launch()

    mock_context.add_init_script.assert_called_once()
    script = mock_context.add_init_script.call_args[0][0]
    assert "navigator" in script
    assert "webdriver" in script


@pytest.mark.asyncio
async def test_launch_raises_on_playwright_import_error():
    """launch() should raise RuntimeError when playwright is not installed."""
    config = BrowserConfig()
    ctrl = BrowserController(config)

    with patch.dict("sys.modules", {"playwright": None, "playwright.async_api": None}):
        with pytest.raises(RuntimeError, match="playwright required"):
            await ctrl.launch()


@pytest.mark.asyncio
async def test_cleanup_closes_context():
    """cleanup() should call context.close()."""
    config = BrowserConfig()
    ctrl = BrowserController(config)

    mock_context = AsyncMock()
    ctrl._context = mock_context
    ctrl._browser_available = True

    await ctrl.cleanup()

    mock_context.close.assert_called_once()
    assert ctrl._context is None
    assert ctrl._browser_available is False


@pytest.mark.asyncio
async def test_cleanup_stops_playwright():
    """cleanup() should call playwright.stop()."""
    config = BrowserConfig()
    ctrl = BrowserController(config)

    mock_pw = AsyncMock()
    ctrl._playwright = mock_pw
    ctrl._browser_available = True

    await ctrl.cleanup()

    mock_pw.stop.assert_called_once()


@pytest.mark.asyncio
async def test_cleanup_handles_context_close_error():
    """cleanup() should handle errors when closing context."""
    config = BrowserConfig()
    ctrl = BrowserController(config)

    mock_context = AsyncMock()
    mock_context.close = AsyncMock(side_effect=Exception("close failed"))
    ctrl._context = mock_context

    mock_pw = AsyncMock()
    ctrl._playwright = mock_pw

    await ctrl.cleanup()

    # Should still attempt to stop playwright despite context close failure
    mock_pw.stop.assert_called_once()
    assert ctrl._browser_available is False


# --- New browser interaction tests ---


@pytest.fixture
def ready_controller():
    """Controller with mock page and mouse already set up."""
    config = BrowserConfig()
    ctrl = BrowserController(config)
    ctrl._page = AsyncMock()
    ctrl._context = AsyncMock()
    ctrl._browser_available = True
    ctrl._mouse = AsyncMock()
    ctrl._captcha_detector = AsyncMock()
    ctrl._captcha_solver = AsyncMock()
    return ctrl


@pytest.mark.asyncio
async def test_click_uses_browser_mouse(ready_controller):
    """click() should use BrowserMouse when available."""
    await ready_controller.click("button.submit")
    ready_controller._mouse.click_element.assert_called_once_with(
        ready_controller._page, "button.submit", timeout=5000
    )


@pytest.mark.asyncio
async def test_click_fallback_without_mouse(ready_controller):
    """click() should fall back to page.click when no BrowserMouse."""
    ready_controller._mouse = None
    await ready_controller.click("button.submit")
    ready_controller._page.click.assert_called_once_with("button.submit", timeout=5000)


@pytest.mark.asyncio
async def test_click_link(ready_controller):
    """click_link() should find link by text and click."""
    await ready_controller.click_link("Documentation")
    ready_controller._mouse.click_element.assert_called_once()
    selector_arg = ready_controller._mouse.click_element.call_args[0][1]
    assert "Documentation" in selector_arg


@pytest.mark.asyncio
async def test_fill_field(ready_controller):
    """fill_field() should click, clear, and type with delay."""
    await ready_controller.fill_field("#email", "test@example.com")
    ready_controller._mouse.click_element.assert_called_once()
    ready_controller._page.fill.assert_called_once_with("#email", "")
    ready_controller._page.type.assert_called_once_with(
        "#email", "test@example.com", delay=85
    )


@pytest.mark.asyncio
async def test_dismiss_cookie_banner_finds_accept(ready_controller):
    """dismiss_cookie_banner() should click first visible cookie button."""
    mock_locator = AsyncMock()
    mock_locator.is_visible = AsyncMock(return_value=True)
    # page.locator() is synchronous in Playwright
    mock_loc_chain = MagicMock()
    mock_loc_chain.first = mock_locator
    ready_controller._page.locator = MagicMock(return_value=mock_loc_chain)

    result = await ready_controller.dismiss_cookie_banner()
    assert result is True
    ready_controller._mouse.click_element.assert_called_once()


@pytest.mark.asyncio
async def test_dismiss_cookie_banner_none_found(ready_controller):
    """dismiss_cookie_banner() should return False when no banner found."""
    mock_locator = AsyncMock()
    mock_locator.is_visible = AsyncMock(return_value=False)
    mock_loc_chain = MagicMock()
    mock_loc_chain.first = mock_locator
    ready_controller._page.locator = MagicMock(return_value=mock_loc_chain)

    result = await ready_controller.dismiss_cookie_banner()
    assert result is False


@pytest.mark.asyncio
async def test_handle_captcha_none_detected(ready_controller):
    """handle_captcha() should return False when no CAPTCHA detected."""
    ready_controller._captcha_detector.detect = AsyncMock(return_value=None)
    result = await ready_controller.handle_captcha()
    assert result is False


@pytest.mark.asyncio
async def test_handle_captcha_detected_and_solved(ready_controller):
    """handle_captcha() should detect and solve CAPTCHA."""
    mock_captcha = MagicMock()
    mock_captcha.kind = "recaptcha"
    ready_controller._captcha_detector.detect = AsyncMock(return_value=mock_captcha)
    ready_controller._captcha_solver.solve = AsyncMock(return_value=True)

    result = await ready_controller.handle_captcha()
    assert result is True
    ready_controller._captcha_solver.solve.assert_called_once()


@pytest.mark.asyncio
async def test_navigate_with_captcha_check(ready_controller):
    """navigate_with_captcha_check() should navigate, dismiss cookies, handle CAPTCHA."""
    ready_controller.navigate = AsyncMock()
    ready_controller.dismiss_cookie_banner = AsyncMock(return_value=False)
    ready_controller.handle_captcha = AsyncMock(return_value=False)

    with patch("work4me.controllers.browser.asyncio.sleep", new_callable=AsyncMock):
        await ready_controller.navigate_with_captcha_check("https://example.com")

    ready_controller.navigate.assert_called_once_with("https://example.com")
    ready_controller.dismiss_cookie_banner.assert_called_once()
    ready_controller.handle_captcha.assert_called_once()


@pytest.mark.asyncio
async def test_screenshot(ready_controller):
    """screenshot() should call page.screenshot."""
    ready_controller._page.screenshot = AsyncMock(return_value=b"png-data")
    result = await ready_controller.screenshot()
    assert result == b"png-data"


@pytest.mark.asyncio
async def test_screenshot_with_clip(ready_controller):
    """screenshot() should pass clip parameter."""
    ready_controller._page.screenshot = AsyncMock(return_value=b"clipped")
    clip = {"x": 10, "y": 20, "width": 100, "height": 50}
    result = await ready_controller.screenshot(clip=clip)
    assert result == b"clipped"
    call_kwargs = ready_controller._page.screenshot.call_args[1]
    assert call_kwargs["clip"] == clip


@pytest.mark.asyncio
async def test_current_url(ready_controller):
    """current_url() should return the page URL."""
    ready_controller._page.url = "https://example.com/page"
    url = await ready_controller.current_url()
    assert url == "https://example.com/page"


@pytest.mark.asyncio
async def test_go_back(ready_controller):
    """go_back() should call page.go_back with navigation timeout."""
    await ready_controller.go_back()
    ready_controller._page.go_back.assert_called_once_with(timeout=15000.0)


@pytest.mark.asyncio
async def test_go_forward(ready_controller):
    """go_forward() should call page.go_forward with navigation timeout."""
    await ready_controller.go_forward()
    ready_controller._page.go_forward.assert_called_once_with(timeout=15000.0)


@pytest.mark.asyncio
async def test_get_cookies(ready_controller):
    """get_cookies() should return cookies from context."""
    ready_controller._context.cookies = AsyncMock(
        return_value=[{"name": "session", "value": "abc"}]
    )
    cookies = await ready_controller.get_cookies()
    assert len(cookies) == 1
    assert cookies[0]["name"] == "session"


@pytest.mark.asyncio
async def test_set_cookies(ready_controller):
    """set_cookies() should add cookies to context."""
    cookies = [{"name": "token", "value": "xyz", "url": "https://example.com"}]
    await ready_controller.set_cookies(cookies)
    ready_controller._context.add_cookies.assert_called_once_with(cookies)


def test_cookie_selectors_not_empty():
    """COOKIE_SELECTORS should have common accept button patterns."""
    assert len(COOKIE_SELECTORS) >= 5
    assert any("Accept" in s for s in COOKIE_SELECTORS)


@pytest.mark.asyncio
async def test_navigate_uses_custom_navigation_timeout():
    """navigate() should respect a custom navigation_timeout from config."""
    config = BrowserConfig(navigation_timeout=5000.0)
    ctrl = BrowserController(config)
    ctrl._page = AsyncMock()
    await ctrl.navigate("https://example.com")
    ctrl._page.goto.assert_called_with(
        "https://example.com", wait_until="domcontentloaded", timeout=5000.0,
    )


def test_controller_init_has_mouse_and_captcha_fields():
    """Constructor should initialize mouse/captcha fields to None."""
    ctrl = BrowserController(BrowserConfig())
    assert ctrl._mouse is None
    assert ctrl._captcha_detector is None
    assert ctrl._captcha_solver is None
