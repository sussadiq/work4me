"""System health checks for Work4Me dependencies."""

import logging
import os
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

_EXT_UUID = "work4me-focus@work4me"
_EXT_INSTALL_DIR = Path.home() / ".local/share/gnome-shell/extensions" / _EXT_UUID
_EXT_BUNDLE_DIR = Path(__file__).parent / "desktop" / "gnome-ext"
_VSCODE_EXT_DIR = Path(__file__).parent.parent / "vscode-extension"


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


class DoctorChecks:
    """Run dependency and permission checks."""

    BINARIES = [
        ("python3", "Python 3.11+"),
        ("node", "Node.js 18+"),
        ("claude", "Claude Code CLI"),
        ("code", "VS Code"),
        ("ydotool", "ydotool"),
        ("wl-copy", "wl-clipboard"),
        ("gdbus", "gdbus (GNOME window management)"),
    ]

    def check_binary(self, cmd: str, label: str) -> CheckResult:
        found = shutil.which(cmd)
        if found:
            return CheckResult(label, True, found)
        return CheckResult(label, False, "NOT FOUND")

    def check_uinput(self) -> CheckResult:
        uinput = Path("/dev/uinput")
        if uinput.exists():
            try:
                mode = uinput.stat().st_mode
                if mode & 0o060:
                    return CheckResult("/dev/uinput", True, "accessible")
            except PermissionError:
                pass
        return CheckResult("/dev/uinput", False, "not accessible")

    def check_wayland(self) -> CheckResult:
        if "WAYLAND_DISPLAY" in os.environ:
            return CheckResult("Wayland", True, os.environ["WAYLAND_DISPLAY"])
        return CheckResult("Wayland", False, "not detected")

    def check_vscode_extension(self) -> CheckResult:
        # Primary: use `code --list-extensions` (authoritative for vsix installs)
        try:
            result = subprocess.run(
                ["code", "--list-extensions"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if "work4me" in line.lower():
                        return CheckResult("VS Code Extension", True, line.strip())
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        # Fallback: scan ~/.vscode/extensions/ (symlink-based dev installs)
        ext_dir = Path.home() / ".vscode" / "extensions"
        if ext_dir.exists():
            for d in ext_dir.iterdir():
                if "work4me" in d.name.lower():
                    return CheckResult("VS Code Extension", True, str(d))

        return CheckResult(
            "VS Code Extension", False,
            "not installed — run: cd vscode-extension && npm run vsix "
            "&& code --install-extension work4me-bridge-0.1.0.vsix",
        )

    def check_gnome_extension(self) -> CheckResult:
        """Check if the work4me-focus GNOME Shell extension is installed and active."""
        try:
            result = subprocess.run(
                ["gnome-extensions", "info", _EXT_UUID],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and "STATE: ACTIVE" in result.stdout.upper():
                return CheckResult("GNOME Extension", True, "active")
            if result.returncode == 0:
                return CheckResult("GNOME Extension", False, "installed but not active")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        if _EXT_INSTALL_DIR.exists():
            return CheckResult("GNOME Extension", False, "installed but not active")
        return CheckResult("GNOME Extension", False, "not installed")

    @staticmethod
    def install_gnome_extension() -> CheckResult:
        """Install bundled extension via gnome-extensions CLI and enable it.

        Uses ``gnome-extensions install`` with a zip file, which is the
        official installation method.  On Wayland, GNOME Shell only
        discovers new extensions after a session restart (log out / log in),
        so this may return ``needs_restart`` in the detail field.
        """
        if not _EXT_BUNDLE_DIR.exists():
            return CheckResult("GNOME Extension Install", False, "bundle not found")

        # Build a zip from the bundled files
        try:
            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
                zip_path = tmp.name
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for src in _EXT_BUNDLE_DIR.iterdir():
                    zf.write(src, src.name)
        except OSError as exc:
            return CheckResult("GNOME Extension Install", False, f"zip failed: {exc}")

        # Install via gnome-extensions CLI (copies + notifies Shell)
        try:
            subprocess.run(
                ["gnome-extensions", "install", "--force", zip_path],
                capture_output=True, timeout=10,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            return CheckResult(
                "GNOME Extension Install", False, f"install failed: {exc}",
            )
        finally:
            Path(zip_path).unlink(missing_ok=True)

        # Try to enable — may fail if Shell hasn't picked it up yet
        try:
            result = subprocess.run(
                ["gnome-extensions", "enable", _EXT_UUID],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                return CheckResult("GNOME Extension Install", True, str(_EXT_INSTALL_DIR))
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        # Extension installed but Shell hasn't discovered it yet (Wayland)
        if _EXT_INSTALL_DIR.exists():
            return CheckResult(
                "GNOME Extension Install", True,
                "needs_restart — log out and back in to activate",
            )

        return CheckResult("GNOME Extension Install", False, "install failed")

    @staticmethod
    def install_vscode_extension() -> CheckResult:
        """Build and install the work4me-bridge VS Code extension.

        Runs ``npm install``, ``npx vsce package``, and
        ``code --install-extension`` from the bundled extension source.
        """
        if not _VSCODE_EXT_DIR.is_dir():
            return CheckResult(
                "VS Code Extension Install", False, "extension source not found",
            )

        try:
            subprocess.run(
                ["npm", "install"],
                cwd=_VSCODE_EXT_DIR, capture_output=True, timeout=60,
                check=True,
            )
            subprocess.run(
                ["npx", "vsce", "package", "--no-dependencies"],
                cwd=_VSCODE_EXT_DIR, capture_output=True, timeout=30,
                check=True,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired,
                subprocess.CalledProcessError) as exc:
            return CheckResult(
                "VS Code Extension Install", False, f"build failed: {exc}",
            )

        vsix = _VSCODE_EXT_DIR / "work4me-bridge-0.1.0.vsix"
        try:
            subprocess.run(
                ["code", "--install-extension", str(vsix)],
                capture_output=True, timeout=30, check=True,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired,
                subprocess.CalledProcessError) as exc:
            return CheckResult(
                "VS Code Extension Install", False, f"install failed: {exc}",
            )

        return CheckResult("VS Code Extension Install", True, str(vsix))

    def run_all(self) -> list[CheckResult]:
        results = []
        for cmd, label in self.BINARIES:
            results.append(self.check_binary(cmd, label))
        results.append(self.check_uinput())
        results.append(self.check_wayland())
        results.append(self.check_vscode_extension())
        # Only check GNOME extension on GNOME desktops
        desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").upper()
        if "GNOME" in desktop:
            results.append(self.check_gnome_extension())
        return results
