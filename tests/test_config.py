from work4me.config import Config, DesktopConfig, ClaudeConfig, BrowserConfig, VSCodeConfig


def test_config_has_mode():
    config = Config()
    assert config.mode in ("manual", "ai-assisted")
    assert config.mode == "manual"  # default


def test_vscode_config_defaults():
    config = VSCodeConfig()
    assert config.websocket_port == 9876
    assert config.launch_on_start is True
    assert config.executable == "code"


def test_browser_config_defaults():
    config = BrowserConfig()
    assert config.chromium_path == "chromium"
    assert config.debug_port == 9222
    assert config.enabled is True


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
