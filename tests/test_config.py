from pathlib import Path
from work4me.config import Config, DesktopConfig, ClaudeConfig, BrowserConfig, VSCodeConfig, load_config


def test_config_has_mode():
    config = Config()
    assert config.mode in ("manual", "ai-assisted")
    assert config.mode == "manual"  # default


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
mode = "ai-assisted"
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
    assert config.mode == "ai-assisted"
    assert config.log_level == "DEBUG"


def test_load_config_missing_file():
    config = load_config(Path("/nonexistent/config.toml"))
    assert config.mode == "manual"  # defaults


def test_load_config_partial_toml(tmp_path):
    toml_file = tmp_path / "config.toml"
    toml_file.write_text('mode = "ai-assisted"\n')
    config = load_config(toml_file)
    assert config.mode == "ai-assisted"
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
