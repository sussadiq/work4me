"""Configuration for Work4Me agent."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


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
    max_budget_usd: float = 5.0
    dangerously_skip_permissions: bool = True
    extra_args: list[str] = field(default_factory=list)


@dataclass
class DesktopConfig:
    compositor: str = "auto"
    input_method: str = "auto"
    terminal: str = "auto"
    editor: str = "neovim"
    browser: str = "chromium"


@dataclass
class Config:
    typing: TypingConfig = field(default_factory=TypingConfig)
    activity: ActivityConfig = field(default_factory=ActivityConfig)
    session: SessionConfig = field(default_factory=SessionConfig)
    claude: ClaudeConfig = field(default_factory=ClaudeConfig)
    desktop: DesktopConfig = field(default_factory=DesktopConfig)

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
