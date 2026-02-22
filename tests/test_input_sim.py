from __future__ import annotations

import logging
from unittest.mock import AsyncMock, patch

import pytest

from work4me.desktop.input_sim import DotoolInput


class TestTranslateKeyToYdotool:
    """Tests for DotoolInput._translate_key_to_ydotool."""

    def setup_method(self) -> None:
        self.inp = DotoolInput()

    def test_return(self) -> None:
        assert self.inp._translate_key_to_ydotool("Return") == ["enter"]

    def test_escape(self) -> None:
        assert self.inp._translate_key_to_ydotool("Escape") == ["esc"]

    def test_tab(self) -> None:
        assert self.inp._translate_key_to_ydotool("Tab") == ["tab"]

    def test_space(self) -> None:
        assert self.inp._translate_key_to_ydotool("space") == ["space"]

    def test_backspace(self) -> None:
        assert self.inp._translate_key_to_ydotool("BackSpace") == ["backspace"]

    def test_f1(self) -> None:
        assert self.inp._translate_key_to_ydotool("F1") == ["F1"]

    def test_ctrl_return(self) -> None:
        result = self.inp._translate_key_to_ydotool("ctrl+Return")
        assert result == ["ctrl+enter"]

    def test_shift_tab(self) -> None:
        result = self.inp._translate_key_to_ydotool("shift+Tab")
        assert result == ["shift+tab"]

    def test_alt_f4(self) -> None:
        result = self.inp._translate_key_to_ydotool("alt+F4")
        assert result == ["alt+F4"]

    def test_ctrl_shift_escape(self) -> None:
        result = self.inp._translate_key_to_ydotool("ctrl+shift+Escape")
        assert result == ["ctrl+shift+esc"]

    def test_unknown_key_falls_back(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING):
            result = self.inp._translate_key_to_ydotool("XF86AudioPlay")
        assert result == ["XF86AudioPlay"]
        assert "Unknown ydotool key name" in caplog.text

    def test_unknown_modifier_falls_back(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING):
            result = self.inp._translate_key_to_ydotool("hyper+Return")
        assert result == ["hyper+Return"]
        assert "Unknown ydotool modifier" in caplog.text


class TestRunYdotoolKey:
    """Tests that _run_ydotool passes evdev key names for key commands."""

    async def test_key_uses_name(self) -> None:
        inp = DotoolInput()
        inp._dotool_path = None
        inp._ydotool_path = "/usr/bin/ydotool"

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.communicate.return_value = (b"", b"")
            mock_proc.returncode = 0
            mock_exec.return_value = mock_proc

            await inp._run_ydotool("key Return")

            mock_exec.assert_called_once_with(
                "/usr/bin/ydotool", "key", "enter",
                stdout=-3,  # asyncio.subprocess.DEVNULL
                stderr=-1,  # asyncio.subprocess.PIPE
            )

    async def test_key_combo_uses_names(self) -> None:
        inp = DotoolInput()
        inp._dotool_path = None
        inp._ydotool_path = "/usr/bin/ydotool"

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.communicate.return_value = (b"", b"")
            mock_proc.returncode = 0
            mock_exec.return_value = mock_proc

            await inp._run_ydotool("key ctrl+Return")

            mock_exec.assert_called_once_with(
                "/usr/bin/ydotool", "key", "ctrl+enter",
                stdout=-3,
                stderr=-1,
            )
