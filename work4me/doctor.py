"""System health checks for Work4Me dependencies."""

import os
import shutil
from dataclasses import dataclass
from pathlib import Path


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
        ext_dir = Path.home() / ".vscode" / "extensions"
        if ext_dir.exists():
            for d in ext_dir.iterdir():
                if "work4me" in d.name.lower():
                    return CheckResult("VS Code Extension", True, str(d))
        return CheckResult("VS Code Extension", False, "not installed")

    def run_all(self) -> list[CheckResult]:
        results = []
        for cmd, label in self.BINARIES:
            results.append(self.check_binary(cmd, label))
        results.append(self.check_uinput())
        results.append(self.check_wayland())
        results.append(self.check_vscode_extension())
        return results
