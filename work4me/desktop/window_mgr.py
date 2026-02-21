"""Window management for switching focus between applications.

Uses compositor-specific methods to raise and focus windows by WM_CLASS.
GNOME/Mutter: gdbus call to org.gnome.Shell.Eval with meta_window.activate().
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

    async def focus_window(self, window_class: str) -> bool: ...
    async def health_check(self) -> bool: ...


class GnomeWindowManager:
    """Focus windows on GNOME/Mutter via org.gnome.Shell.Eval D-Bus method."""

    def __init__(self) -> None:
        self._gdbus_path = shutil.which("gdbus")
        self._available: bool | None = None  # None = not yet checked

    async def focus_window(self, window_class: str) -> bool:
        """Activate the first window matching wm_class (case-insensitive)."""
        if self._available is False:
            return False
        if not self._gdbus_path:
            self._mark_unavailable("gdbus not found")
            return False

        sanitized = window_class.replace("'", "")

        js = (
            "global.get_window_actors().find(a => "
            f"a.meta_window.get_wm_class()?.toLowerCase() === '{sanitized.lower()}'"
            ")?.meta_window.activate(global.get_current_time())"
        )

        try:
            proc = await asyncio.create_subprocess_exec(
                self._gdbus_path,
                "call", "--session",
                "--dest", "org.gnome.Shell",
                "--object-path", "/org/gnome/Shell",
                "--method", "org.gnome.Shell.Eval",
                js,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=5.0)
        except asyncio.TimeoutError:
            logger.warning("gdbus Shell.Eval timed out")
            return False
        except OSError as exc:
            self._mark_unavailable(f"gdbus exec failed: {exc}")
            return False

        if proc.returncode != 0:
            err = stderr.decode(errors="replace").strip()
            if "not found" in err or "does not exist" in err:
                self._mark_unavailable(f"Shell.Eval unavailable: {err}")
            else:
                logger.debug("gdbus Shell.Eval failed: %s", err)
            return False

        output = stdout.decode(errors="replace")
        if "(true," in output:
            self._available = True
            return True

        return False

    async def health_check(self) -> bool:
        """Return True if gdbus and Shell.Eval are likely available."""
        if self._available is not None:
            return self._available
        if not self._gdbus_path:
            self._available = False
            return False
        # Probe with a harmless eval
        result = await self.focus_window("__health_check_nonexistent__")
        # Even if no window matched, _available is set based on D-Bus reachability
        if self._available is None:
            self._available = True
        return self._available

    def _mark_unavailable(self, reason: str) -> None:
        if self._available is not False:
            logger.info("GNOME window management unavailable: %s", reason)
            self._available = False


class SwayWindowManager:
    """Stub for Sway compositor — future swaymsg implementation."""

    async def focus_window(self, window_class: str) -> bool:
        return False

    async def health_check(self) -> bool:
        return False


class NullWindowManager:
    """No-op fallback when no supported compositor is detected."""

    async def focus_window(self, window_class: str) -> bool:
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
