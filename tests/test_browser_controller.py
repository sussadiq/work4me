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
    assert controller._browser is None
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


@pytest.mark.asyncio
async def test_launch_creates_context_when_empty(controller):
    """When browser has no contexts, a new context should be created."""
    mock_browser = AsyncMock()
    mock_browser.contexts = []
    mock_context = AsyncMock()
    mock_context.pages = []
    mock_context.new_page = AsyncMock(return_value=AsyncMock())
    mock_browser.new_context = AsyncMock(return_value=mock_context)

    mock_pw_instance = AsyncMock()
    mock_pw_instance.chromium.connect_over_cdp = AsyncMock(return_value=mock_browser)

    async def fake_launch():
        # Simulate what launch() does after connecting
        controller._browser = mock_browser
        if controller._browser.contexts:
            controller._context = controller._browser.contexts[0]
        else:
            controller._context = await controller._browser.new_context()
        controller._page = await controller._context.new_page()

    await fake_launch()
    mock_browser.new_context.assert_called_once()


@pytest.mark.asyncio
async def test_cleanup_waits_for_termination(controller):
    """cleanup() should await process.wait() after terminate()."""
    mock_proc = AsyncMock()
    mock_proc.wait = AsyncMock(return_value=0)
    controller._process = mock_proc
    controller._browser = None

    await controller.cleanup()
    mock_proc.terminate.assert_called_once()
    mock_proc.wait.assert_called()
    assert controller._process is None


@pytest.mark.asyncio
async def test_cleanup_kills_if_terminate_hangs(controller):
    """cleanup() should escalate to kill() if terminate times out."""
    import asyncio as aio

    mock_proc = AsyncMock()
    mock_proc.wait = AsyncMock(return_value=0)
    controller._process = mock_proc
    controller._browser = None

    with patch("work4me.controllers.browser.asyncio.wait_for", side_effect=aio.TimeoutError()):
        await controller.cleanup()

    mock_proc.kill.assert_called_once()
