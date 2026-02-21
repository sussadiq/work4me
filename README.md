# Work4Me

**A Linux desktop AI agent that does your coding work — visibly, at human speed.**

Work4Me takes a task and a time budget, decomposes it into activities, and executes each one through real desktop applications (VS Code, Chromium, terminal). It opens files, types code, runs commands, searches the web, takes breaks — all paced like a person actually sitting at the keyboard.

Under the hood, Claude Code CLI does the real engineering. Work4Me is the performance layer that makes it look like someone's home.

---

## The Problem

AI can write code in seconds. But your time tracker, your screen recorder, your Upwork client — they all expect hours of visible work. Copy-pasting AI output doesn't look like engineering. It looks like what it is.

Work4Me fixes that. It takes the same AI output and replays it the way a developer would: opening files one by one, typing with realistic speed and typos, pausing to read, switching to the browser to look something up, running tests, taking coffee breaks. The work is real. The pacing is human.

## How It Works

```
  "Implement JWT auth"          you
  + 4 hours budget               │
         │                        │
         ▼                        │   you go do literally
  ┌──────────────┐                │   whatever you want
  │ Task Planner │ Claude breaks  │
  │              │ it into pieces │
  └──────┬───────┘                │
         ▼                        │
  ┌──────────────┐                │
  │  Scheduler   │ Maps onto      │
  │              │ work sessions  │
  └──────┬───────┘                │
         ▼                        │
  ┌──────────────┐                │
  │ Orchestrator │ Runs Claude    │
  │              │ Code per task  │
  └──────┬───────┘                │
         ▼                        │
  ┌──────────────┐                │
  │  Behavior    │ Replays at     │
  │  Engine      │ human speed    │
  └──────┬───────┘                │
         ▼                        ▼
  VS Code · Chrome · Terminal   done.
```

**Step by step:**

1. **Plan** — Claude decomposes your task into coding, research, terminal, and review activities
2. **Schedule** — Activities get distributed across work sessions with natural breaks (configurable)
3. **Execute** — Each activity runs through Claude Code CLI headless at full speed
4. **Replay** — The results are performed visibly: files open in VS Code, commands get typed into the terminal, searches happen in the browser, all at ~85 WPM with realistic variation
5. **Monitor** — A behavior engine watches activity patterns and adjusts pacing — adds idle pauses, mouse movements, typing speed variation, so it never looks robotic

---

## Requirements

| What | Why |
|------|-----|
| Linux with GNOME Wayland | Primary target (Sway support planned) |
| Python 3.11+ | Runtime |
| [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) | The brain — must be installed and authenticated |
| VS Code | Where code gets visibly written |
| Chromium / Chrome | Browser automation via Playwright CDP |
| `gdbus` | D-Bus calls for GNOME window switching |

## Installation

### 1. Clone and install

```bash
git clone https://github.com/your-org/work4me.git
cd work4me
pip install -e ".[dev]"
```

### 2. Set up the VS Code extension

The `work4me-bridge` extension runs a WebSocket server inside VS Code so Work4Me can remotely open files, type text, and execute terminal commands.

```bash
cd vscode-extension
npm install && npm run compile
```

Install it:

```bash
# Dev mode — symlink into VS Code extensions
ln -s "$(pwd)" ~/.vscode/extensions/work4me-bridge

# Or load via CLI flag (Work4Me does this automatically on launch)
code --extensions-dir /path/to/vscode-extension
```

The extension listens on `ws://localhost:9876` by default. Change the port in VS Code settings:

```json
{ "work4me.port": 9876 }
```

### 3. GNOME window focus extension

Work4Me bundles a minimal GNOME Shell extension for switching focus between VS Code and Chrome. It gets auto-installed on first run, but you can do it manually:

```bash
# Create a zip and install via the official CLI tool
cd work4me/desktop/gnome-ext
zip /tmp/work4me-focus.zip metadata.json extension.js
gnome-extensions install --force /tmp/work4me-focus.zip
```

**On Wayland, you need to log out and back in** for GNOME Shell to discover the new extension. Then enable it:

```bash
gnome-extensions enable work4me-focus@work4me
```

> **Why an extension?** `org.gnome.Shell.Eval` has been completely blocked since GNOME 45, and `Shell.FocusApp` returns `AccessDenied`. Our extension runs inside GNOME Shell and exposes a single D-Bus method (`ActivateByWmClass`) that bypasses focus-stealing restrictions and handles cross-workspace window activation. Same pattern as [activate-window-by-title](https://github.com/lucaswerkmeister/activate-window-by-title), stripped to just what we need.

### 4. Verify everything

```bash
work4me doctor
```

This checks for all binaries, permissions, Wayland session, VS Code extension, and (on GNOME) the window focus extension.

---

## Usage

```bash
# Start a 4-hour coding session
work4me start --task "Implement user authentication with JWT" --budget 240

# Use ai-assisted mode (Claude runs visibly in the terminal)
work4me start --task "Fix pagination bug" --budget 120 --mode ai-assisted

# Point to a specific config
work4me start --task "Add API rate limiting" --budget 180 \
  --config ~/.config/work4me/config.toml

# Check what's happening
work4me status

# Stop gracefully (finishes current activity, commits, cleans up)
work4me stop
```

### Operating Modes

| Mode | What happens |
|------|-------------|
| **`manual`** (default) | Claude runs headless at full speed. Work4Me replays every file edit, terminal command, and search visibly in VS Code / browser at human pace. |
| **`ai-assisted`** | Claude runs in a visible VS Code terminal. Work4Me types prompts and reviews output like a developer using an AI assistant. |

---

## Configuration

Config lives at `~/.config/work4me/config.toml`. Everything has defaults — you only need to set what you want to change.

```toml
mode = "manual"  # or "ai-assisted"

[session]
duration_mean = 50       # avg work session (minutes)
break_mean = 8           # avg break (minutes)
sessions_per_4_hours = 4

[typing]
wpm = 85                 # words per minute
error_rate = 0.02        # typo frequency (corrected naturally)

[claude]
model = "sonnet"
max_turns = 25

[browser]
enabled = true
window_class = "Chromium-browser"

[vscode]
launch_on_start = true
window_class = "Code"
```

---

## Project Structure

```
work4me/
├── cli.py                     Entry point — start, stop, status, doctor
├── config.py                  TOML config → nested dataclasses
├── doctor.py                  System health checks + GNOME extension installer
│
├── core/
│   ├── orchestrator.py        The brain — plans, dispatches, monitors, recovers
│   ├── state.py               State machine + crash recovery snapshots
│   └── events.py              Internal event bus
│
├── controllers/
│   ├── claude_code.py         Claude Code CLI subprocess + JSON stream parser
│   ├── vscode.py              VS Code remote control via WebSocket
│   ├── browser.py             Chromium automation via Playwright CDP
│   ├── editor.py              [planned] Neovim RPC for Sway
│   └── terminal.py            [planned] tmux control for Sway
│
├── behavior/
│   ├── engine.py              Human-like pacing orchestration
│   ├── typing.py              Keystroke timing with Gaussian jitter
│   ├── mouse.py               Bezier cursor paths with Fitts' law timing
│   └── activity_monitor.py    Activity ratio tracking + adjustment signals
│
├── planning/
│   ├── task_planner.py        Claude-powered task decomposition
│   └── scheduler.py           Work session / break scheduling
│
├── desktop/
│   ├── window_mgr.py          Compositor-specific window focus switching
│   ├── gnome-ext/             Bundled GNOME Shell extension for window focus
│   └── input_sim.py           [planned] ydotool/dotool input simulation
│
└── vscode-extension/          Companion VS Code WebSocket bridge
```

---

## Testing

```bash
# Full suite
python -m pytest tests/ -q

# Specific module
python -m pytest tests/test_orchestrator.py -v

# Type checking
python -m mypy work4me/ --strict
```

185 tests covering orchestration, controllers, behavior engine, scheduling, config, CLI, window management, doctor checks, and crash recovery. All async tests use `pytest-asyncio` with auto mode.

---

## Security

This tool executes AI-generated code on your machine, so the codebase is hardened:

- **Shell injection prevention** — all subprocess args go through `shlex.quote()`
- **Path traversal guards** — file paths from AI output are resolved and checked against the working directory
- **URL encoding** — browser search queries are properly encoded
- **WebSocket message isolation** — response-ID matching prevents interleaved command results
- **Crash recovery** — activity-level state snapshots mean a crash doesn't re-execute completed work
- **Graceful degradation** — every controller (browser, VS Code, window manager) handles unavailability without crashing the session

---

## Design Docs

The `docs/` folder contains 13 research and design documents covering the architecture decisions in detail:

| Doc | Topic |
|-----|-------|
| `00-overview.md` | High-level architecture |
| `01-stack-recommendation.md` | Technology choices and rationale |
| `02-wayland-platform.md` | Wayland input, window management, screen capture |
| `03-architecture.md` | Component design and data flow |
| `04-claude-code-integration.md` | Claude Code CLI integration strategy |
| `05-browser-automation.md` | Playwright CDP approach |
| `06-terminal-editor-control.md` | tmux + Neovim control |
| `07-behavior-model.md` | Human-like pacing algorithms |
| `08-task-scheduling.md` | Work session and break scheduling |
| `09-risk-analysis.md` | Threat model and mitigations |
| `10-implementation-roadmap.md` | Build sequence and milestones |
| `11-distribution.md` | Packaging and deployment |
| `12-prior-art.md` | Related tools and research |

These are living documents — they get updated as the architecture evolves.

---

## License

MIT
