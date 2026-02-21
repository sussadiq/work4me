"""Configuration for Work4Me agent."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TypingConfig:
    wpm_code: float = 62.0
    wpm_prose: float = 80.0
    inter_key_delay_min: float = 0.050
    inter_key_delay_max: float = 0.120
    inter_key_delay_sigma: float = 0.015
    error_rate: float = 0.06
    think_pause_probability: float = 0.03
    think_pause_min: float = 1.0
    think_pause_max: float = 5.0
    burst_length_min: int = 3
    burst_length_max: int = 8
    burst_speed_multiplier: float = 1.5


@dataclass
class ActivityConfig:
    target_ratio_min: float = 0.40
    target_ratio_max: float = 0.70
    variance_min: float = 0.04
    idle_micro_movement_min: float = 45.0
    idle_micro_movement_max: float = 90.0
    max_continuous_high_activity: float = 1800.0


@dataclass
class SessionConfig:
    duration_mean: float = 52.0
    duration_sigma: float = 5.0
    break_mean: float = 6.5
    break_sigma: float = 1.5
    sessions_per_4_hours: int = 4


@dataclass
class ClaudeConfig:
    cli_path: str = "claude"
    model: str = "sonnet"
    max_turns: int = 15
    max_budget_usd: float = 0.0  # 0 = unlimited (Max plan)
    dangerously_skip_permissions: bool = True
    extra_args: list[str] = field(default_factory=list)
    plan_max_retries: int = 3
    plan_retry_base_delay: float = 2.0


@dataclass
class DesktopConfig:
    compositor: str = "auto"
    input_method: str = "auto"
    terminal: str = "auto"
    editor: str = "vscode"
    browser: str = "chromium"


@dataclass
class VSCodeConfig:
    websocket_port: int = 9876
    extension_dir: str = ""
    launch_on_start: bool = True
    executable: str = "code"
    window_class: str = "code"


@dataclass
class BrowserConfig:
    chromium_path: str = "google-chrome"
    debug_port: int = 9222
    enabled: bool = True
    ozone_platform: str = "wayland"
    user_data_dir: str = ""
    profile_directory: str = ""
    window_class: str = "google-chrome"
    cdp_max_retries: int = 5
    cdp_retry_base_delay: float = 1.0
    cdp_initial_wait: float = 2.0


@dataclass
class Config:
    typing: TypingConfig = field(default_factory=TypingConfig)
    activity: ActivityConfig = field(default_factory=ActivityConfig)
    session: SessionConfig = field(default_factory=SessionConfig)
    claude: ClaudeConfig = field(default_factory=ClaudeConfig)
    desktop: DesktopConfig = field(default_factory=DesktopConfig)
    vscode: VSCodeConfig = field(default_factory=VSCodeConfig)
    browser: BrowserConfig = field(default_factory=BrowserConfig)

    mode: str = "manual"  # "manual" or "ai-assisted"
    default_hours: float = 4.0
    working_dir: str = "."
    log_level: str = "INFO"

    @property
    def runtime_dir(self) -> Path:
        base = os.environ.get("XDG_RUNTIME_DIR", "/tmp")
        return Path(base) / "work4me"

    @property
    def log_dir(self) -> Path:
        base = os.environ.get("HOME", "/tmp")
        return Path(base) / ".local" / "share" / "work4me" / "logs"


def load_config(path: Path | None = None) -> Config:
    """Load config from TOML file, falling back to defaults."""
    import tomllib

    if path is None:
        path = Path.home() / ".config" / "work4me" / "config.toml"

    config = Config()
    if not path.exists():
        return config

    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except Exception:
        logger.warning("Failed to parse config at %s, using defaults", path)
        return config

    _apply_toml(config, data)
    return config


def _apply_toml(config: Config, data: dict[str, Any]) -> None:
    """Apply TOML dict onto Config dataclass (one level of nesting)."""
    for key, value in data.items():
        if isinstance(value, dict) and hasattr(config, key):
            sub = getattr(config, key)
            for sk, sv in value.items():
                if hasattr(sub, sk):
                    setattr(sub, sk, sv)
        elif hasattr(config, key):
            setattr(config, key, value)
