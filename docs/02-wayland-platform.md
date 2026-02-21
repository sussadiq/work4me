# Wayland Platform Analysis

## Input Simulation

### ydotool (Universal — Primary Fallback)

**How it works:** Uses Linux kernel's `/dev/uinput` to create a virtual input device. Events are injected at kernel level — works on ALL Wayland compositors, X11, and even TTY.

**Architecture:** Requires `ydotoold` daemon running. Client sends commands via Unix socket (default `$XDG_RUNTIME_DIR/.ydotool_socket`).

**Permissions (non-root):**
```bash
# udev rule: /etc/udev/rules.d/99-work4me-uinput.rules
KERNEL=="uinput", GROUP="uinput", MODE="0660", OPTIONS+="static_node=uinput"

# Create group and add user
sudo groupadd -f uinput
sudo usermod -aG uinput $USER
# User must log out and back in
```

**Commands:** `type` (text), `key` (press/release keycodes), `mousemove`, `click`, `mousemove_relative`

**Known issues:** Uses numeric keycodes with explicit press/release notation. Types slowly compared to direct protocol tools. Cannot target specific windows.

### dotool (Universal — Better Syntax)

**How it works:** Also uses `/dev/uinput` like ydotool, but with friendlier syntax. Reads actions from stdin.

**Key advantages over ydotool:**
- Accepts key **names** instead of numeric keycodes: `echo "key alt+F4" | dotool`
- Supports keyboard layouts via `DOTOOL_XKB_LAYOUT` env var
- Daemon/client pair (`dotoold`/`dotoolc`) to avoid device registration delay

**Same permissions as ydotool** (uinput access).

### wtype (wlroots Only — Keyboard Only)

Uses `zwp_virtual_keyboard_v1` Wayland protocol. Works on wlroots compositors (Sway, Hyprland). Does NOT work on GNOME or KDE. Keyboard only, no mouse.

### RemoteDesktop Portal (Cross-Compositor — Best for GNOME)

**D-Bus interface:** `org.freedesktop.portal.RemoteDesktop`

Combines input emulation + screen capture in one authorized session. After one-time user consent:
- `NotifyKeyboardKeycode` — inject keyboard events
- `NotifyPointerMotionAbsolute` — inject mouse movement
- `NotifyPointerButton` — inject mouse clicks
- Screen capture via PipeWire stream

**Restore tokens:** `persist_mode=2` stores a token on disk. Subsequent sessions skip the consent dialog.

**Supported:** GNOME, KDE, wlroots portals.

### libei (Future — Not Ready)

New input emulation standard by Red Hat. Client library `libei`, server library `libeis`. Version 1.0 released, protocol stable. Python bindings: `hzy`.

**Compositor support:** GNOME/Mutter has a WIP merge request. wlroots/Sway has an open issue. KDE and Hyprland: no support. **Not practically usable today.**

### xdotool on Wayland

Partially works for XWayland windows only. Window management completely broken. Recent versions refuse to run when detecting XWayland. **Not viable — avoid.**

### Strategy

```
                   ┌─────────────────┐
                   │  Detect Compositor │
                   └────────┬────────┘
                            │
              ┌─────────────┼─────────────┐
              │             │             │
         GNOME/KDE      wlroots       Other
              │             │             │
    RemoteDesktop      wtype (kb)    ydotool/dotool
    Portal (D-Bus)     + ydotool       (universal)
                       (mouse)
```

---

## Window Management

**No universal solution.** Must be compositor-specific.

### GNOME/Mutter
- No native CLI for window move/resize/focus
- Options:
  - GNOME Shell extensions via D-Bus: `activate-window-by-title`, `Window Commander`
  - `org.gnome.Shell.Eval` D-Bus interface — **implemented** in `work4me/desktop/window_mgr.py` via `gdbus call`. Uses JS to find windows by `wm_class` and call `activate()`. Caches availability to avoid log spam; gracefully degrades if Shell.Eval is restricted.
  - AT-SPI accessibility APIs for reading UI state
  - GNOME 49 `xdg_toplevel_tag_v1` protocol + `gnome-service-client` for tagging windows

### Sway
- `swaymsg` IPC — comprehensive control
- Focus: `swaymsg '[app_id="firefox"]' focus`
- Query: `swaymsg -t get_tree` (JSON)
- Move, resize, fullscreen, kill, workspace management
- Subscribe to events: window open/close/focus

### Hyprland
- `hyprctl dispatch` — full compositor control
- `hyprctl clients` — list windows (JSON)
- `hyprctl activewindow` — focused window info
- `--batch` flag for multiple commands
- **No longer wlroots-based** — wlrctl/grim may not work with newer versions

### KDE/KWin
- `kdotool` — Rust tool providing xdotool-like commands via KWin D-Bus scripting
- KWin scripting API (JavaScript/QML) loaded at runtime
- `org.kde.KWin` D-Bus interface: cascadeDesktop, killWindow, setCurrentDesktop
- KDE Plasma 6.8+ is Wayland-exclusive

### wlr-foreign-toplevel-management Protocol
- wlroots protocol for listing/managing toplevel windows
- Supported by: Sway, Hyprland, Niri, River, labwc, Wayfire, and **KDE KWin**
- **NOT supported by:** GNOME/Mutter

---

## Screen Capture

### ScreenCast Portal + PipeWire (Cross-Compositor)

**D-Bus interface:** `org.freedesktop.portal.ScreenCast`

- Creates screen capture sessions via PipeWire
- Supports **restore tokens** for session persistence:
  - `persist_mode=2` (persistent) — token stored on disk, valid until user revokes
  - After initial consent, subsequent sessions skip the dialog
- Supported by GNOME, KDE, wlroots portals

### grim (wlroots Only)
- `grim screenshot.png` — full screen, silent, no dialog
- `grim -g "X,Y WxH" screenshot.png` — region
- `grim -o DP-1 screenshot.png` — specific output
- Only works on wlroots compositors

### GNOME Screenshots
- `org.gnome.Shell.Screenshot` D-Bus — access removed for third-party apps post-GNOME 41
- `xdg-desktop-portal Screenshot` — requires user confirmation dialog every time
- `gnome-screenshot` — broken in GNOME 49+
- **No silent screenshots on GNOME** — use ScreenCast portal instead

---

## Accessibility (AT-SPI)

AT-SPI2 runs over D-Bus (the a11y bus), NOT the display protocol. Works on Wayland same as X11.

**Capabilities:**
- Hierarchical tree of UI elements (buttons, text fields, menus)
- Properties: name, role, state, bounds, text content
- Actions: click, activate, set text
- Event notifications: focus changes, text changes

**Libraries:** `pyatspi2` (Python), `libatspi` (C), `at-spi2-core`

**Limitation on Wayland:** Mouse review (Orca feature) doesn't work. GNOME has a desktop-specific protocol to address remaining gaps.

---

## Compositor Comparison Matrix

| Feature | GNOME/Mutter | KDE/KWin | Sway | Hyprland |
|---|---|---|---|---|
| **Input: ydotool/dotool** | YES | YES | YES | YES |
| **Input: RemoteDesktop portal** | YES (dialog once) | YES (dialog once) | Partial | NO |
| **Input: wtype** | NO | NO | YES | YES (older) |
| **Window mgmt: native IPC** | Extensions only | kdotool/D-Bus/scripts | swaymsg | hyprctl |
| **Window mgmt: wlr-foreign-toplevel** | NO | YES | YES | YES |
| **Screenshots: grim** | NO | NO | YES | YES (older) |
| **Screenshots: portal** | YES (dialog) | YES (dialog) | YES (dialog) | YES (dialog) |
| **Screencast: PipeWire portal** | YES | YES | YES | YES |
| **Screencast: restore tokens** | YES | YES | YES | YES |
| **AT-SPI accessibility** | YES | YES | YES | YES |
| **Clipboard: wl-clipboard** | YES | YES | YES | YES |

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

## Target Priority

1. **GNOME/Mutter** — most common desktop, RemoteDesktop portal is the best approach
2. **Sway** — most automatable (swaymsg IPC + grim + wtype), good for development/testing
3. **KDE/KWin** — kdotool provides good coverage
4. **Hyprland** — hyprctl is powerful but Hyprland's break from wlroots adds complexity
