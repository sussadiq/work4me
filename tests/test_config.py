from pathlib import Path
from work4me.config import (
    Config, DesktopConfig, ClaudeConfig, BrowserConfig, VSCodeConfig,
    MicroPauseConfig, BrowserMouseConfig, CaptchaConfig, load_config,
)


def test_config_has_mode():
    config = Config()
    assert config.mode in ("sidebar", "manual")
    assert config.mode == "sidebar"  # default


def test_vscode_config_defaults():
    config = VSCodeConfig()
    assert config.websocket_port == 9876
    assert config.launch_on_start is True
    assert config.executable == "code"
    assert config.window_class == "code"


def test_browser_config_defaults():
    config = BrowserConfig()
    assert config.enabled is True
    assert config.user_data_dir == ""
    assert config.window_class == "firefox"
    assert config.launch_timeout == 30000.0


def test_claude_config_no_budget_cap():
    config = ClaudeConfig()
    assert config.max_budget_usd == 0.0  # 0 means unlimited (Max plan)


def test_desktop_config_editor_is_vscode():
    config = DesktopConfig()
    assert config.editor == "vscode"


def test_config_has_vscode_and_browser():
    config = Config()
    assert isinstance(config.vscode, VSCodeConfig)
    assert isinstance(config.browser, BrowserConfig)


def test_load_config_from_toml(tmp_path):
    toml_file = tmp_path / "config.toml"
    toml_file.write_text("""
mode = "manual"
log_level = "DEBUG"

[typing]
wpm_code = 100.0

[activity]
target_ratio_min = 0.50

[claude]
model = "opus"

[vscode]
websocket_port = 8888
""")
    config = load_config(toml_file)
    assert config.typing.wpm_code == 100.0
    assert config.activity.target_ratio_min == 0.50
    assert config.claude.model == "opus"
    assert config.vscode.websocket_port == 8888
    assert config.mode == "manual"
    assert config.log_level == "DEBUG"


def test_load_config_missing_file():
    config = load_config(Path("/nonexistent/config.toml"))
    assert config.mode == "sidebar"  # defaults


def test_load_config_partial_toml(tmp_path):
    toml_file = tmp_path / "config.toml"
    toml_file.write_text('mode = "manual"\n')
    config = load_config(toml_file)
    assert config.mode == "manual"
    assert config.typing.wpm_code == 62.0  # unchanged default


def test_claude_config_retry_defaults():
    config = ClaudeConfig()
    assert config.plan_max_retries == 3
    assert config.plan_retry_base_delay == 2.0


def test_browser_config_has_no_cdp_fields():
    config = BrowserConfig()
    assert not hasattr(config, "cdp_max_retries")
    assert not hasattr(config, "chromium_path")
    assert not hasattr(config, "debug_port")


def test_micro_pause_config_defaults():
    config = MicroPauseConfig()
    assert config.min_seconds == 15.0
    assert config.max_seconds == 60.0
    assert config.frequency_per_activity == 0.3


def test_config_has_micro_pause():
    config = Config()
    assert isinstance(config.micro_pause, MicroPauseConfig)


def test_session_config_no_breaks():
    from work4me.config import SessionConfig
    config = SessionConfig()
    assert config.break_mean == 0.0
    assert config.break_sigma == 0.0
    assert config.sessions_per_4_hours == 1


def test_micro_pause_config_from_toml(tmp_path):
    toml_file = tmp_path / "config.toml"
    toml_file.write_text("""
[micro_pause]
min_seconds = 20.0
max_seconds = 45.0
frequency_per_activity = 0.5
""")
    config = load_config(toml_file)
    assert config.micro_pause.min_seconds == 20.0
    assert config.micro_pause.max_seconds == 45.0
    assert config.micro_pause.frequency_per_activity == 0.5


# --- BrowserMouseConfig and CaptchaConfig ---


def test_browser_mouse_config_defaults():
    config = BrowserMouseConfig()
    assert config.step_interval_min == 0.008
    assert config.step_interval_max == 0.016
    assert config.overshoot_probability == 0.15
    assert config.click_delay_min == 0.05
    assert config.click_delay_max == 0.15


def test_captcha_config_defaults():
    config = CaptchaConfig()
    assert config.enabled is True
    assert config.max_attempts == 3
    assert config.screenshot_timeout == 5000.0


def test_browser_config_has_mouse_and_captcha():
    config = BrowserConfig()
    assert isinstance(config.mouse, BrowserMouseConfig)
    assert isinstance(config.captcha, CaptchaConfig)


def test_toml_two_level_nesting_browser_mouse(tmp_path):
    """TOML [browser.mouse] should apply to BrowserMouseConfig."""
    toml_file = tmp_path / "config.toml"
    toml_file.write_text("""
[browser.mouse]
step_interval_min = 0.01
click_delay_max = 0.20

[browser.captcha]
enabled = false
max_attempts = 5
""")
    config = load_config(toml_file)
    assert config.browser.mouse.step_interval_min == 0.01
    assert config.browser.mouse.click_delay_max == 0.20
    assert config.browser.captcha.enabled is False
    assert config.browser.captcha.max_attempts == 5


def test_toml_two_level_nesting_preserves_other_fields(tmp_path):
    """Two-level nesting should not break one-level fields."""
    toml_file = tmp_path / "config.toml"
    toml_file.write_text("""
[browser]
enabled = false
window_class = "chrome"

[browser.mouse]
overshoot_probability = 0.25
""")
    config = load_config(toml_file)
    assert config.browser.enabled is False
    assert config.browser.window_class == "chrome"
    assert config.browser.mouse.overshoot_probability == 0.25
    # Other mouse defaults preserved
    assert config.browser.mouse.step_interval_min == 0.008
