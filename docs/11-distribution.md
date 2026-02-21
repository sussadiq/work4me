# Distribution & Packaging

## Packaging Format Comparison

| Format | uinput Access | D-Bus Access | Pros | Cons | Verdict |
|---|---|---|---|---|---|
| **Tarball + script** | Full | Full | No sandbox, simple | Manual install | **Primary** |
| **AppImage** | Full | Full | No root to run, portable | No auto-update by default | **Secondary** |
| **Flatpak** | Blocked | Filtered | Auto-update, sandboxed | Can't access `/dev/uinput` | **Avoid** |
| **Snap** | Blocked (needs joystick interface) | Restricted | Ubuntu store | Same sandbox issues | **Avoid** |
| **.deb/.rpm** | Full | Full | Distro-native | Per-distro packaging | Future |
| **Nix flake** | Full | Full | Reproducible builds | Niche audience | Future |
| **pipx** | Full | Full | Python-native | Requires Python on system | Alternative |

## Primary: Tarball + Install Script

```
work4me-0.1.0-linux-x86_64.tar.gz
  ├── work4me/                      # Python package (or PyInstaller bundle)
  ├── install.sh                    # Setup script
  ├── uninstall.sh                  # Cleanup script
  ├── 99-work4me-uinput.rules      # udev rule
  └── work4me.service               # systemd user service
```

## System Dependencies

| Dependency | Purpose | Required? | Package Names |
|---|---|---|---|
| Python 3.11+ | Runtime | Yes | `python3` |
| Node.js 18+ | Claude Code CLI runtime | Yes | `nodejs` (or via nvm) |
| Claude Code CLI | AI engineering intelligence | Yes | `npm install -g @anthropic-ai/claude-code` |
| ydotool | Input simulation (universal) | Yes | `ydotool` |
| tmux | Terminal multiplexing | Yes | `tmux` |
| wl-clipboard | Clipboard access | Yes | `wl-clipboard` |
| Kitty or WezTerm | Terminal emulator | Recommended | `kitty` / `wezterm` |
| Neovim | Visible code editor | Recommended | `neovim` |
| Chromium | Browser automation | For browser features | `chromium` |
| xdg-desktop-portal | Portal APIs | Pre-installed | (already on most desktops) |

## Dependency Detection

```python
DEPS = {
    'ydotool': {
        'apt': 'ydotool',
        'dnf': 'ydotool',
        'pacman': 'ydotool',
        'check': 'which ydotool'
    },
    'tmux': {
        'apt': 'tmux',
        'dnf': 'tmux',
        'pacman': 'tmux',
        'check': 'which tmux'
    },
    'wl-clipboard': {
        'apt': 'wl-clipboard',
        'dnf': 'wl-clipboard',
        'pacman': 'wl-clipboard',
        'check': 'which wl-copy'
    },
    'neovim': {
        'apt': 'neovim',
        'dnf': 'neovim',
        'pacman': 'neovim',
        'check': 'which nvim'
    },
    'node': {
        'check': 'which node',
        'install_note': 'Install via https://nodejs.org or nvm'
    }
}

def detect_package_manager():
    for pm in ['apt', 'dnf', 'pacman', 'zypper']:
        if shutil.which(pm):
            return pm
    return None
```

## Permissions Setup

### uinput Access (Required for ydotool/dotool)

```bash
# Create udev rule: /etc/udev/rules.d/99-work4me-uinput.rules
KERNEL=="uinput", MODE="0660", GROUP="uinput", OPTIONS+="static_node=uinput"

# Create group and add user
sudo groupadd -f uinput
sudo usermod -aG uinput $USER

# Reload udev rules
sudo udevadm control --reload && sudo udevadm trigger --name-match uinput

# User MUST log out and back in for group membership to take effect
```

### Other Permissions

- **PipeWire:** Accessible via session bus, no special permissions
- **D-Bus session bus:** Accessible to any process in user's session
- **File system:** Work4Me runs as user, needs read/write to project directory
- **RemoteDesktop portal:** One-time user consent dialog, then persistent restore token

## Compositor Detection

```python
import os, shutil

def detect_compositor() -> str:
    desktop = os.environ.get('XDG_CURRENT_DESKTOP', '').upper()
    session = os.environ.get('XDG_SESSION_TYPE', '')

    if 'GNOME' in desktop: return 'gnome'
    if 'KDE' in desktop: return 'kde'
    if desktop == 'SWAY' or shutil.which('swaymsg'): return 'sway'
    if desktop == 'HYPRLAND' or shutil.which('hyprctl'): return 'hyprland'
    if session == 'wayland': return 'unknown-wayland'
    return 'x11'
```

Adaptations by compositor:
- **Window management:** swaymsg (Sway), hyprctl (Hyprland), kdotool (KDE), D-Bus extensions (GNOME)
- **Input simulation:** RemoteDesktop portal (GNOME/KDE), ydotool (universal)
- **Screenshots:** grim (wlroots), ScreenCast portal (universal)

## Install Script Flow

```bash
#!/bin/bash
# install.sh

echo "Work4Me Installer"

# 1. Detect distro and package manager
PM=$(detect_package_manager)

# 2. Check for required dependencies
for dep in ydotool tmux wl-clipboard neovim; do
    if ! command -v $dep &>/dev/null; then
        echo "Installing $dep..."
        sudo $PM install -y $dep
    fi
done

# 3. Check for Node.js
if ! command -v node &>/dev/null; then
    echo "Node.js is required for Claude Code CLI."
    echo "Install from https://nodejs.org or via nvm"
    exit 1
fi

# 4. Check for Claude Code CLI
if ! command -v claude &>/dev/null; then
    echo "Installing Claude Code CLI..."
    npm install -g @anthropic-ai/claude-code
fi

# 5. Install udev rule for uinput access
sudo cp 99-work4me-uinput.rules /etc/udev/rules.d/
sudo groupadd -f uinput
sudo usermod -aG uinput $USER
sudo udevadm control --reload
sudo udevadm trigger --name-match uinput

# 6. Install Work4Me Python package
pip install --user ./work4me/

# 7. Install systemd user service (optional)
mkdir -p ~/.config/systemd/user/
cp work4me.service ~/.config/systemd/user/
systemctl --user daemon-reload

# 8. Remind about re-login
echo ""
echo "Installation complete!"
echo "IMPORTANT: Log out and back in for uinput group membership to take effect."
echo "Then run: work4me doctor"
```

## Doctor Command

```bash
$ work4me doctor

Checking dependencies...
  ✓ Python 3.12.3
  ✓ Node.js 20.11.0
  ✓ Claude Code CLI 1.0.12
  ✓ tmux 3.4
  ✓ Neovim 0.10.1
  ✓ ydotool 1.1.2
  ✓ wl-clipboard 2.2.1

Checking permissions...
  ✓ /dev/uinput accessible
  ✓ D-Bus session bus connected
  ✓ Wayland session detected

Checking compositor...
  ✓ GNOME/Mutter detected
  ✓ xdg-desktop-portal-gnome running

Checking Claude Code...
  ✓ Claude Code authenticated
  ✓ API key valid

All checks passed! Run: work4me start --task "..." --hours 4
```

## Auto-Updates

For tarball distribution, self-update pattern:
1. Check GitHub Releases API for latest version on startup (or daily)
2. Download new tarball
3. Verify SHA256 checksum
4. Replace current installation
5. Restart daemon

If distributed as AppImage: `AppImageUpdate` handles delta updates with embedded update info.

## Systemd User Service

```ini
# ~/.config/systemd/user/work4me.service
[Unit]
Description=Work4Me Desktop AI Agent
After=graphical-session.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 -m work4me daemon
Restart=on-failure
RestartSec=5
Environment=XDG_RUNTIME_DIR=%t

[Install]
WantedBy=graphical-session.target
```

```bash
# Start
systemctl --user start work4me

# Enable on login
systemctl --user enable work4me

# Check status
systemctl --user status work4me
```
