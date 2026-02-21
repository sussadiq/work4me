# Implementation Roadmap

## Current Implementation Status

The architecture revision (dual-mode, VS Code, interleaved execution) has been implemented. See `docs/plans/2026-02-21-implementation-plan.md` for the detailed task breakdown.

### Completed (Phase 1 — Architecture Revision)

| # | Component | Files | Tests |
|---|-----------|-------|-------|
| 1 | Config updates | `config.py` | 6 pass |
| 2 | VS Code extension | `vscode-extension/` (TypeScript) | compiles |
| 3 | VS Code Python controller | `controllers/vscode.py` | 8 pass |
| 4 | Task planner | `planning/task_planner.py` | 4 pass |
| 5 | Scheduler | `planning/scheduler.py` | 5 pass |
| 6 | Browser controller | `controllers/browser.py` | 6 pass |
| 7 | Activity monitor | `behavior/activity_monitor.py` | 7 pass |
| 8 | Mouse simulation | `behavior/mouse.py` | 6 pass |
| 9 | Orchestrator rewrite | `core/orchestrator.py` | 7 pass |
| 10 | CLI + dependencies | `cli.py`, `pyproject.toml` | 3 pass |
| 11 | Integration smoke test | `tests/test_integration.py` | 1 pass |
| 12 | Documentation update | `docs/` | — |

**Total: 53 tests, ~3500 LOC (Python + TypeScript)**

### Next Phase — Hardening & Polish

- **RemoteDesktop portal** input for GNOME (replace ydotool)
- **Compositor abstraction** (Sway, Hyprland)
- **Screen capture** for self-monitoring
- **Error recovery** — controller health checks, crash recovery
- **Human interrupt detection** — back off when user is present
- **Install script** and packaging
- **Adaptive pacing** — ahead of schedule → add tests/docs, behind → prioritize
- **TOML config file** support

### What Success Looks Like

- Human-like activity that passes Hubstaff/Time Doctor inspection
- Real code, real commits, real working software produced
- Autonomous 4-hour sessions with zero user intervention
- Graceful error recovery and state persistence
