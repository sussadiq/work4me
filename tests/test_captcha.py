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
def mock_claude():
    return AsyncMock()


@pytest.fixture
def solver(mock_claude):
    return CaptchaSolver(CaptchaConfig(), mock_claude)


@pytest.fixture
def captcha_info():
    return CaptchaInfo(
        kind="recaptcha",
        selector="iframe[src*='recaptcha']",
        box={"x": 10, "y": 20, "width": 300, "height": 80},
    )


@pytest.mark.asyncio
async def test_solve_screenshots_and_calls_claude(solver, mock_claude, captcha_info):
    """solve should screenshot the CAPTCHA area, call Claude Code, and execute steps."""
    mock_page = AsyncMock()
    mock_page.screenshot = AsyncMock(return_value=b"fake-png-data")
    mock_mouse = AsyncMock()

    mock_result = MagicMock()
    mock_result.error = ""
    mock_result.raw_text = '{"steps": [{"action": "click", "x": 150, "y": 40}]}'
    mock_claude.execute = AsyncMock(return_value=mock_result)

    result = await solver.solve(mock_page, mock_mouse, captcha_info)

    mock_page.screenshot.assert_called_once()
    mock_claude.execute.assert_called_once()
    # Verify the prompt references a temp file path and the captcha kind
    call_kwargs = mock_claude.execute.call_args
    assert "recaptcha" in call_kwargs.kwargs.get("prompt", call_kwargs[1].get("prompt", ""))
    # max_turns must be >= 3 so Claude can read the image and respond
    assert call_kwargs.kwargs.get("max_turns", call_kwargs[1].get("max_turns")) == 3
    mock_mouse.click_at.assert_called_once()
    assert result is True


@pytest.mark.asyncio
async def test_solve_returns_false_on_api_error(solver, mock_claude, captcha_info):
    """solve should return False when Claude Code CLI fails."""
    mock_page = AsyncMock()
    mock_page.screenshot = AsyncMock(return_value=b"fake-png-data")
    mock_mouse = AsyncMock()

    mock_claude.execute = AsyncMock(side_effect=Exception("CLI error"))

    result = await solver.solve(mock_page, mock_mouse, captcha_info)
    assert result is False


@pytest.mark.asyncio
async def test_solve_returns_false_on_result_error(solver, mock_claude, captcha_info):
    """solve should return False when Claude Code returns an error."""
    mock_page = AsyncMock()
    mock_page.screenshot = AsyncMock(return_value=b"fake-png-data")
    mock_mouse = AsyncMock()

    mock_result = MagicMock()
    mock_result.error = "Some error occurred"
    mock_result.raw_text = ""
    mock_claude.execute = AsyncMock(return_value=mock_result)

    result = await solver.solve(mock_page, mock_mouse, captcha_info)
    assert result is False


@pytest.mark.asyncio
async def test_solve_disabled_returns_false(mock_claude, captcha_info):
    """solve should return False when CAPTCHA solving is disabled."""
    solver = CaptchaSolver(CaptchaConfig(enabled=False), mock_claude)
    result = await solver.solve(AsyncMock(), AsyncMock(), captcha_info)
    assert result is False


@pytest.mark.asyncio
async def test_solve_handles_type_step(solver, mock_claude, captcha_info):
    """solve should handle 'type' action steps."""
    mock_page = AsyncMock()
    mock_page.screenshot = AsyncMock(return_value=b"fake-png-data")
    mock_mouse = AsyncMock()

    mock_result = MagicMock()
    mock_result.error = ""
    mock_result.raw_text = '{"steps": [{"action": "type", "text": "abc123", "selector": "#input"}]}'
    mock_claude.execute = AsyncMock(return_value=mock_result)

    result = await solver.solve(mock_page, mock_mouse, captcha_info)
    assert result is True
    mock_page.type.assert_called_once_with("#input", "abc123", delay=85)


def test_parse_solution_extracts_json(mock_claude):
    """_parse_solution should extract JSON from mixed text."""
    solver = CaptchaSolver(CaptchaConfig(), mock_claude)
    raw = 'Here is the solution: {"steps": [{"action": "click", "x": 10, "y": 20}]} done.'
    solution = solver._parse_solution(raw)
    assert solution is not None
    assert len(solution.steps) == 1
    assert solution.steps[0]["action"] == "click"


def test_parse_solution_returns_none_on_invalid(mock_claude):
    """_parse_solution should return None when no valid JSON found."""
    solver = CaptchaSolver(CaptchaConfig(), mock_claude)
    assert solver._parse_solution("no json here") is None
    assert solver._parse_solution("") is None


@pytest.mark.asyncio
async def test_ask_claude_returns_none_on_timeout(solver, mock_claude, captcha_info):
    """_ask_claude should return None when Claude Code CLI times out."""
    import asyncio

    async def slow_execute(**kwargs):
        await asyncio.sleep(999)

    mock_claude.execute = slow_execute

    # Patch the timeout to be very short so the test runs fast
    with patch("work4me.controllers.captcha.asyncio.wait_for", side_effect=asyncio.TimeoutError):
        result = await solver._ask_claude(b"fake-png", "recaptcha")
    assert result is None


def test_captcha_selectors_not_empty():
    """The CAPTCHA_SELECTORS list should not be empty."""
    assert len(CAPTCHA_SELECTORS) >= 5
