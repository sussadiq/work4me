# System Architecture

## Process Architecture

```
work4me (main daemon)                     # Python asyncio, single process
  |
  +-- ydotoold                            # uinput daemon (may already be running)
  |
  +-- claude -p ... --output-format       # Claude Code CLI (per-activity, interleaved)
  |     stream-json
  |
  +-- VS Code                             # Primary visible IDE
  |     +-- work4me-bridge extension      # WebSocket server on port 9876
  |     +-- integrated terminal           # Visible terminal commands
  |
  +-- firefox (via Playwright)             # Browser (launched at startup)
```

**Single asyncio process.** All concurrency is cooperative coroutines. External tools run as OS subprocesses via `asyncio.create_subprocess_exec`. No multiprocessing — workload is 100% I/O-bound.

## IPC Channels

| From → To | Mechanism |
|---|---|
| Daemon ↔ Claude CLI | stdin/stdout pipes, stream-json parsing (manual mode) |
| Daemon ↔ VS Code | WebSocket (work4me-bridge extension, port 9876) |
| Daemon ↔ Claude Code extension | Via VS Code bridge commands (sidebar mode) |
| Daemon ↔ Browser | Playwright `firefox.launch_persistent_context` (managed) |
| Daemon ↔ Desktop | D-Bus via `dbus_next` (RemoteDesktop portal) |
| Daemon ↔ dotool/ydotool | Subprocess calls (keyboard input for sidebar mode) |
| CLI ↔ Daemon | Unix socket at `$XDG_RUNTIME_DIR/work4me/daemon.sock` |

## Socket / File Layout

```
$XDG_RUNTIME_DIR/work4me/
  daemon.pid                 # PID file for single-instance enforcement
  daemon.sock                # Unix socket for CLI control (start/stop/status)
  state.json                 # Persisted state for crash recovery
  schedule.json              # Current task schedule
  activity_log.jsonl         # Activity log (append-only)
```

## Module Breakdown

```
work4me/
  __main__.py              # Entry point: python -m work4me
  cli.py                   # CLI: start, stop, status, pause, resume, doctor
  config.py                # Configuration loading (TOML) and validation
  daemon.py                # PID file, signal handling, daemon lifecycle

  core/
    orchestrator.py        # Main state machine and event loop
    state.py               # State definitions, persistence, transitions
    events.py              # Typed async event bus

  planning/
    task_planner.py        # Task decomposition via Claude Code (3-level hierarchy)
    scheduler.py           # Time-aware scheduling, adaptive pacing
    time_budget.py         # Session/break structure, time arithmetic

  desktop/
    compositor.py          # Compositor detection and abstraction
    input_sim.py           # Input simulation (RemoteDesktop portal / ydotool)
    window_mgr.py          # Window focus, positioning (compositor-specific)
    screen_capture.py      # ScreenCast portal + PipeWire frame capture
    clipboard.py           # wl-copy / wl-paste wrapper

  controllers/
    vscode.py              # VS Code control via WebSocket bridge extension
    browser.py             # Firefox via Playwright
    terminal.py            # tmux session management (fallback)
    editor.py              # Neovim RPC (fallback)
    claude_code.py         # Claude Code CLI subprocess management

  behavior/
    engine.py              # Central behavior coordinator
    typing.py              # Human-like keystroke timing
    mouse.py               # Bezier curves, Fitts's law
    timing.py              # Activity/idle patterns, break scheduling
    activity_monitor.py    # Track own activity, enforce realism constraints
```

## Module Responsibilities

### `core/orchestrator.py` — Orchestrator
The brain. Runs the main asyncio event loop and state machine. Supports dual operating modes: Sidebar mode (primary — drives Claude Code VS Code extension sidebar with human-like typing) and Manual mode (fallback — headless Claude, replay in VS Code). Uses interleaved per-activity execution.

```python
class Orchestrator:
    def __init__(self, config: Config):
        self.state_machine = StateMachine()
        self.event_bus = EventBus()
        self._planner = TaskPlanner(config.claude)
        self._scheduler = Scheduler(config.session)
        self._behavior = BehaviorEngine(config)
        self._vscode = VSCodeController(config.vscode)
        self._browser_ctrl = BrowserController(config.browser)
        self._claude = ClaudeCodeManager(config.claude)
        self._activity_monitor = ActivityMonitor(config.activity)

    async def run(self, task_description: str, time_budget_minutes: int, working_dir: str):
        """Main entry point. Plans, schedules, executes per-activity."""
```

### `planning/task_planner.py` — TaskPlanner
Decomposes user task into 3-level hierarchy using Claude Code itself:

```python
@dataclass
class Feature:
    description: str
    activities: list[Activity]

@dataclass
class Activity:
    kind: ActivityKind  # CODING, READING, TERMINAL, BROWSER, THINKING, BREAK
    description: str
    estimated_minutes: float
    micro_actions: list[MicroAction]
    dependencies: list[str]

@dataclass
class MicroAction:
    kind: MicroActionKind  # OPEN_FILE, TYPE_CODE, RUN_COMMAND, BROWSE_URL, READ_CODE, THINK
    params: dict
    estimated_seconds: float
```

### `planning/scheduler.py` — Scheduler
Maps activities onto wall-clock time with human-like session structure.

### `desktop/input_sim.py` — Input Simulation
Abstraction over multiple input methods:

```python
class InputMethod(Protocol):
    async def type_key(self, keycode: int, press: bool) -> None: ...
    async def move_mouse(self, x: float, y: float, absolute: bool) -> None: ...
    async def click_mouse(self, button: int) -> None: ...

class RemoteDesktopPortalInput(InputMethod):
    """Uses org.freedesktop.portal.RemoteDesktop D-Bus interface."""

class YdotoolInput(InputMethod):
    """Falls back to ydotool subprocess calls."""
```

### `controllers/claude_code.py` — ClaudeCodeManager
Interface to Claude Code CLI — the actual engineering intelligence.

```python
class ClaudeCodeManager:
    async def execute(self, prompt: str, working_dir: str,
                      max_turns: int = 10,
                      max_budget_usd: float = 1.0) -> AsyncIterator[StreamEvent]:
        """Run claude -p and yield parsed stream-json events."""

    async def continue_session(self, session_id: str, prompt: str) -> AsyncIterator[StreamEvent]:
        """Resume a previous session."""

    async def plan_task(self, task_description: str, context: str) -> TaskPlan:
        """Ask Claude Code to decompose a task into structured JSON."""
```

### `behavior/engine.py` — BehaviorEngine
Central coordinator — every desktop interaction passes through this module.

```python
class BehaviorEngine:
    async def type_text(self, text: str, input_method: InputMethod) -> None:
        """Type with human-like characteristics (variable speed, errors, pauses)."""

    async def move_mouse_to(self, x: float, y: float, input_method: InputMethod) -> None:
        """Move mouse along Bezier curve with Fitts's law velocity."""

    async def idle_think(self, duration_seconds: float) -> None:
        """Simulate thinking with micro-movements every 45-90 sec."""

    async def take_break(self, duration_seconds: float) -> None:
        """Simulate break with minimal activity."""
```

### `behavior/activity_monitor.py` — ActivityMonitor
Tracks own activity statistics in sliding windows to ensure human-plausible bounds.

```python
class ActivityMonitor:
    def activity_ratio(self, window_seconds: int = 600) -> float:
        """Activity % per 10-min window. Target: 40-70%."""

    def variance(self, window_seconds: int = 5400) -> float:
        """Variance over 90-min window. Must be >4%."""

    def is_within_bounds(self) -> ActivityHealth:
        """Check all anti-detection constraints."""

    def recommended_adjustment(self) -> BehaviorAdjustment:
        """Suggest: slow down, speed up, add idle, add mouse."""
```

### Each Controller has health/recovery interface:

```python
class Controller(Protocol):
    async def health_check(self) -> bool: ...
    async def restart(self) -> None: ...
    async def cleanup(self) -> None: ...
```

## State Machine

```
                  +---> PLANNING ---+
                  |                 |
IDLE ---> INITIALIZING ---> WORKING ---> WRAPPING_UP ---> COMPLETED
  ^          |                 |              |
  |          v                 v              v
  +------ PAUSED <-------  INTERRUPTED    ERROR
```

Note: The ON_BREAK state has been removed. Work sessions use organic micro-pauses (15-60 seconds) between activities instead of formal breaks, producing more natural-looking activity patterns.

| State | Description | Active Modules |
|---|---|---|
| `IDLE` | Daemon running, no task. Waiting for CLI command. | CLI listener |
| `INITIALIZING` | Launching VS Code, browser. Connecting controllers. | DesktopController, all Controllers |
| `PLANNING` | Claude Code decomposes task. Scheduler builds timeline. | ClaudeCodeManager, TaskPlanner, Scheduler |
| `WORKING` | Executing activities: sidebar prompts, typing, commands, browsing. | All controllers, BehaviorEngine, ActivityMonitor |
| `PAUSED` | User manually paused. All activity stops. | CLI listener only |
| `WRAPPING_UP` | <10 min remaining. Committing work, final cleanup. | TerminalController (git commit) |
| `COMPLETED` | Done. Report generated. Transition to IDLE. | None |
| `INTERRUPTED` | User activity detected. Agent backs off. | Desktop event listener |
| `ERROR` | Unrecoverable failure. Awaiting user intervention. | CLI listener, logging |

### State Transitions

```python
TRANSITIONS = {
    IDLE:          {"start_task": INITIALIZING},
    INITIALIZING:  {"setup_complete": PLANNING, "setup_failed": ERROR},
    PLANNING:      {"plan_ready": WORKING, "plan_failed": ERROR, "user_pause": PAUSED},
    WORKING:       {"time_almost_up": WRAPPING_UP,
                    "task_complete_early": WRAPPING_UP, "user_pause": PAUSED,
                    "user_interrupt": INTERRUPTED, "error": ERROR, "replan_needed": PLANNING},
    PAUSED:        {"user_resume": WORKING, "user_stop": WRAPPING_UP},
    WRAPPING_UP:   {"wrapped_up": COMPLETED, "error": ERROR},
    INTERRUPTED:   {"user_gone": WORKING, "user_pause": PAUSED, "timeout": PAUSED},
    COMPLETED:     {"start_task": INITIALIZING},
    ERROR:         {"retry": INITIALIZING, "user_fix": PLANNING},
}
```

### WORKING Sub-States

```
PICKING_ACTIVITY -> EXECUTING_MICRO_ACTION -> (loop) -> ACTIVITY_DONE
                          |
                          v
                    WAITING_FOR_CLAUDE  (need Claude Code output)
                          |
                          v
                    REPLAYING_OUTPUT    (typing code/commands visibly)
```

## Core Data Flow

### Sidebar Mode (Primary)
```
1. Scheduler picks next activity: "Write auth middleware"
       |
2. VSCodeController.open_claude_sidebar()
3. VSCodeController.new_claude_conversation()
4. VSCodeController.focus_claude_input()
       |
5. BehaviorEngine.type_text(prompt) via dotool
       |  (human-like keystrokes in Claude Code sidebar)
       |
6. VSCodeController.start_claude_watch()
7. input_sim.type_key("Return")  →  Claude starts working
       |
8. Poll VSCodeController.is_claude_busy() until idle (5s threshold)
       |
9. VSCodeController.stop_claude_watch()  →  log file changes
       |
10. Review diffs (2-8s pause), then accept_diff() or reject_diff()
       |
11. Open changed files for visual review
12. ActivityMonitor records events, adjusts pacing
```

### Manual Mode (Fallback)
```
1. Scheduler picks next activity: "Write auth middleware"
       |
2. ClaudeCodeManager.execute(activity_prompt)
       |  (subprocess: claude -p "..." --output-format stream-json)
       |
3. Claude Code works at full speed (seconds):
       |  → stream-json events captured as actions
       |
4. For each action — replay in VS Code:
       |  a. VSCodeController.open_file("src/auth.ts")
       |  b. VSCodeController.type_text(code_content)  # visible typing
       |  c. VSCodeController.save_file()
       |
5. For terminal commands:
       |  a. VSCodeController.run_terminal_command("npm test")
       |
6. ActivityMonitor records events, adjusts pacing
```

## Feedback Loops

```
ActivityMonitor ---(health)---> Orchestrator ---(adjust)---> BehaviorEngine
                                     |
                                     +---(replan)---> Scheduler ---(new schedule)--->
```

ActivityMonitor checks health every 60 seconds. If activity too high → insert idle pauses. If too low → speed up. If variance too low → add fluctuation.

## Event Bus

```python
class EventBus:
    async def emit(self, event: Event) -> None: ...
    def subscribe(self, event_type: type[Event], handler: Callable) -> None: ...

@dataclass
class StateChanged(Event):
    old_state: State
    new_state: State

@dataclass
class ClaudeOutput(Event):
    event_type: str  # "edit", "bash", "text"
    content: dict

@dataclass
class HealthWarning(Event):
    metric: str
    value: float
    threshold: float
    recommendation: str
```

## Error Recovery

### Error Hierarchy

| Level | Example | Strategy |
|---|---|---|
| 0: Micro-action | Typo didn't register | Retry 3x with exponential backoff |
| 1: Activity | Claude Code error | Skip/retry, replan if critical |
| 2: Controller | tmux died, browser crashed | Health check + restart |
| 3: System | D-Bus down, uinput lost | Persist state, transition to ERROR |
| 4: Unrecoverable | API key invalid, disk full | Log, notify user, ERROR state |

### State Persistence

Written to `$XDG_RUNTIME_DIR/work4me/state.json` every 30 seconds and on state transitions:

```json
{
  "version": 1,
  "state": "WORKING",
  "task_description": "Implement JWT auth...",
  "time_budget_minutes": 240,
  "started_at": "2026-02-21T09:00:00Z",
  "elapsed_minutes": 87,
  "current_activity_index": 3,
  "current_micro_action_index": 7,
  "completed_activities": [0, 1, 2],
  "claude_session_id": "abc-123-def",
  "controller_state": {
    "tmux_session": "work4me",
    "working_dir": "/home/user/project",
    "last_file": "src/middleware/auth.ts",
    "last_url": "https://jwt.io/introduction"
  }
}
```

On startup with existing state: ask user to resume or start fresh.

### Watchdog Coroutine

Runs every 60 seconds:
1. Check controller health → restart if needed
2. Check activity health → emit HealthWarning if bounds exceeded
3. Check time budget → trigger WRAPPING_UP if <10 min
4. Persist state

## Configuration

### CLI Interface

```bash
work4me start --task "Implement JWT auth" --hours 4
work4me start --task-file ~/tasks/jwt-auth.md --hours 4
work4me status
work4me pause
work4me resume
work4me stop          # Graceful wrap-up + commit
work4me kill          # Immediate stop
work4me log [--tail]
work4me doctor        # Verify deps and permissions
```

### Config File: `~/.config/work4me/config.toml`

```toml
[task]
default_hours = 4
max_budget_usd = 5.0
claude_model = "sonnet"

[behavior]
typing_wpm_code = 62
typing_wpm_prose = 80
error_rate = 0.06
target_activity_ratio = 0.55
session_duration_mean = 52
break_duration_mean = 6.5

[desktop]
compositor = "auto"
input_method = "auto"
terminal = "auto"
editor = "neovim"
browser = "firefox"

[claude]
cli_path = "claude"
dangerously_skip_permissions = true
extra_args = []
```

## Key Architectural Decisions

### Why replay Claude Code's output instead of driving desktop directly?
Claude Code in `--dangerously-skip-permissions` mode works headlessly — fast but invisible. Work4Me intercepts actions via stream-json and replays visibly at human speed. Separation means: real work at full speed, visible presentation at human speed.

### Why asyncio single-process?
100% I/O-bound workload. asyncio handles thousands of concurrent I/O operations efficiently. Multiprocessing adds complexity for zero benefit.

### Why VS Code as primary IDE?
Screenshot credibility — VS Code is what engineers use in 2026. The custom WebSocket bridge extension (`work4me-bridge`) provides precise programmatic control (open files, type text, run terminal commands, navigate). tmux/Neovim are retained as fallbacks.

### Why dual operating modes?
Mode A (Manual Developer) imitates hand-coding. Mode B (AI-Assisted Developer) imitates using AI tools interactively. Both are realistic 2026 workflows. Users choose which pattern they want to present to time trackers.
