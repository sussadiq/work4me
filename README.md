# Work4Me

A Linux desktop AI agent that performs real software engineering work with human-like pacing. It runs Claude Code CLI headless, then replays every action — file edits, terminal commands, browser searches — visibly across your desktop at natural typing speed.

## Why

AI writes code in seconds. Time-tracking tools expect hours of visible activity. Work4Me bridges that gap: it decomposes a task into subtasks, schedules them across a time budget with natural breaks, and executes each one through real applications (VS Code, Chromium, terminal) with human-paced keystrokes, mouse movements, and idle pauses.

## How It Works

```
Task + Time Budget
        │
        ▼
┌─────────────────┐
│  Task Planner    │  Claude decomposes task into activities
└────────┬────────┘
         ▼
┌─────────────────┐
│   Scheduler      │  Maps activities onto work sessions with breaks
└────────┬────────┘
         ▼
┌─────────────────┐
│  Orchestrator    │  Runs each activity through Claude Code CLI
└────────┬────────┘
         ▼
┌─────────────────┐
│ Behavior Engine  │  Replays actions at human speed with variation
└────────┬────────┘
         ▼
  VS Code · Browser · Terminal
```

1. **Plan** — Claude Code decomposes your task into coding, research, and review activities
2. **Schedule** — Activities are distributed across work sessions with natural breaks
3. **Execute** — Each activity runs through Claude Code CLI (headless, full speed)
4. **Replay** — Actions are replayed visibly: files open in VS Code, commands type in terminal, searches happen in the browser — all at human pace
5. **Monitor** — A behavior engine adjusts pacing, adds idle pauses, and injects variation to keep activity patterns natural

## Requirements

- Linux (GNOME Wayland — primary target; Sway planned)
- Python 3.11+
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) installed and authenticated
- VS Code with the Work4Me WebSocket extension
- Chromium (for browser automation via Playwright)

## Installation

### 1. Python package

```bash
git clone https://github.com/your-org/work4me.git
cd work4me
pip install -e ".[dev]"
```

### 2. VS Code extension

The `work4me-bridge` extension runs a WebSocket server inside VS Code so Work4Me can open files, type text, and run terminal commands remotely.

```bash
cd vscode-extension
npm install
npm run compile
```

Then install it into VS Code:

```bash
# Option A: symlink into VS Code extensions (development)
ln -s "$(pwd)" ~/.vscode/extensions/work4me-bridge

# Option B: load via CLI flag (Work4Me does this automatically)
code --extensions-dir /path/to/vscode-extension
```

The extension activates on startup and listens on `ws://localhost:9876` by default. To change the port, add to your VS Code `settings.json`:

```json
{
  "work4me.port": 9876
}
```

### 3. Verify

```bash
work4me doctor
```

## Usage

```bash
# Start a 4-hour coding session
work4me start --task "Implement user authentication with JWT" --budget 240

# Use a specific operating mode
work4me start --task "Fix pagination bug" --budget 120 --mode ai-assisted

# With a config file
work4me start --task "Add API rate limiting" --budget 180 --config ~/.config/work4me/config.toml

# Check status
work4me status

# Stop gracefully
work4me stop
```

### Operating Modes

| Mode | How it works |
|------|-------------|
| `manual` (default) | Claude runs headless, Work4Me replays actions in VS Code |
| `ai-assisted` | Claude runs visibly in a VS Code terminal |

## Configuration

Work4Me loads config from `~/.config/work4me/config.toml`. All fields are optional — sensible defaults are built in.

```toml
[session]
duration_mean = 50       # Average session length (minutes)
break_mean = 8           # Average break length (minutes)
sessions_per_4_hours = 4

[typing]
wpm = 85
error_rate = 0.02

[claude]
model = "sonnet"
max_turns = 25

[desktop]
compositor = "gnome"
editor = "vscode"
browser = "chromium"
```

## Project Structure

```
work4me/
├── cli.py                  # CLI entry point (start, stop, status, doctor)
├── config.py               # TOML config loading with dataclass defaults
├── doctor.py               # System dependency checker
├── core/
│   ├── orchestrator.py     # Main brain — plans, executes, monitors
│   ├── state.py            # State machine + crash recovery snapshots
│   └── events.py           # Event bus for internal communication
├── controllers/
│   ├── claude_code.py      # Claude Code CLI subprocess + JSON stream parser
│   ├── vscode.py           # VS Code control via WebSocket
│   ├── browser.py          # Chromium automation via Playwright CDP
│   ├── editor.py           # [STAGED] Neovim RPC (planned for Sway)
│   └── terminal.py         # [STAGED] tmux control (planned for Sway)
├── behavior/
│   ├── engine.py           # Human-like pacing with speed multiplier
│   ├── typing.py           # Keystroke timing with Gaussian jitter
│   ├── mouse.py            # Bezier cursor paths with Fitts' law timing
│   └── activity_monitor.py # Tracks activity ratios and recommends adjustments
├── planning/
│   ├── task_planner.py     # Claude-powered task decomposition
│   └── scheduler.py        # Session/break scheduling from config
└── desktop/
    └── input_sim.py        # [STAGED] ydotool/dotool input simulation
```

## Testing

```bash
# Run all tests
python -m pytest -v

# Run a specific test file
python -m pytest tests/test_orchestrator.py -v
```

132 tests covering orchestration, controllers, behavior engine, scheduling, config, CLI, and crash recovery.

## Security

The hardened codebase includes:

- Shell injection prevention via `shlex.quote()` for all subprocess commands
- Path traversal guards on file operations from AI output
- URL encoding for browser search queries
- Response-ID matching on WebSocket to prevent message interleaving
- Crash recovery with activity-level resume (no re-execution of completed work)

## License

MIT
