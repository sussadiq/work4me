# tests/test_browser_controller.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import quote_plus
from work4me.controllers.browser import BrowserController
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
    mock_page.goto.assert_called_with("https://example.com", wait_until="domcontentloaded")

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
        "", headless=False, timeout=30000.0,
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
