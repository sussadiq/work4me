"""Tests for BrowserMouse — Bezier + Fitts's law bridge to Playwright."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from work4me.behavior.mouse import HumanMouse, Point
from work4me.config import BrowserMouseConfig
from work4me.controllers.browser_mouse import BrowserMouse


@pytest.fixture
def config():
    return BrowserMouseConfig()


@pytest.fixture
def human_mouse():
    return HumanMouse()


@pytest.fixture
def browser_mouse(human_mouse, config):
    return BrowserMouse(human_mouse, config)


@pytest.fixture
def mock_page():
    page = AsyncMock()
    page.mouse = AsyncMock()
    # page.locator() is synchronous in Playwright, returns a Locator
    page.locator = MagicMock()
    return page


@pytest.mark.asyncio
async def test_move_to_generates_bezier_path(browser_mouse, mock_page):
    """move_to should call page.mouse.move multiple times along a Bezier path."""
    with patch("work4me.controllers.browser_mouse.asyncio.sleep", new_callable=AsyncMock):
        await browser_mouse.move_to(mock_page, 500.0, 400.0)

    # Bezier path should produce multiple intermediate points
    assert mock_page.mouse.move.call_count >= 5
    # Final tracked position should be updated
    assert browser_mouse.position.x == 500.0
    assert browser_mouse.position.y == 400.0


@pytest.mark.asyncio
async def test_move_to_short_distance(browser_mouse, mock_page):
    """Very short moves should still complete."""
    with patch("work4me.controllers.browser_mouse.asyncio.sleep", new_callable=AsyncMock):
        await browser_mouse.move_to(mock_page, 1.0, 1.0)

    assert mock_page.mouse.move.call_count >= 1


@pytest.mark.asyncio
async def test_click_at_moves_then_clicks(browser_mouse, mock_page):
    """click_at should move to position and then click."""
    with patch("work4me.controllers.browser_mouse.asyncio.sleep", new_callable=AsyncMock):
        await browser_mouse.click_at(mock_page, 200.0, 150.0)

    # Should have moved and then clicked
    assert mock_page.mouse.move.call_count >= 1
    mock_page.mouse.click.assert_called_once_with(200.0, 150.0, button="left")


@pytest.mark.asyncio
async def test_click_at_right_button(browser_mouse, mock_page):
    """click_at should support right-click."""
    with patch("work4me.controllers.browser_mouse.asyncio.sleep", new_callable=AsyncMock):
        await browser_mouse.click_at(mock_page, 100.0, 100.0, button="right")

    mock_page.mouse.click.assert_called_once_with(100.0, 100.0, button="right")


@pytest.mark.asyncio
async def test_click_element_computes_center(browser_mouse, mock_page):
    """click_element should compute bounding box center and click there."""
    mock_locator = AsyncMock()
    mock_locator.bounding_box = AsyncMock(
        return_value={"x": 100, "y": 200, "width": 80, "height": 40}
    )
    mock_page.locator.return_value.first = mock_locator

    with patch("work4me.controllers.browser_mouse.asyncio.sleep", new_callable=AsyncMock):
        with patch("work4me.controllers.browser_mouse.random.uniform", return_value=0.0):
            await browser_mouse.click_element(mock_page, "button.submit")

    mock_page.locator.assert_called_with("button.submit")
    # Center should be approximately (140, 220) with jitter=0
    click_call = mock_page.mouse.click.call_args
    assert 137 <= click_call[0][0] <= 143
    assert 217 <= click_call[0][1] <= 223


@pytest.mark.asyncio
async def test_click_element_raises_on_invisible(browser_mouse, mock_page):
    """click_element should raise ValueError when element has no bounding box."""
    mock_locator = AsyncMock()
    mock_locator.bounding_box = AsyncMock(return_value=None)
    mock_page.locator.return_value.first = mock_locator

    with pytest.raises(ValueError, match="Element not visible"):
        await browser_mouse.click_element(mock_page, ".hidden")


@pytest.mark.asyncio
async def test_micro_movement(browser_mouse, mock_page):
    """micro_movement should make a small jitter movement."""
    browser_mouse._pos = Point(500.0, 500.0)

    await browser_mouse.micro_movement(mock_page)

    mock_page.mouse.move.assert_called_once()
    # Position should have changed slightly
    new_pos = browser_mouse.position
    assert abs(new_pos.x - 500.0) < 50
    assert abs(new_pos.y - 500.0) < 50


def test_initial_position_is_origin(browser_mouse):
    """BrowserMouse should start at (0, 0)."""
    assert browser_mouse.position.x == 0.0
    assert browser_mouse.position.y == 0.0
