# tests/test_cli.py
import argparse
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from work4me.cli import build_parser, cmd_start
from work4me.config import Config


def test_start_accepts_mode_flag():
    parser = build_parser()
    args = parser.parse_args(["start", "--task", "Build API", "--hours", "4", "--mode", "ai-assisted"])
    assert args.mode == "ai-assisted"


def test_start_default_mode_is_manual():
    parser = build_parser()
    args = parser.parse_args(["start", "--task", "Build API", "--hours", "4"])
    assert args.mode == "manual"


def test_start_accepts_working_dir():
    parser = build_parser()
    args = parser.parse_args(["start", "--task", "Build API", "--hours", "4", "--dir", "/tmp/project"])
    assert args.dir == "/tmp/project"


def test_start_accepts_config_flag():
    parser = build_parser()
    args = parser.parse_args(["start", "--task", "Build API", "--config", "/tmp/config.toml"])
    assert args.config == "/tmp/config.toml"


@pytest.mark.asyncio
async def test_cmd_start_uses_load_config(tmp_path):
    """cmd_start should call load_config when --config is provided."""
    toml_file = tmp_path / "config.toml"
    toml_file.write_text('mode = "ai-assisted"\n')

    with patch("work4me.cli.load_config") as mock_load:
        mock_config = Config(mode="ai-assisted")
        mock_load.return_value = mock_config
        with patch("work4me.cli.Orchestrator") as MockOrch:
            MockOrch.return_value.run = AsyncMock()
            args = argparse.Namespace(
                task="test", hours=1.0, working_dir=".", model="sonnet",
                max_budget=5.0, mode="manual", dir=".", verbose=False,
                config=str(toml_file),
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
                task="test", hours=1.0, working_dir=".", model="sonnet",
                max_budget=5.0, mode="manual", dir=".", verbose=False,
                config=None,
            )
            await cmd_start(args)
            mock_load.assert_called_once_with(None)
