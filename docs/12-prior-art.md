# Existing Tools & Prior Art

## AI Desktop Agents

### Anthropic Computer Use
- **Architecture:** Docker container with Ubuntu 22.04, Xfce desktop, VNC server
- **Uses X11 inside container** (not Wayland): xvfb, xdotool, scrot
- **Agent loop:** screenshot → Claude API → action → screenshot → repeat
- `ComputerTool` class shells out to `xdotool` for mouse/keyboard
- `scrot` for screenshots, `imagemagick` for processing
- Recommended resolution: 1024x768 or 1280x800
- Beta header: `anthropic-beta: computer-use-2025-01-24`
- **Lesson:** Containerized X11 sidesteps all Wayland issues but may not register as "real desktop activity" to host time trackers

### Bytebot
- Self-hosted AI desktop agent in Docker container
- Uses X11 (Xfce4) inside container, similar to Anthropic's approach
- Daemon exposes "computer use primitives" (keyboard, mouse, screen)
- Supports multiple AI providers
- Deployable via Docker Compose or Kubernetes

### Open Interpreter
- LLM-powered code execution (Python, JS, Shell) locally
- Computer API for GUI control: screen capture, mouse/keyboard
- Vision capabilities for analyzing screenshots
- Supports GPT-4o, Claude, or local models
- Primary focus: macOS; Linux/Wayland support secondary

### Agent S (Simular AI)
- Open-source framework for autonomous computer interaction
- Agent-Computer Interface (ACI) for web and desktop automation

### UI-TARS (ByteDance)
- Open-source multimodal AI agent stack
- Desktop application connecting AI models to agent infrastructure

### Eigent
- Open-source multi-agent desktop workforce
- Developer, Browser, Document, Multi-Modal agents
- Cross-platform: Windows, Linux, macOS
- Based on CAMEL-AI framework

**Pattern:** Nearly all AI desktop agents use containerized X11. Work4Me is novel in targeting native Wayland.

---

## Desktop Automation Frameworks

### Working on Wayland

| Tool | Status | How |
|---|---|---|
| **dogtail 1.0+** | Wayland-native (Aug 2024) | AT-SPI + ScreenCast/RemoteDesktop portals |
| **wayland-automation** | New (Jan 2026) | Direct Wayland socket + wtype, multi-compositor |
| **ydotool** | Works everywhere | Kernel uinput (compositor-agnostic) |
| **dotool** | Works everywhere | Kernel uinput, friendlier syntax |
| **wtype** | wlroots only | `zwp_virtual_keyboard_v1` protocol |
| **wlrctl** | wlroots only | wlroots window management protocols |

### Broken on Wayland

| Tool | Status | Why |
|---|---|---|
| **xdotool** | XWayland only | Uses X11 protocol, fails for native Wayland windows |
| **autokey** | Experimental Wayland fork | GNOME only, many APIs unimplemented |
| **pyautogui** | Completely broken | Uses Xlib, returns black screenshots |
| **SikuliX** | Broken (Java Robot bug) | Captures only black screens on Wayland |
| **LDTP** | Dormant | Superseded by dogtail |

---

## Time Tracker Analysis

### Hubstaff (Most Sophisticated)

**Activity measurement:**
- Measures keyboard and mouse per **10-minute intervals** (600 seconds)
- Each second: active (any KB/mouse) or inactive (none)
- Activity % = active seconds / 600
- Does NOT log actual keystrokes — only detects input occurred
- Screenshots: 0-3 per 10 min (default), up to 10/10min

**Color thresholds:** Green ≥50%, Yellow 20-50%, Red <20%

**Fraud detection (CRITICAL):**
- List of known time fraud applications (mouse jigglers)
- Flags ≥95% activity for 30+ minutes ("unusually high")
- Flags ≤4% fluctuation for 90+ minutes ("unusually consistent")
- Flags 0% fluctuation for 40+ minutes
- Flags keyboard ~0% while mouse active for 50+ minutes
- Detects repetitive, robotic mouse movement patterns
- AI-powered pattern recognition

**Linux/Wayland:** Supports screenshots on GNOME 41 and below with Wayland. Only GNOME display manager. Cannot show keyboard/mouse activity breakdown on Linux.

### Time Doctor

**Activity measurement:**
- Tracks keyboard and mouse when screenshots enabled
- Average keystrokes and mouse movements per minute under each screenshot
- Does NOT record keystroke content
- Screenshots at **intentionally randomized intervals** (prevent preparation)
- Auto-stops on configurable idle duration
- Tracks websites and applications used

### TopTracker (Toptal)

**Activity measurement:**
- Tracks keyboard and mouse clicks (not keystrokes)
- Enters "idle" on no input
- Basic activity stats
- Screenshots, keystroke counts, optional webcam
- Freelancer controls what gets tracked (can blur screenshots)
- Supports Linux: Ubuntu 14.04+, Debian 9+, Fedora 23+

### Toggl Track

**Activity measurement:**
- Timeline auto-captures app/website usage (>10 sec)
- Idle detection based on keyboard/mouse
- Prompts user when idle (keep/discard)
- Activity data private to user (not visible to employers)
- **Linux desktop app deprecated**
- Much less surveillance-oriented

---

## What We Can Build On

| Existing Tool | How We Use It |
|---|---|
| **ydotool/dotool** | Input simulation layer (keyboard + mouse) |
| **dogtail** | UI state verification via AT-SPI (optional) |
| **tmux** | Terminal control layer (send-keys, capture-pane) |
| **Playwright/CDP** | Browser automation |
| **pynvim** | Neovim remote control |
| **libtmux** | Python tmux API |
| **dbus-next** | D-Bus communication (portals, compositor) |
| **bezmouse/human_mouse** | Reference for Bezier mouse movement algorithms |
| **Pydoll** | Reference for realistic CDP browser interaction |

## What We Build From Scratch

| Component | Why Custom |
|---|---|
| **Orchestrator / State Machine** | Unique to Work4Me's pacing requirements |
| **Behavior Engine** | Custom human-like timing tuned for time trackers |
| **Activity Monitor** | Anti-detection constraint enforcement |
| **Task Planner + Scheduler** | Time budget distribution is novel |
| **Claude Code Manager** | Stream-json parsing + action replay pipeline |
| **Compositor Abstraction** | No existing cross-compositor automation framework |

---

## Key Insight from Prior Art

All existing AI desktop agents (Anthropic, Bytebot, Open Interpreter) use **containerized X11** to avoid Wayland's automation restrictions. This is pragmatic for AI tasks but doesn't solve Work4Me's core problem — time trackers run on the **host desktop**, not inside containers. Work4Me must operate on the native Wayland desktop to generate activity that's visible to host-level time trackers. This makes Work4Me architecturally novel but also means confronting Wayland's fragmented automation landscape directly.
