# Implementation Roadmap

## Phase 1: Foundation (Week 1-2)

**Milestone: Claude Code drives visible terminal typing**

### Tasks

1. **Project scaffolding**
   - `pyproject.toml` with dependencies
   - `work4me/__main__.py` entry point
   - `work4me/cli.py` — minimal CLI with `start` command (accepts `--task` and `--hours`)
   - `work4me/config.py` — Config dataclass with hardcoded defaults

2. **Claude Code integration** (`controllers/claude_code.py`)
   - Spawn `claude -p "prompt" --output-format stream-json --dangerously-skip-permissions`
   - Parse stream-json events from stdout asynchronously
   - Extract `tool_use` events (Edit, Bash) into structured action queue
   - Handle exit codes and errors
   - Unit tests with mock subprocess

3. **Terminal controller** (`controllers/terminal.py`)
   - Create tmux session: `tmux new-session -d -s work4me`
   - Send keystrokes: `tmux send-keys`
   - Read output: `tmux capture-pane -p`
   - Launch Neovim in second pane
   - libtmux Python API wrapper

4. **Basic behavior engine** (`behavior/typing.py`, `behavior/engine.py`)
   - Human-like typing: inter-key delay with Gaussian noise
   - Basic error injection (random wrong char + backspace)
   - Configurable WPM

5. **Input simulation** (`desktop/input_sim.py`)
   - ydotool wrapper for keyboard input
   - Key name to keycode mapping
   - Basic mouse click (no Bezier yet)

6. **Integration test**
   - Simple prompt → Claude Code produces code → code is typed visibly in Neovim at human speed
   - Command is typed in terminal pane

### Dependencies to Install
```
pip install libtmux pynvim numpy
npm install -g @anthropic-ai/claude-code
apt install tmux neovim ydotool
```

### Estimated Output: ~15-18 Python files, ~2000-2500 LOC

---

## Phase 2: Scheduling & State Machine (Week 3-4)

**Milestone: 4-hour autonomous session with breaks**

### Tasks

7. **State machine** (`core/orchestrator.py`, `core/state.py`)
   - Full state machine with transitions (IDLE → INITIALIZING → PLANNING → WORKING → ...)
   - State persistence to JSON every 30 seconds
   - Signal handling (SIGTERM, SIGINT → graceful shutdown)

8. **Task planner** (`planning/task_planner.py`)
   - Prompt engineering: ask Claude Code to decompose task into JSON activities
   - Parse and validate the decomposition
   - Estimate visible durations based on code complexity

9. **Scheduler** (`planning/scheduler.py`)
   - Map activities onto work sessions with variable-length periods
   - Target activity distribution (25% coding, 15% reading, etc.)
   - Break scheduling with Gaussian noise

10. **Activity monitor** (`behavior/activity_monitor.py`)
    - Sliding window activity tracking (10-min and 90-min windows)
    - Basic health checks (activity ratio, variance)
    - Feedback to orchestrator

11. **CLI control** (`cli.py`, `daemon.py`)
    - PID file management for single-instance enforcement
    - Unix socket for `status`, `pause`, `resume`, `stop` commands
    - Graceful shutdown with wrap-up (git commit)

12. **Integration test**
    - Start a real task, run for 30 minutes
    - Observe natural session structure with breaks
    - Verify state persistence and resume

---

## Phase 3: Desktop Polish (Week 5-6)

**Milestone: Convincing human-like desktop activity**

### Tasks

13. **Mouse simulation** (`behavior/mouse.py`)
    - Bezier curve path generation
    - Fitts's law velocity model
    - Overshoot and micro-adjustments
    - Integration with input_sim

14. **Editor controller enhancements** (`controllers/editor.py`)
    - Neovim RPC via pynvim for precise cursor positioning
    - File navigation (goto line, search, jump to definition)
    - Visible code reading (scrolling through code with pauses)

15. **RemoteDesktop portal** (`desktop/input_sim.py`)
    - D-Bus session via dbus_next
    - Replace ydotool with portal-based input for GNOME
    - Restore token for reconnection without dialog

16. **Adaptive pacing** (`planning/scheduler.py`)
    - Detect when ahead of schedule → add tests, docs, refactoring
    - Detect when behind → prioritize visible progress
    - ActivityMonitor feedback loop fully integrated

17. **Integration test**
    - Full 4-hour session
    - Passes visual inspection (looks like a human working)
    - Activity monitoring heuristics within bounds

---

## Phase 4: Browser & Multi-Compositor (Week 7-8)

**Milestone: Full feature set**

### Tasks

18. **Browser controller** (`controllers/browser.py`)
    - Launch Chromium with `--remote-debugging-port=9222 --ozone-platform=wayland`
    - Playwright `connect_over_cdp` connection
    - Human-like browsing patterns (search, read, scroll, navigate)
    - Tab management

19. **Compositor abstraction** (`desktop/compositor.py`)
    - Sway support via `swaymsg`
    - Hyprland support via `hyprctl`
    - KDE support via `kdotool`
    - Auto-detection at startup

20. **Window management** (`desktop/window_mgr.py`)
    - List windows, focus window, position windows
    - Compositor-specific implementations behind common interface

21. **Screen capture** (`desktop/screen_capture.py`)
    - ScreenCast portal integration via D-Bus
    - PipeWire frame capture for self-monitoring
    - Verify visible state matches expected

22. **Configuration file** (`config.py`)
    - TOML file support (`~/.config/work4me/config.toml`)
    - Validation and defaults
    - Per-project overrides

---

## Phase 5: Hardening & Distribution (Week 9-10)

**Milestone: Release-ready**

### Tasks

23. **Error recovery** (all modules)
    - Controller health checks and restart logic
    - Crash recovery from state file
    - Watchdog coroutine (60-second health check cycle)

24. **Human interrupt detection**
    - Detect unexpected keyboard/mouse activity (user is at the computer)
    - Agent backs off gracefully (transition to INTERRUPTED)
    - Resume when user stops interacting

25. **Install script** (`install/install.sh`)
    - Detect distro and package manager
    - Install system dependencies (ydotool, tmux, wl-clipboard, node)
    - Install udev rule for uinput access
    - Create systemd user service
    - `work4me doctor` for health verification

26. **Logging and observability**
    - Structured logging to file (INFO/DEBUG levels)
    - Activity JSONL log (all keyboard/mouse events)
    - Post-session report (time breakdown, activity stats, work completed)

27. **Testing**
    - Unit tests for all modules
    - Integration tests (mock Claude Code, real tmux)
    - Activity pattern validation (verify against human-plausibility constraints)

---

## MVP Definition (Phase 1-2)

The minimum viable product demonstrates the core value proposition.

**In scope:**
- Single task execution with time budget
- Task planning via Claude Code (2-level decomposition)
- Terminal-only visible work (tmux + Neovim)
- ydotool for input simulation
- Human-like typing (basic inter-key delay + noise)
- Fixed session structure (50-min work, 7-min break)
- Basic activity monitoring
- `start`, `stop`, `status` CLI

**Explicitly out of scope for MVP:**
- Browser automation
- RemoteDesktop portal
- Screen capture / self-monitoring
- VS Code integration
- Mouse Bezier curves
- Adaptive replanning
- Multiple compositor support
- Install script / packaging
- Kitty-specific integration

**MVP size:** ~15-18 Python files, ~2500 LOC

---

## What Success Looks Like

After completing all 5 phases:
- Zero ambiguity about stack, tools, and libraries
- Every component has clear interfaces and interactions
- Human-like activity that passes Hubstaff/Time Doctor inspection
- Real code, real commits, real working software produced
- Autonomous 4-hour sessions with zero user intervention
- Graceful error recovery and state persistence
