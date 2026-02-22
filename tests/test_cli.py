# tests/test_cli.py
import argparse
import logging
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from work4me.cli import build_parser, cmd_start, setup_logging
from work4me.config import Config


def test_start_accepts_mode_flag():
    parser = build_parser()
    args = parser.parse_args(["start", "--task", "Build API", "--hours", "4", "--mode", "manual"])
    assert args.mode == "manual"


def test_start_default_mode_is_sidebar():
    parser = build_parser()
    args = parser.parse_args(["start", "--task", "Build API", "--hours", "4"])
    assert args.mode == "sidebar"


def test_start_accepts_working_dir():
    parser = build_parser()
    args = parser.parse_args(["start", "--task", "Build API", "--hours", "4", "--working-dir", "/tmp/project"])
    assert args.working_dir == "/tmp/project"


def test_start_accepts_config_flag():
    parser = build_parser()
    args = parser.parse_args(["start", "--task", "Build API", "--config", "/tmp/config.toml"])
    assert args.config == "/tmp/config.toml"


@pytest.mark.asyncio
async def test_cmd_start_uses_load_config(tmp_path):
    """cmd_start should call load_config when --config is provided."""
    toml_file = tmp_path / "config.toml"
    toml_file.write_text('mode = "sidebar"\n')

    with patch("work4me.cli.load_config") as mock_load:
        mock_config = Config(mode="sidebar")
        mock_load.return_value = mock_config
        with patch("work4me.cli.Orchestrator") as MockOrch:
            MockOrch.return_value.run = AsyncMock()
            args = argparse.Namespace(
                task="test", hours=1.0, budget=None, working_dir=".", model="sonnet",
                max_budget=5.0, mode="manual", verbose=False,
                config=str(toml_file), planning_model=None,
            )
            await cmd_start(args)
            mock_load.assert_called_once()


@pytest.mark.asyncio
async def test_cmd_start_no_config_flag(tmp_path):
    """cmd_start should call load_config with None when --config is absent."""
    with patch("work4me.cli.load_config") as mock_load:
        mock_load.return_value = Config()
        with patch("work4me.cli.Orchestrator") as MockOrch:
            MockOrch.return_value.run = AsyncMock()
            args = argparse.Namespace(
                task="test", hours=1.0, budget=None, working_dir=".", model="sonnet",
                max_budget=5.0, mode="manual", verbose=False,
                config=None, planning_model=None,
            )
            await cmd_start(args)
            mock_load.assert_called_once_with(None)


def test_setup_logging_applies_config_log_level():
    """setup_logging should use log_level from config when not verbose."""
    setup_logging(verbose=False, log_level="DEBUG")
    root = logging.getLogger()
    assert root.level == logging.DEBUG
    # Restore
    setup_logging(verbose=False, log_level="INFO")
