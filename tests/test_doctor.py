"""Tests for doctor command."""
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


def test_check_vscode_extension_found():
    dc = DoctorChecks()
    with patch("pathlib.Path.exists", return_value=True), \
         patch("pathlib.Path.iterdir", return_value=[MagicMock(name="work4me-bridge")]):
        # The mock's name attr is set via constructor, need to set it properly
        mock_dir = MagicMock()
        mock_dir.name = "work4me-bridge-0.1.0"
        with patch("pathlib.Path.iterdir", return_value=[mock_dir]):
            result = dc.check_vscode_extension()
    assert result.passed


def test_check_vscode_extension_missing():
    dc = DoctorChecks()
    with patch("pathlib.Path.exists", return_value=False):
        result = dc.check_vscode_extension()
    assert not result.passed


def test_run_all_returns_list():
    dc = DoctorChecks()
    with patch("shutil.which", return_value="/usr/bin/test"), \
         patch("pathlib.Path.exists", return_value=True), \
         patch("pathlib.Path.stat") as mock_stat:
        mock_stat.return_value.st_mode = 0o660
        mock_dir = MagicMock()
        mock_dir.name = "work4me-bridge"
        with patch("pathlib.Path.iterdir", return_value=[mock_dir]), \
             patch.dict("os.environ", {"WAYLAND_DISPLAY": "wayland-0"}):
            results = dc.run_all()
    assert isinstance(results, list)
    assert all(isinstance(r, CheckResult) for r in results)
