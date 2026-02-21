# Work4Me — Project Overview

## What Is Work4Me?

Work4Me is a Linux desktop AI agent that replicates the full observable workflow of a human software engineer. Given a task description and a time budget, it autonomously plans, researches, and codes — producing real, meaningful work while generating realistic, natural desktop activity that is fully visible to time-tracking/screenshot tools (Hubstaff, Time Doctor, Toggl, TopTracker, etc.).

## The Core Problem

AI tools like Claude Code can complete engineering tasks in minutes. But remote engineers and contractors are monitored by time trackers that take periodic screenshots, measure keyboard/mouse activity, and log app usage. A task completed in 2 minutes but billed for 4 hours creates a mismatch. Work4Me bridges this gap — it does the real work but paces it like a human across the user-defined time window.

## The Core Architectural Insight

Claude Code runs headless doing real work at full speed, and Work4Me intercepts its actions (via stream-json) and **replays them visibly** through desktop applications at human speed. The work is real; the pacing is simulated.

```
Claude Code (headless, fast)     Work4Me (visible, paced)
         |                              |
  Writes auth.ts in 5 sec  -->  Types auth.ts char-by-char at 60 WPM over 15 min
  Runs "npm test" in 1 sec -->  Types "npm test" visibly, watches output
  Searches docs mentally   -->  Opens browser, scrolls Stack Overflow
```

## What It Must Do

1. **Accept a task** — User provides description + time budget (e.g., "Build a REST API with auth", 4 hours)
2. **Plan the work** — Break into subtasks, generate prompts, plan a natural workflow schedule
3. **Execute visibly** — Open real apps (browser, terminal, IDE), perform real actions, produce real output
4. **Pace like a human** — Distribute work naturally with realistic patterns (research, coding bursts, breaks, debugging)
5. **Handle autonomy** — Resolve errors, grant permissions to Claude Code, handle build failures
6. **Produce real results** — Actual code, actual commits, actual working software

## Constraints

- **Target Platform (Phase 1):** Linux with Wayland (GNOME/Mutter primary, Sway secondary)
- **Future Platforms:** macOS, Windows, X11 Linux (design with portability in mind)
- **The work must be REAL** — not a screen faker
- **Activity must be VISIBLE** — every action visible in screenshots
- **The agent must be AUTONOMOUS** — zero user intervention once started
- **Time tracking compliance** — activity patterns must satisfy time tracker detection

## Key Decisions (Summary)

| Decision | Choice | Rationale |
|---|---|---|
| Language | Python 3.11+ with asyncio | Best D-Bus, desktop automation, terminal control ecosystem |
| Input simulation | ydotool/dotool (universal) + RemoteDesktop portal (GNOME) | Only universal Wayland input methods |
| AI engine | Claude Code CLI (`claude -p --output-format stream-json`) | Full headless support, stream parsing |
| Terminal | tmux (universal) + Kitty/WezTerm (rich control) | `send-keys` + `capture-pane` |
| Editor | Neovim (via pynvim RPC) | Best programmatic control of any editor |
| Browser | Chromium via CDP/Playwright | `--remote-debugging-port` + visible window |
| Distribution | Tarball + install script | Flatpak/Snap blocked by sandbox |

## Document Index

| File | Contents |
|---|---|
| `00-overview.md` | This file — project overview and key decisions |
| `01-stack-recommendation.md` | Technology stack comparison and recommendation |
| `02-wayland-platform.md` | Wayland automation capabilities, limitations, compositor matrix |
| `03-architecture.md` | System architecture — processes, modules, state machine, data flow |
| `04-claude-code-integration.md` | Claude Code CLI flags, stream-json parsing, session management |
| `05-browser-automation.md` | Chromium CDP, Playwright, human-like browsing |
| `06-terminal-editor-control.md` | tmux, Kitty, WezTerm, Neovim, VS Code control |
| `07-behavior-model.md` | Human-like activity patterns, typing, mouse, idle, anti-detection |
| `08-task-scheduling.md` | Task decomposition, scheduling algorithms, adaptive pacing |
| `09-risk-analysis.md` | Technical risks, limitations, mitigation strategies |
| `10-implementation-roadmap.md` | Phased development plan with milestones |
| `11-distribution.md` | Packaging, dependencies, setup flow, permissions |
| `12-prior-art.md` | Existing tools, AI desktop agents, time tracker analysis |
