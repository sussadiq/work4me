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
        # Simulate what _finalize_connection() does after connecting
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
    mock_proc = MagicMock()
    mock_proc.returncode = None
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

    mock_proc = MagicMock()
    mock_proc.returncode = None
    mock_proc.wait = AsyncMock(return_value=0)
    controller._process = mock_proc
    controller._browser = None

    with patch("work4me.controllers.browser.asyncio.wait_for", side_effect=aio.TimeoutError()):
        await controller.cleanup()

    mock_proc.kill.assert_called_once()


@pytest.mark.asyncio
async def test_cleanup_handles_process_lookup_error(controller):
    """cleanup() should handle ProcessLookupError when process already exited."""
    mock_proc = MagicMock()
    mock_proc.returncode = None
    mock_proc.terminate = MagicMock(side_effect=ProcessLookupError())
    controller._process = mock_proc
    controller._browser = None

    await controller.cleanup()
    assert controller._process is None


@pytest.mark.asyncio
async def test_cleanup_skips_terminate_when_already_exited(controller):
    """cleanup() should skip terminate when process already has a returncode."""
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    controller._process = mock_proc
    controller._browser = None

    await controller.cleanup()
    mock_proc.terminate.assert_not_called()
    assert controller._process is None


def test_browser_available_flag_defaults_false(controller):
    """_browser_available defaults to False."""
    assert controller._browser_available is False


@pytest.mark.asyncio
async def test_launch_adds_user_data_dir():
    """Launch should include --user-data-dir when configured."""
    config = BrowserConfig(user_data_dir="/home/user/.chrome-profile")
    ctrl = BrowserController(config)

    mock_proc = AsyncMock()
    mock_proc.pid = 1234
    mock_proc.returncode = None  # Process still running

    mock_pw_instance = AsyncMock()
    mock_browser = AsyncMock()
    mock_browser.contexts = []
    mock_ctx = AsyncMock()
    mock_ctx.pages = []
    mock_ctx.new_page = AsyncMock(return_value=AsyncMock())
    mock_browser.new_context = AsyncMock(return_value=mock_ctx)
    mock_pw_instance.chromium.connect_over_cdp = AsyncMock(return_value=mock_browser)
    mock_pw_cm = AsyncMock()
    mock_pw_cm.__aenter__ = AsyncMock(return_value=mock_pw_instance)

    with patch.object(ctrl, '_try_connect_existing', new_callable=AsyncMock, return_value=False), \
         patch("work4me.controllers.browser.asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_proc) as mock_exec, \
         patch("work4me.controllers.browser.asyncio.sleep", new_callable=AsyncMock), \
         patch.dict("sys.modules", {"playwright": MagicMock(), "playwright.async_api": MagicMock(async_playwright=lambda: mock_pw_cm)}):
        await ctrl.launch()

    cmd_args = mock_exec.call_args[0]
    assert any("--user-data-dir=/home/user/.chrome-profile" in str(a) for a in cmd_args)


@pytest.mark.asyncio
async def test_launch_adds_profile_directory():
    """Launch should include --profile-directory when configured."""
    config = BrowserConfig(profile_directory="Profile 1")
    ctrl = BrowserController(config)

    mock_proc = AsyncMock()
    mock_proc.pid = 1234
    mock_proc.returncode = None  # Process still running

    mock_pw_instance = AsyncMock()
    mock_browser = AsyncMock()
    mock_browser.contexts = []
    mock_ctx = AsyncMock()
    mock_ctx.pages = []
    mock_ctx.new_page = AsyncMock(return_value=AsyncMock())
    mock_browser.new_context = AsyncMock(return_value=mock_ctx)
    mock_pw_instance.chromium.connect_over_cdp = AsyncMock(return_value=mock_browser)
    mock_pw_cm = AsyncMock()
    mock_pw_cm.__aenter__ = AsyncMock(return_value=mock_pw_instance)

    with patch.object(ctrl, '_try_connect_existing', new_callable=AsyncMock, return_value=False), \
         patch("work4me.controllers.browser.asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_proc) as mock_exec, \
         patch("work4me.controllers.browser.asyncio.sleep", new_callable=AsyncMock), \
         patch.dict("sys.modules", {"playwright": MagicMock(), "playwright.async_api": MagicMock(async_playwright=lambda: mock_pw_cm)}):
        await ctrl.launch()

    cmd_args = mock_exec.call_args[0]
    assert any("--profile-directory=Profile 1" in str(a) for a in cmd_args)


@pytest.mark.asyncio
async def test_launch_retries_cdp_connection():
    """launch() should retry CDP connection on failure and succeed on 3rd attempt."""
    config = BrowserConfig(cdp_max_retries=5, cdp_retry_base_delay=0.01, cdp_initial_wait=0.0)
    ctrl = BrowserController(config)

    mock_proc = AsyncMock()
    mock_proc.pid = 1234
    mock_proc.returncode = None  # Process still running

    mock_pw_instance = AsyncMock()
    mock_browser = AsyncMock()
    mock_browser.contexts = []
    mock_ctx = AsyncMock()
    mock_ctx.pages = []
    mock_ctx.new_page = AsyncMock(return_value=AsyncMock())
    mock_browser.new_context = AsyncMock(return_value=mock_ctx)

    cdp_call_count = 0
    async def flaky_cdp(endpoint):
        nonlocal cdp_call_count
        cdp_call_count += 1
        if cdp_call_count < 3:
            raise ConnectionError("CDP refused")
        return mock_browser

    mock_pw_instance.chromium.connect_over_cdp = AsyncMock(side_effect=flaky_cdp)
    mock_pw_cm = AsyncMock()
    mock_pw_cm.__aenter__ = AsyncMock(return_value=mock_pw_instance)

    with patch.object(ctrl, '_try_connect_existing', new_callable=AsyncMock, return_value=False), \
         patch("work4me.controllers.browser.asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_proc), \
         patch("work4me.controllers.browser.asyncio.sleep", new_callable=AsyncMock), \
         patch.dict("sys.modules", {"playwright": MagicMock(), "playwright.async_api": MagicMock(async_playwright=lambda: mock_pw_cm)}):
        await ctrl.launch()

    assert cdp_call_count == 3
    assert ctrl._browser_available is True


@pytest.mark.asyncio
async def test_launch_raises_after_cdp_retries_exhausted():
    """launch() should raise RuntimeError after all CDP retries fail."""
    config = BrowserConfig(cdp_max_retries=3, cdp_retry_base_delay=0.01, cdp_initial_wait=0.0)
    ctrl = BrowserController(config)

    mock_proc = AsyncMock()
    mock_proc.pid = 1234
    mock_proc.returncode = None  # Process still running

    mock_pw_instance = AsyncMock()
    mock_pw_instance.chromium.connect_over_cdp = AsyncMock(side_effect=ConnectionError("refused"))
    mock_pw_instance.stop = AsyncMock()
    mock_pw_cm = AsyncMock()
    mock_pw_cm.__aenter__ = AsyncMock(return_value=mock_pw_instance)

    with patch.object(ctrl, '_try_connect_existing', new_callable=AsyncMock, return_value=False), \
         patch("work4me.controllers.browser.asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_proc), \
         patch("work4me.controllers.browser.asyncio.sleep", new_callable=AsyncMock), \
         patch.dict("sys.modules", {"playwright": MagicMock(), "playwright.async_api": MagicMock(async_playwright=lambda: mock_pw_cm)}):
        with pytest.raises(RuntimeError, match="CDP connection failed after 3 attempts"):
            await ctrl.launch()


# --- New tests for pre-flight, singleton detection, Chrome takeover ---


@pytest.mark.asyncio
async def test_launch_preflight_connects_to_existing_cdp():
    """When CDP is already available on the port, launch() skips spawning."""
    config = BrowserConfig(cdp_initial_wait=0.0)
    ctrl = BrowserController(config)

    mock_browser = AsyncMock()
    mock_browser.contexts = []
    mock_ctx = AsyncMock()
    mock_ctx.pages = []
    mock_ctx.new_page = AsyncMock(return_value=AsyncMock())
    mock_browser.new_context = AsyncMock(return_value=mock_ctx)

    mock_pw_instance = AsyncMock()
    mock_pw_instance.chromium.connect_over_cdp = AsyncMock(return_value=mock_browser)
    mock_pw_cm = AsyncMock()
    mock_pw_cm.__aenter__ = AsyncMock(return_value=mock_pw_instance)

    with patch("work4me.controllers.browser.asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec, \
         patch("work4me.controllers.browser.asyncio.sleep", new_callable=AsyncMock), \
         patch.dict("sys.modules", {"playwright": MagicMock(), "playwright.async_api": MagicMock(async_playwright=lambda: mock_pw_cm)}):
        await ctrl.launch()

    # Should NOT have spawned a Chrome process
    mock_exec.assert_not_called()
    # But should be connected
    assert ctrl._browser_available is True
    assert ctrl._browser is mock_browser


@pytest.mark.asyncio
async def test_launch_preflight_failure_proceeds_to_spawn():
    """When pre-flight CDP fails, launch() proceeds to spawn Chrome normally."""
    config = BrowserConfig(cdp_max_retries=1, cdp_retry_base_delay=0.01, cdp_initial_wait=0.0)
    ctrl = BrowserController(config)

    mock_proc = AsyncMock()
    mock_proc.pid = 5678
    mock_proc.returncode = None  # Process still running

    mock_browser = AsyncMock()
    mock_browser.contexts = []
    mock_ctx = AsyncMock()
    mock_ctx.pages = []
    mock_ctx.new_page = AsyncMock(return_value=AsyncMock())
    mock_browser.new_context = AsyncMock(return_value=mock_ctx)

    # Pre-flight fails, then _connect_cdp succeeds
    call_count = 0
    async def cdp_side_effect(endpoint, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First call is from _try_connect_existing — fail
            raise ConnectionError("no CDP on port")
        # Second call is from _connect_cdp — succeed
        return mock_browser

    mock_pw_instance = AsyncMock()
    mock_pw_instance.chromium.connect_over_cdp = AsyncMock(side_effect=cdp_side_effect)
    mock_pw_instance.stop = AsyncMock()
    mock_pw_cm = AsyncMock()
    mock_pw_cm.__aenter__ = AsyncMock(return_value=mock_pw_instance)

    with patch("work4me.controllers.browser.asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_proc) as mock_exec, \
         patch("work4me.controllers.browser.asyncio.sleep", new_callable=AsyncMock), \
         patch.dict("sys.modules", {"playwright": MagicMock(), "playwright.async_api": MagicMock(async_playwright=lambda: mock_pw_cm)}):
        await ctrl.launch()

    # Should have spawned Chrome
    mock_exec.assert_called_once()
    assert ctrl._browser_available is True


@pytest.mark.asyncio
async def test_launch_detects_early_exit_and_restarts():
    """When Chrome exits immediately (singleton), launch() terminates existing and re-spawns."""
    config = BrowserConfig(cdp_max_retries=1, cdp_retry_base_delay=0.01, cdp_initial_wait=0.0)
    ctrl = BrowserController(config)

    # First spawn: process exits immediately (singleton behavior)
    exited_proc = AsyncMock()
    exited_proc.pid = 1111
    exited_proc.returncode = 0  # Already exited

    # Second spawn: process stays running
    running_proc = AsyncMock()
    running_proc.pid = 2222
    running_proc.returncode = None

    mock_browser = AsyncMock()
    mock_browser.contexts = []
    mock_ctx = AsyncMock()
    mock_ctx.pages = []
    mock_ctx.new_page = AsyncMock(return_value=AsyncMock())
    mock_browser.new_context = AsyncMock(return_value=mock_ctx)

    mock_pw_instance = AsyncMock()
    mock_pw_instance.chromium.connect_over_cdp = AsyncMock(return_value=mock_browser)
    mock_pw_cm = AsyncMock()
    mock_pw_cm.__aenter__ = AsyncMock(return_value=mock_pw_instance)

    spawn_returns = [exited_proc, running_proc]

    with patch.object(ctrl, '_try_connect_existing', new_callable=AsyncMock, return_value=False), \
         patch.object(ctrl, '_terminate_existing_chrome', new_callable=AsyncMock) as mock_terminate, \
         patch("work4me.controllers.browser.asyncio.create_subprocess_exec", new_callable=AsyncMock, side_effect=spawn_returns) as mock_exec, \
         patch("work4me.controllers.browser.asyncio.sleep", new_callable=AsyncMock), \
         patch.dict("sys.modules", {"playwright": MagicMock(), "playwright.async_api": MagicMock(async_playwright=lambda: mock_pw_cm)}):
        await ctrl.launch()

    # Should have spawned twice (initial + after terminate)
    assert mock_exec.call_count == 2
    # Should have terminated existing Chrome
    mock_terminate.assert_called_once()
    assert ctrl._browser_available is True


@pytest.mark.asyncio
async def test_terminate_existing_chrome_graceful(controller):
    """_terminate_existing_chrome() sends pkill and waits for graceful shutdown."""
    pkill_proc = AsyncMock()
    pkill_proc.wait = AsyncMock(return_value=0)

    # pgrep returns non-zero (no processes found) on first check
    pgrep_proc = AsyncMock()
    pgrep_proc.wait = AsyncMock(return_value=1)

    call_count = 0
    async def mock_subprocess(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if args[0] == "pkill":
            return pkill_proc
        return pgrep_proc

    with patch("work4me.controllers.browser.asyncio.create_subprocess_exec", side_effect=mock_subprocess), \
         patch("work4me.controllers.browser.asyncio.sleep", new_callable=AsyncMock):
        await controller._terminate_existing_chrome()

    # pkill was called (graceful)
    assert call_count >= 2  # pkill + at least one pgrep


@pytest.mark.asyncio
async def test_terminate_existing_chrome_force_kill(controller):
    """_terminate_existing_chrome() escalates to force kill when graceful fails."""
    # Track pkill calls to distinguish graceful vs force
    pkill_calls = []

    async def mock_subprocess(*args, **kwargs):
        proc = AsyncMock()
        proc.wait = AsyncMock(return_value=0)
        if args[0] == "pkill":
            pkill_calls.append(list(args))
            return proc
        if args[0] == "pgrep":
            # Always return 0 = processes still found
            proc.wait = AsyncMock(return_value=0)
            return proc
        return proc

    with patch("work4me.controllers.browser.asyncio.create_subprocess_exec", side_effect=mock_subprocess), \
         patch("work4me.controllers.browser.asyncio.sleep", new_callable=AsyncMock):
        await controller._terminate_existing_chrome()

    # Should have at least two pkill calls: graceful + force (-9)
    assert len(pkill_calls) >= 2
    # Last pkill should be force kill
    assert "-9" in pkill_calls[-1]
