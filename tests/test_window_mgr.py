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
    mock_proc.communicate = AsyncMock(return_value=(b"(true,)", b""))

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        with patch("asyncio.wait_for", return_value=(b"(true,)", b"")):
            result = await mgr.focus_window("Code")

    assert result is True
    assert mgr._available is True


async def test_gnome_window_not_found():
    mgr = GnomeWindowManager()
    mgr._gdbus_path = "/usr/bin/gdbus"

    mock_proc = AsyncMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"(false,)", b""))

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        with patch("asyncio.wait_for", return_value=(b"(false,)", b"")):
            result = await mgr.focus_window("NonExistent")

    assert result is False


async def test_gnome_failure_returncode():
    mgr = GnomeWindowManager()
    mgr._gdbus_path = "/usr/bin/gdbus"

    mock_proc = AsyncMock()
    mock_proc.returncode = 1
    mock_proc.communicate = AsyncMock(return_value=(b"", b"some error"))

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        with patch("asyncio.wait_for", new_callable=AsyncMock) as mock_wait:
            mock_wait.return_value = (b"", b"some error")
            result = await mgr.focus_window("code")

    assert result is False


async def test_gnome_extension_not_found_caches():
    mgr = GnomeWindowManager()
    mgr._gdbus_path = "/usr/bin/gdbus"

    mock_proc = AsyncMock()
    mock_proc.returncode = 1
    mock_proc.communicate = AsyncMock(
        return_value=(b"", b"object does not exist at path")
    )

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        with patch("asyncio.wait_for", new_callable=AsyncMock) as mock_wait:
            mock_wait.return_value = (b"", b"object does not exist at path")
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


async def test_gnome_passes_wm_class_directly():
    """wm_class is passed directly to gdbus — no JS injection concerns."""
    mgr = GnomeWindowManager()
    mgr._gdbus_path = "/usr/bin/gdbus"

    mock_proc = AsyncMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"(true,)", b""))

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        with patch("asyncio.wait_for", return_value=(b"(true,)", b"")):
            await mgr.focus_window("Code")

    call_args = mock_exec.call_args[0]
    assert call_args[-1] == "Code"  # wm_class passed as last arg
    assert "com.work4me.WindowFocus.ActivateByWmClass" in call_args


async def test_gnome_cached_unavailable_skips_exec():
    mgr = GnomeWindowManager()
    mgr._gdbus_path = "/usr/bin/gdbus"
    mgr._available = False  # Pre-cached as unavailable

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        result = await mgr.focus_window("code")

    assert result is False
    mock_exec.assert_not_called()


# ------------------------------------------------------------------
# GnomeWindowManager — title_hint matching
# ------------------------------------------------------------------

async def test_gnome_title_hint_calls_new_method():
    """When title_hint is provided, should call ActivateByWmClassAndTitle."""
    mgr = GnomeWindowManager()
    mgr._gdbus_path = "/usr/bin/gdbus"

    mock_proc = AsyncMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"(true,)", b""))

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        with patch("asyncio.wait_for", return_value=(b"(true,)", b"")):
            result = await mgr.focus_window("code", title_hint="cowork")

    assert result is True
    call_args = mock_exec.call_args[0]
    assert "ActivateByWmClassAndTitle" in call_args[-3]
    assert call_args[-2] == "code"
    assert call_args[-1] == "cowork"


async def test_gnome_title_hint_fallback_on_old_extension():
    """When new method is not found, should fall back to ActivateByWmClass."""
    mgr = GnomeWindowManager()
    mgr._gdbus_path = "/usr/bin/gdbus"

    # First call (title method) fails with "not found", second (class-only) succeeds
    call_count = 0
    async def mock_create_subprocess(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        proc = AsyncMock()
        if call_count == 1:
            proc.returncode = 1
            proc.communicate = AsyncMock(return_value=(b"", b"method not found"))
        else:
            proc.returncode = 0
            proc.communicate = AsyncMock(return_value=(b"(true,)", b""))
        return proc

    with patch("asyncio.create_subprocess_exec", side_effect=mock_create_subprocess):
        with patch("asyncio.wait_for", side_effect=[
            (b"", b"method not found"),
            (b"(true,)", b""),
        ]):
            result = await mgr.focus_window("code", title_hint="cowork")

    assert result is True
    assert call_count == 2


async def test_gnome_no_title_hint_uses_old_method():
    """When title_hint is empty, should use ActivateByWmClass directly."""
    mgr = GnomeWindowManager()
    mgr._gdbus_path = "/usr/bin/gdbus"

    mock_proc = AsyncMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"(true,)", b""))

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        with patch("asyncio.wait_for", return_value=(b"(true,)", b"")):
            result = await mgr.focus_window("code", title_hint="")

    assert result is True
    call_args = mock_exec.call_args[0]
    assert "ActivateByWmClass" in call_args[-2]
    assert "ActivateByWmClassAndTitle" not in str(call_args)


async def test_gnome_title_hint_passes_args_correctly():
    """title_hint and wm_class should be passed as separate gdbus arguments."""
    mgr = GnomeWindowManager()
    mgr._gdbus_path = "/usr/bin/gdbus"

    mock_proc = AsyncMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"(true,)", b""))

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        with patch("asyncio.wait_for", return_value=(b"(true,)", b"")):
            await mgr.focus_window("code", title_hint="my-project")

    call_args = mock_exec.call_args[0]
    # Last two positional args should be wm_class and title_substring
    assert call_args[-2] == "code"
    assert call_args[-1] == "my-project"


async def test_gnome_health_check_no_gdbus():
    mgr = GnomeWindowManager()
    mgr._gdbus_path = None
    assert await mgr.health_check() is False


async def test_gnome_health_check_cached():
    mgr = GnomeWindowManager()
    mgr._available = True
    assert await mgr.health_check() is True


async def test_gnome_health_check_introspect_success():
    mgr = GnomeWindowManager()
    mgr._gdbus_path = "/usr/bin/gdbus"

    mock_proc = AsyncMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(
        return_value=(b"interface com.work4me.WindowFocus { ActivateByWmClass }", b"")
    )

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        with patch("asyncio.wait_for", return_value=(
            b"interface com.work4me.WindowFocus { ActivateByWmClass }", b""
        )):
            result = await mgr.health_check()

    assert result is True
    assert mgr._available is True
    # Verify introspect was used, not call
    call_args = mock_exec.call_args[0]
    assert "introspect" in call_args


async def test_gnome_health_check_introspect_fails():
    mgr = GnomeWindowManager()
    mgr._gdbus_path = "/usr/bin/gdbus"

    mock_proc = AsyncMock()
    mock_proc.returncode = 1
    mock_proc.communicate = AsyncMock(return_value=(b"", b"not found"))

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        with patch("asyncio.wait_for", return_value=(b"", b"not found")):
            result = await mgr.health_check()

    assert result is False
    assert mgr._available is False


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
