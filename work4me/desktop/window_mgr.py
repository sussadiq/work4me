"""Window management for switching focus between applications.

Uses compositor-specific methods to raise and focus windows by WM_CLASS.
GNOME/Mutter: gdbus call to bundled work4me-focus extension which exposes
  com.work4me.WindowFocus.ActivateByWmClass via D-Bus.
Sway: stub for future swaymsg implementation.
Null: no-op fallback when no compositor is detected.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
from typing import Protocol

logger = logging.getLogger(__name__)


class WindowManager(Protocol):
    """Protocol for compositor-specific window management."""

    async def focus_window(self, window_class: str, *, title_hint: str = "") -> bool: ...
    async def health_check(self) -> bool: ...


class GnomeWindowManager:
    """Focus windows on GNOME/Mutter via bundled work4me-focus extension.

    Calls com.work4me.WindowFocus.ActivateByWmClass over D-Bus.
    The extension runs inside GNOME Shell, bypassing focus-stealing
    restrictions and handling cross-workspace activation.
    """

    _DBUS_DEST = "org.gnome.Shell"
    _DBUS_PATH = "/com/work4me/WindowFocus"
    _DBUS_METHOD = "com.work4me.WindowFocus.ActivateByWmClass"
    _DBUS_METHOD_TITLE = "com.work4me.WindowFocus.ActivateByWmClassAndTitle"

    def __init__(self) -> None:
        self._gdbus_path = shutil.which("gdbus")
        self._available: bool | None = None  # None = not yet checked

    async def focus_window(self, window_class: str, *, title_hint: str = "") -> bool:
        """Activate a window matching wm_class, optionally by title substring."""
        if self._available is False:
            return False
        if not self._gdbus_path:
            self._mark_unavailable("gdbus not found")
            return False

        if title_hint:
            result = await self._call_dbus(
                self._DBUS_METHOD_TITLE, window_class, title_hint,
            )
            if result is not None:
                return result
            # New method not available (old extension) — fall back
            logger.debug("ActivateByWmClassAndTitle unavailable, falling back")

        return await self._call_dbus(self._DBUS_METHOD, window_class) or False

    async def _call_dbus(self, method: str, *args: str) -> bool | None:
        """Call a D-Bus method. Returns True/False on success, None if method missing."""
        try:
            proc = await asyncio.create_subprocess_exec(
                self._gdbus_path,  # type: ignore[arg-type]
                "call", "--session",
                "--dest", self._DBUS_DEST,
                "--object-path", self._DBUS_PATH,
                "--method", method,
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=5.0)
        except asyncio.TimeoutError:
            logger.warning("gdbus %s timed out", method.rpartition(".")[-1])
            return False
        except OSError as exc:
            self._mark_unavailable(f"gdbus exec failed: {exc}")
            return False

        if proc.returncode != 0:
            err = stderr.decode(errors="replace").strip()
            if "not found" in err or "does not exist" in err:
                if method == self._DBUS_METHOD_TITLE:
                    return None  # Method missing — caller should fall back
                self._mark_unavailable(f"Extension unavailable: {err}")
            else:
                logger.debug("gdbus %s failed: %s", method.rpartition(".")[-1], err)
            return False

        output = stdout.decode(errors="replace")
        if "(true,)" in output:
            self._available = True
            return True

        return False

    async def health_check(self) -> bool:
        """Return True if the work4me-focus extension is reachable."""
        if self._available is not None:
            return self._available
        if not self._gdbus_path:
            self._available = False
            return False

        # Introspect the extension path — no side effects
        try:
            proc = await asyncio.create_subprocess_exec(
                self._gdbus_path,
                "introspect", "--session",
                "--dest", self._DBUS_DEST,
                "--object-path", self._DBUS_PATH,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=5.0)
        except (asyncio.TimeoutError, OSError):
            self._available = False
            return False

        if proc.returncode == 0 and b"ActivateByWmClass" in stdout:
            self._available = True
        else:
            self._available = False
        return self._available

    def _mark_unavailable(self, reason: str) -> None:
        if self._available is not False:
            logger.info("GNOME window management unavailable: %s", reason)
            self._available = False


class SwayWindowManager:
    """Stub for Sway compositor — future swaymsg implementation."""

    async def focus_window(self, window_class: str, *, title_hint: str = "") -> bool:
        return False

    async def health_check(self) -> bool:
        return False


class NullWindowManager:
    """No-op fallback when no supported compositor is detected."""

    async def focus_window(self, window_class: str, *, title_hint: str = "") -> bool:
        return False

    async def health_check(self) -> bool:
        return False


def detect_window_manager() -> GnomeWindowManager | SwayWindowManager | NullWindowManager:
    """Detect compositor and return appropriate WindowManager implementation."""
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").upper()

    if "GNOME" in desktop:
        logger.info("Detected GNOME — using GnomeWindowManager")
        return GnomeWindowManager()

    if desktop == "SWAY" or shutil.which("swaymsg"):
        logger.info("Detected Sway — using SwayWindowManager (stub)")
        return SwayWindowManager()

    logger.info("No supported compositor detected — using NullWindowManager")
    return NullWindowManager()
