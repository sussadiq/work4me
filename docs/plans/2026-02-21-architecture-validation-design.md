# Architecture Validation & Revision Design

**Date:** 2026-02-21
**Status:** Approved
**Scope:** Full architecture review — feasibility, visual correctness, cost-effectiveness

## Context

After implementing ~18 Python files covering the core flow (state machine, Claude Code integration, human-like typing, input simulation, terminal control), a deep review of all 13 design docs against the code and real-world constraints revealed 5 significant issues requiring architectural changes.

## Key Decisions

### 1. Interleaved Execution (was: batch-then-replay)

**Problem:** The original design runs Claude Code once for the entire task, then replays all actions visibly. This produces a 4-hour session of typing pre-computed code with zero real debugging — unrealistic and brittle.

**Decision:** Run Claude Code per-activity from the upfront plan. Each activity (~15-45 min visible) gets its own Claude Code invocation. If Claude Code hits errors during an activity, the visible session shows real troubleshooting.

**Cost impact:** Zero — Claude Code Max ($100/mo unlimited) eliminates per-invocation costs. Interleaved execution is free.

### 2. Dual Operating Modes

**Decision:** Two user-selectable modes:

**Mode A — Manual Developer:** Imitates a developer coding by hand. Claude Code runs headless per-activity, Work4Me replays actions visibly in VS Code at human speed. Best for contexts where AI tool usage isn't expected.

**Mode B — AI-Assisted Developer:** Imitates a developer using Claude Code interactively. Work4Me types prompts into a visible Claude Code terminal session (via `--input-format stream-json`), reviews output in VS Code, makes minor visible tweaks. More realistic for 2026, easier to implement.

Both modes share: upfront task planning, session/break scheduling, human-like activity patterns, browser research phases, anti-detection monitoring.

### 3. VS Code + Custom Extension (was: tmux + Neovim)

**Problem:** Neovim in a tmux session looks niche in screenshots. tmux sessions created with `-d` (detached) are invisible to time trackers.

**Decision:** Launch stock VS Code, control via a small WebSocket extension (~300-400 LOC TypeScript). The extension exposes commands:

```
WebSocket server on localhost:9876
  openFile(path, line?)          → Opens file at line
  typeText(text)                 → Types text at cursor position
  navigateTo(line, col)          → Move cursor
  saveFile()                     → Save current file
  runTerminalCommand(cmd)        → Execute in integrated terminal
  getActiveFile()                → Return current file path
  getVisibleText()               → Return visible editor content
  showTerminal() / hideTerminal()
  focusEditor() / focusTerminal()
```

Work4Me's Python side connects via `websockets` library and sends JSON commands. tmux retained as fallback for Mode B terminal display.

### 4. Hybrid File Write Strategy (was: Claude writes, Neovim re-types)

**Problem:** Claude Code writes files headlessly to disk, then Work4Me re-types the already-written code as visual theater. File timestamps don't match visible typing activity.

**Decision:**

| Scenario | Strategy | Rationale |
|----------|----------|-----------|
| New file creation | Work4Me types code into VS Code, saves via extension | Timestamps match visible activity |
| Existing file edit | Claude writes headlessly, VS Code reloads, Work4Me scrolls reviewing | Natural "review my changes" pattern |
| Terminal commands | Work4Me types into VS Code terminal | Always visible |
| Git operations | Work4Me types git commands in terminal | Always visible |

### 5. Browser Automation from Phase 1 (was: Phase 4)

**Problem:** Pure IDE sessions lack activity variety. Time trackers flag monotonic patterns.

**Decision:** Include Chromium/Playwright from the start. During BROWSER activities in the plan, Work4Me opens real browser pages (docs, Stack Overflow, GitHub), scrolls at reading speed, types search queries. Claude Code's planning phase includes `search_queries` per activity to drive visible browsing.

## Revised Process Architecture

```
work4me (main daemon)                     # Python asyncio, single process
  │
  ├── Claude Code CLI                     # Per-activity invocations
  │     Mode A: headless (-p --output-format stream-json)
  │     Mode B: interactive (--input-format stream-json, visible output)
  │
  ├── VS Code                             # Visible IDE
  │     └── work4me-extension             # WebSocket bridge
  │
  ├── Chromium                            # Visible browser
  │     └── Playwright/CDP               # Programmatic control
  │
  ├── ydotoold                            # Universal input fallback
  │
  └── (optional) tmux                     # Mode B terminal display
```

## Revised Execution Flow

### Planning Phase (shared, both modes)

1. One Claude Code headless invocation decomposes task into JSON activities
2. Scheduler maps activities to 4 work sessions with variable breaks
3. Each activity tagged: CODING, READING, TERMINAL, BROWSER, THINKING

### Mode A Execution (per activity)

1. Claude Code runs headless for this activity
2. Captures tool_use events (Edit/Write/Bash)
3. New files: type into VS Code via extension, save
4. File edits: Claude writes headlessly, VS Code reloads, Work4Me scrolls reviewing
5. Commands: type into VS Code integrated terminal
6. Between activities: think pauses, context switches

### Mode B Execution (per activity)

1. Focus visible terminal with Claude Code session
2. Work4Me types the prompt at human speed (via `--input-format stream-json`)
3. Claude Code runs — output visible in terminal in real-time
4. When done: switch to VS Code, browse changed files, scroll through reviewing
5. Optional: make small visible edits/tweaks via VS Code extension
6. Switch back, type next prompt

### Browser Activities (both modes)

Open Chromium via Playwright, navigate to URLs from activity plan, scroll at reading speed, type search queries character-by-character, switch between tabs, leave documentation tabs open during coding phases.

## Revised Module Structure

```
work4me/
  __main__.py, cli.py, config.py, daemon.py

  core/
    orchestrator.py        # Revised: dual-mode execution loop
    state.py               # Existing: validated, solid
    events.py              # Existing: validated, solid

  planning/
    task_planner.py        # NEW: Claude Code task decomposition → JSON
    scheduler.py           # NEW: Session/break time mapping
    time_budget.py         # NEW: Time arithmetic, budget tracking

  desktop/
    compositor.py          # Compositor detection and abstraction
    input_sim.py           # Existing: dotool/ydotool, validated
    window_mgr.py          # Window focus, positioning (compositor-specific)

  controllers/
    claude_code.py         # Existing: extend for --input-format stream-json (Mode B)
    vscode.py              # NEW: WebSocket client for VS Code extension
    browser.py             # NEW: Chromium via Playwright/CDP
    terminal.py            # Existing: keep for tmux fallback

  behavior/
    engine.py              # Existing: validated, solid
    typing.py              # Existing: validated, solid
    mouse.py               # NEW: Bezier curves, Fitts's law
    timing.py              # NEW: Activity/idle pattern generation
    activity_monitor.py    # NEW: Anti-detection constraint enforcement

  vscode-extension/        # NEW: TypeScript VS Code extension
    src/extension.ts       # WebSocket server + VS Code API bridge
    package.json
```

## What's Validated and Unchanged

These components are confirmed solid after review:

- **Python 3.11 + asyncio** single-process architecture — correct for 100% I/O-bound workload
- **State machine** (10 states, validated transitions) — well-implemented in `core/state.py`
- **Event bus** — typed async, clean implementation in `core/events.py`
- **HumanTyper** — sophisticated keystroke timing (fast bigrams, adjacent-key typos, burst patterns) in `behavior/typing.py`
- **BehaviorEngine** — think pauses, activity tracking, break simulation in `behavior/engine.py`
- **Input simulation** (dotool/ydotool) — universal Wayland support in `desktop/input_sim.py`
- **ClaudeCodeManager** — production-quality stream-json parsing in `controllers/claude_code.py`
- **Anti-detection constraints** — well-researched Hubstaff thresholds in `docs/07-behavior-model.md`
- **3-level task decomposition** (Feature → Activity → MicroAction) design
- **Session structure** (4 sessions, variable breaks, Gaussian noise) design
- **Config system** — clean dataclass-based configuration in `config.py`
- **CLI** — functional with start/stop/status/doctor commands

## Changes from Original Docs

| Original Design | Revised Design | Reason |
|-----------------|---------------|--------|
| Single batch Claude Code execution | Interleaved per-activity execution | More realistic, enables real debugging |
| Single mode (manual coding) | Dual mode (manual + AI-assisted) | Mode B more realistic for 2026, easier to build |
| tmux + Neovim as visible IDE | VS Code + custom extension | More credible in screenshots |
| Browser in Phase 4 (week 7-8) | Browser from Phase 1 | Activity variety needed immediately |
| `max_budget_usd = 5.0` per session | No budget cap (Max plan) | Unlimited invocations |
| File write: Claude writes, Neovim re-types | Hybrid: new files typed, edits reloaded+reviewed | Consistent timestamps |

## Risk Updates

| New Risk | Severity | Mitigation |
|----------|----------|------------|
| VS Code extension maintenance | Low | Small surface area (~300 LOC), stable VS Code API |
| Mode B: detecting Claude Code readiness | Medium | `--input-format stream-json` provides structured control |
| Browser adds complexity to MVP | Medium | Playwright abstracts CDP; human-like patterns are configurable |
| Dual mode increases test surface | Medium | Shared planning/behavior modules minimize duplication |
