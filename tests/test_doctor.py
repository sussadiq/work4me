"""Tests for doctor command."""
import subprocess
import pytest
from unittest.mock import patch, MagicMock
from work4me.doctor import DoctorChecks, CheckResult


def test_check_result_pass():
    r = CheckResult("test", True, "/usr/bin/test")
    assert r.passed
    assert r.detail == "/usr/bin/test"


def test_check_result_fail():
    r = CheckResult("test", False, "NOT FOUND")
    assert not r.passed


def test_check_binary_found():
    dc = DoctorChecks()
    with patch("shutil.which", return_value="/usr/bin/python3"):
        result = dc.check_binary("python3", "Python 3.11+")
    assert result.passed


def test_check_binary_missing():
    dc = DoctorChecks()
    with patch("shutil.which", return_value=None):
        result = dc.check_binary("nonexistent", "Fake tool")
    assert not result.passed


def test_check_vscode_extension_found_via_cli():
    dc = DoctorChecks()
    mock_result = MagicMock(returncode=0, stdout="some.ext\nwork4me.work4me-bridge\nother.ext\n")
    with patch("subprocess.run", return_value=mock_result):
        result = dc.check_vscode_extension()
    assert result.passed
    assert "work4me" in result.detail.lower()


def test_check_vscode_extension_cli_fails_fallback_to_dir():
    dc = DoctorChecks()
    mock_dir = MagicMock()
    mock_dir.name = "work4me-bridge-0.1.0"
    mock_dir.__str__ = lambda self: "/home/user/.vscode/extensions/work4me-bridge-0.1.0"
    with patch("subprocess.run", side_effect=FileNotFoundError), \
         patch("pathlib.Path.exists", return_value=True), \
         patch("pathlib.Path.iterdir", return_value=[mock_dir]):
        result = dc.check_vscode_extension()
    assert result.passed
    assert "work4me-bridge" in result.detail


def test_check_vscode_extension_missing():
    dc = DoctorChecks()
    mock_result = MagicMock(returncode=0, stdout="some.ext\nother.ext\n")
    with patch("subprocess.run", return_value=mock_result), \
         patch("pathlib.Path.exists", return_value=False):
        result = dc.check_vscode_extension()
    assert not result.passed
    assert "not installed" in result.detail


def test_run_all_returns_list():
    dc = DoctorChecks()
    mock_cli = MagicMock(returncode=0, stdout="work4me.work4me-bridge\n")
    with patch("shutil.which", return_value="/usr/bin/test"), \
         patch("pathlib.Path.exists", return_value=True), \
         patch("pathlib.Path.stat") as mock_stat, \
         patch("subprocess.run", return_value=mock_cli):
        mock_stat.return_value.st_mode = 0o660
        with patch.dict("os.environ", {"WAYLAND_DISPLAY": "wayland-0"}):
            results = dc.run_all()
    assert isinstance(results, list)
    assert all(isinstance(r, CheckResult) for r in results)


# ------------------------------------------------------------------
# GNOME Extension checks
# ------------------------------------------------------------------

def test_check_gnome_extension_active():
    dc = DoctorChecks()
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "  Name: Work4Me Window Focus\n  State: ACTIVE\n"
    with patch("subprocess.run", return_value=mock_result):
        result = dc.check_gnome_extension()
    assert result.passed
    assert result.detail == "active"


def test_check_gnome_extension_inactive():
    dc = DoctorChecks()
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "  Name: Work4Me Window Focus\n  State: INACTIVE\n"
    with patch("subprocess.run", return_value=mock_result), \
         patch("pathlib.Path.exists", return_value=True):
        result = dc.check_gnome_extension()
    assert not result.passed
    assert "not active" in result.detail


def test_check_gnome_extension_missing():
    dc = DoctorChecks()
    with patch("subprocess.run", side_effect=FileNotFoundError), \
         patch("pathlib.Path.exists", return_value=False):
        result = dc.check_gnome_extension()
    assert not result.passed
    assert "not installed" in result.detail


def test_install_gnome_extension_success():
    mock_src = MagicMock()
    mock_src.name = "extension.js"
    mock_enable = MagicMock(returncode=0)
    with patch("pathlib.Path.exists", return_value=True), \
         patch("pathlib.Path.iterdir", return_value=[mock_src]), \
         patch("tempfile.NamedTemporaryFile") as mock_tmp, \
         patch("zipfile.ZipFile"), \
         patch("pathlib.Path.unlink"), \
         patch("subprocess.run", return_value=mock_enable):
        mock_tmp.return_value.__enter__ = MagicMock(return_value=MagicMock(name="/tmp/x.zip"))
        mock_tmp.return_value.__exit__ = MagicMock(return_value=False)
        result = DoctorChecks.install_gnome_extension()
    assert result.passed


def test_install_gnome_extension_bundle_missing():
    with patch("pathlib.Path.exists", return_value=False):
        result = DoctorChecks.install_gnome_extension()
    assert not result.passed
    assert "bundle not found" in result.detail


# ------------------------------------------------------------------
# Playwright Firefox checks
# ------------------------------------------------------------------

def test_check_playwright_firefox_found():
    dc = DoctorChecks()
    mock_bin = MagicMock()
    mock_bin.__str__ = lambda self: "/home/user/.cache/ms-playwright/firefox-1509/firefox/firefox"
    with patch("pathlib.Path.exists", return_value=True), \
         patch("pathlib.Path.glob", return_value=[mock_bin]):
        result = dc.check_playwright_firefox()
    assert result.passed
    assert "firefox" in result.detail


def test_check_playwright_firefox_missing():
    dc = DoctorChecks()
    with patch("pathlib.Path.exists", return_value=True), \
         patch("pathlib.Path.glob", return_value=[]):
        result = dc.check_playwright_firefox()
    assert not result.passed
    assert "playwright install firefox" in result.detail


def test_check_playwright_firefox_no_cache_dir():
    dc = DoctorChecks()
    with patch("pathlib.Path.exists", return_value=False):
        result = dc.check_playwright_firefox()
    assert not result.passed
    assert "playwright install firefox" in result.detail


def test_run_all_includes_gnome_extension_on_gnome():
    dc = DoctorChecks()
    mock_cli = MagicMock(returncode=0, stdout="work4me.work4me-bridge\nState: ACTIVE\n")
    with patch("shutil.which", return_value="/usr/bin/test"), \
         patch("pathlib.Path.exists", return_value=True), \
         patch("pathlib.Path.stat") as mock_stat, \
         patch("subprocess.run", return_value=mock_cli), \
         patch.dict("os.environ", {"WAYLAND_DISPLAY": "wayland-0", "XDG_CURRENT_DESKTOP": "GNOME"}):
        mock_stat.return_value.st_mode = 0o660
        results = dc.run_all()
    names = [r.name for r in results]
    assert "GNOME Extension" in names


# ------------------------------------------------------------------
# VS Code Extension install
# ------------------------------------------------------------------

def test_install_vscode_extension_success():
    with patch("pathlib.Path.is_dir", return_value=True), \
         patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        result = DoctorChecks.install_vscode_extension()
    assert result.passed
    assert "vsix" in result.detail


def test_install_vscode_extension_source_missing():
    with patch("pathlib.Path.is_dir", return_value=False):
        result = DoctorChecks.install_vscode_extension()
    assert not result.passed
    assert "source not found" in result.detail
