"""Tests for work4me.desktop.window_mgr."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from work4me.desktop.window_mgr import (
    GnomeWindowManager,
    NullWindowManager,
    SwayWindowManager,
    detect_window_manager,
)


# ------------------------------------------------------------------
# NullWindowManager
# ------------------------------------------------------------------

async def test_null_focus_returns_false():
    mgr = NullWindowManager()
    assert await mgr.focus_window("code") is False


async def test_null_health_check_returns_false():
    mgr = NullWindowManager()
    assert await mgr.health_check() is False


# ------------------------------------------------------------------
# SwayWindowManager (stub)
# ------------------------------------------------------------------

async def test_sway_focus_returns_false():
    mgr = SwayWindowManager()
    assert await mgr.focus_window("code") is False


async def test_sway_health_check_returns_false():
    mgr = SwayWindowManager()
    assert await mgr.health_check() is False


# ------------------------------------------------------------------
# GnomeWindowManager
# ------------------------------------------------------------------

async def test_gnome_no_gdbus_returns_false():
    mgr = GnomeWindowManager()
    mgr._gdbus_path = None
    assert await mgr.focus_window("code") is False


async def test_gnome_no_gdbus_caches_unavailable():
    mgr = GnomeWindowManager()
    mgr._gdbus_path = None
    await mgr.focus_window("code")
    assert mgr._available is False
    # Second call should short-circuit
    assert await mgr.focus_window("code") is False


async def test_gnome_success():
    mgr = GnomeWindowManager()
    mgr._gdbus_path = "/usr/bin/gdbus"

    mock_proc = AsyncMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"(true, '')", b""))

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        with patch("asyncio.wait_for", return_value=(b"(true, '')", b"")):
            mock_proc.communicate = AsyncMock(return_value=(b"(true, '')", b""))
            result = await mgr.focus_window("code")

    assert result is True
    assert mgr._available is True


async def test_gnome_failure_returncode():
    mgr = GnomeWindowManager()
    mgr._gdbus_path = "/usr/bin/gdbus"

    mock_proc = AsyncMock()
    mock_proc.returncode = 1
    mock_proc.communicate = AsyncMock(return_value=(b"", b"some error"))

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        with patch("asyncio.wait_for", new_callable=AsyncMock) as mock_wait:
            mock_wait.return_value = (b"", b"some error")
            mock_proc.communicate = AsyncMock(return_value=(b"", b"some error"))
            result = await mgr.focus_window("code")

    assert result is False


async def test_gnome_shell_eval_not_found_caches():
    mgr = GnomeWindowManager()
    mgr._gdbus_path = "/usr/bin/gdbus"

    mock_proc = AsyncMock()
    mock_proc.returncode = 1
    mock_proc.communicate = AsyncMock(
        return_value=(b"", b"object not found on bus")
    )

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        with patch("asyncio.wait_for", new_callable=AsyncMock) as mock_wait:
            mock_wait.return_value = (b"", b"object not found on bus")
            mock_proc.communicate = AsyncMock(
                return_value=(b"", b"object not found on bus")
            )
            await mgr.focus_window("code")

    assert mgr._available is False


async def test_gnome_timeout():
    mgr = GnomeWindowManager()
    mgr._gdbus_path = "/usr/bin/gdbus"

    mock_proc = AsyncMock()
    mock_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError)

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
            result = await mgr.focus_window("code")

    assert result is False


async def test_gnome_oserror_caches_unavailable():
    mgr = GnomeWindowManager()
    mgr._gdbus_path = "/usr/bin/gdbus"

    with patch("asyncio.create_subprocess_exec", side_effect=OSError("no such file")):
        result = await mgr.focus_window("code")

    assert result is False
    assert mgr._available is False


async def test_gnome_sanitizes_single_quotes():
    """Single quotes in window_class should be stripped to prevent injection."""
    mgr = GnomeWindowManager()
    mgr._gdbus_path = "/usr/bin/gdbus"

    mock_proc = AsyncMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"(true, '')", b""))

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        with patch("asyncio.wait_for", new_callable=AsyncMock) as mock_wait:
            mock_wait.return_value = (b"(true, '')", b"")
            await mgr.focus_window("co'de")

    # Verify the JS passed to gdbus doesn't contain the single quote
    call_args = mock_exec.call_args[0]
    js_arg = call_args[-1]  # Last positional arg is the JS string
    assert "'" in js_arg  # JS string delimiters
    assert "co'de" not in js_arg  # Injection stripped


async def test_gnome_cached_unavailable_skips_exec():
    mgr = GnomeWindowManager()
    mgr._gdbus_path = "/usr/bin/gdbus"
    mgr._available = False  # Pre-cached as unavailable

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        result = await mgr.focus_window("code")

    assert result is False
    mock_exec.assert_not_called()


async def test_gnome_health_check_no_gdbus():
    mgr = GnomeWindowManager()
    mgr._gdbus_path = None
    assert await mgr.health_check() is False


async def test_gnome_health_check_cached():
    mgr = GnomeWindowManager()
    mgr._available = True
    assert await mgr.health_check() is True


# ------------------------------------------------------------------
# detect_window_manager()
# ------------------------------------------------------------------

def test_detect_gnome():
    with patch.dict("os.environ", {"XDG_CURRENT_DESKTOP": "GNOME"}):
        mgr = detect_window_manager()
    assert isinstance(mgr, GnomeWindowManager)


def test_detect_ubuntu_gnome():
    with patch.dict("os.environ", {"XDG_CURRENT_DESKTOP": "ubuntu:GNOME"}):
        mgr = detect_window_manager()
    assert isinstance(mgr, GnomeWindowManager)


def test_detect_sway():
    with patch.dict("os.environ", {"XDG_CURRENT_DESKTOP": "SWAY"}, clear=False):
        mgr = detect_window_manager()
    assert isinstance(mgr, SwayWindowManager)


def test_detect_sway_via_binary():
    with patch.dict("os.environ", {"XDG_CURRENT_DESKTOP": ""}, clear=False):
        with patch("shutil.which", return_value="/usr/bin/swaymsg"):
            mgr = detect_window_manager()
    assert isinstance(mgr, SwayWindowManager)


def test_detect_unknown():
    with patch.dict("os.environ", {"XDG_CURRENT_DESKTOP": "i3"}, clear=False):
        with patch("shutil.which", return_value=None):
            mgr = detect_window_manager()
    assert isinstance(mgr, NullWindowManager)
