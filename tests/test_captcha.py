"""Tests for CAPTCHA detection and solving."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from work4me.config import CaptchaConfig
from work4me.controllers.captcha import (
    CAPTCHA_SELECTORS,
    CaptchaDetector,
    CaptchaInfo,
    CaptchaSolution,
    CaptchaSolver,
)


# ------------------------------------------------------------------
# CaptchaDetector tests
# ------------------------------------------------------------------


@pytest.fixture
def detector():
    return CaptchaDetector()


@pytest.mark.asyncio
async def test_detect_recaptcha_iframe(detector):
    """Should detect reCAPTCHA iframe and return 'recaptcha' kind."""
    mock_page = AsyncMock()
    mock_locator = AsyncMock()
    mock_locator.bounding_box = AsyncMock(
        return_value={"x": 10, "y": 20, "width": 300, "height": 80}
    )

    def locator_side_effect(selector):
        mock = MagicMock()
        if selector == "iframe[src*='recaptcha']":
            mock.first = mock_locator
        else:
            failing = AsyncMock()
            failing.bounding_box = AsyncMock(side_effect=Exception("not found"))
            mock.first = failing
        return mock

    mock_page.locator = locator_side_effect

    result = await detector.detect(mock_page)
    assert result is not None
    assert result.kind == "recaptcha"
    assert result.box["width"] == 300


@pytest.mark.asyncio
async def test_detect_hcaptcha(detector):
    """Should detect hCaptcha element."""
    mock_page = AsyncMock()

    call_count = 0

    def locator_side_effect(selector):
        nonlocal call_count
        mock = MagicMock()
        if ".h-captcha" in selector:
            loc = AsyncMock()
            loc.bounding_box = AsyncMock(
                return_value={"x": 0, "y": 0, "width": 200, "height": 60}
            )
            mock.first = loc
        else:
            loc = AsyncMock()
            loc.bounding_box = AsyncMock(return_value=None)
            mock.first = loc
        call_count += 1
        return mock

    mock_page.locator = locator_side_effect

    result = await detector.detect(mock_page)
    assert result is not None
    assert result.kind == "hcaptcha"


@pytest.mark.asyncio
async def test_detect_no_captcha(detector):
    """Should return None when no CAPTCHA is present."""
    mock_page = AsyncMock()

    def locator_side_effect(selector):
        mock = MagicMock()
        loc = AsyncMock()
        loc.bounding_box = AsyncMock(return_value=None)
        mock.first = loc
        return mock

    mock_page.locator = locator_side_effect

    result = await detector.detect(mock_page)
    assert result is None


@pytest.mark.asyncio
async def test_detect_handles_exceptions(detector):
    """Should gracefully handle exceptions from locator calls."""
    mock_page = AsyncMock()

    def locator_side_effect(selector):
        mock = MagicMock()
        loc = AsyncMock()
        loc.bounding_box = AsyncMock(side_effect=Exception("timeout"))
        mock.first = loc
        return mock

    mock_page.locator = locator_side_effect

    result = await detector.detect(mock_page)
    assert result is None


# ------------------------------------------------------------------
# CaptchaSolver tests
# ------------------------------------------------------------------


@pytest.fixture
def solver():
    return CaptchaSolver(CaptchaConfig())


@pytest.fixture
def captcha_info():
    return CaptchaInfo(
        kind="recaptcha",
        selector="iframe[src*='recaptcha']",
        box={"x": 10, "y": 20, "width": 300, "height": 80},
    )


@pytest.mark.asyncio
async def test_solve_screenshots_and_calls_claude(solver, captcha_info):
    """solve should screenshot the CAPTCHA area, call Claude, and execute steps."""
    mock_page = AsyncMock()
    mock_page.screenshot = AsyncMock(return_value=b"fake-png-data")

    mock_mouse = AsyncMock()

    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text='{"steps": [{"action": "click", "x": 150, "y": 40}]}')]
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    solver._client = mock_client

    result = await solver.solve(mock_page, mock_mouse, captcha_info)

    mock_page.screenshot.assert_called_once()
    mock_client.messages.create.assert_called_once()
    mock_mouse.click_at.assert_called_once()
    assert result is True


@pytest.mark.asyncio
async def test_solve_returns_false_on_api_error(solver, captcha_info):
    """solve should return False when the Claude API call fails."""
    mock_page = AsyncMock()
    mock_page.screenshot = AsyncMock(return_value=b"fake-png-data")
    mock_mouse = AsyncMock()

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(side_effect=Exception("API error"))
    solver._client = mock_client

    result = await solver.solve(mock_page, mock_mouse, captcha_info)
    assert result is False


@pytest.mark.asyncio
async def test_solve_disabled_returns_false(captcha_info):
    """solve should return False when CAPTCHA solving is disabled."""
    solver = CaptchaSolver(CaptchaConfig(enabled=False))
    result = await solver.solve(AsyncMock(), AsyncMock(), captcha_info)
    assert result is False


@pytest.mark.asyncio
async def test_solve_handles_type_step(solver, captcha_info):
    """solve should handle 'type' action steps."""
    mock_page = AsyncMock()
    mock_page.screenshot = AsyncMock(return_value=b"fake-png-data")
    mock_mouse = AsyncMock()

    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.content = [
        MagicMock(text='{"steps": [{"action": "type", "text": "abc123", "selector": "#input"}]}')
    ]
    mock_client.messages.create = AsyncMock(return_value=mock_response)
    solver._client = mock_client

    result = await solver.solve(mock_page, mock_mouse, captcha_info)
    assert result is True
    mock_page.type.assert_called_once_with("#input", "abc123", delay=85)


def test_get_client_returns_none_without_anthropic(solver):
    """_get_client should return None when anthropic is not installed."""
    solver._client = None
    with patch.dict("sys.modules", {"anthropic": None}):
        client = solver._get_client()
    assert client is None


def test_captcha_selectors_not_empty():
    """The CAPTCHA_SELECTORS list should not be empty."""
    assert len(CAPTCHA_SELECTORS) >= 5
