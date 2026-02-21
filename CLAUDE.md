# Work4Me — Desktop AI Agent

## Quick Reference
- **What:** Linux desktop AI agent that drives real software engineering tools (editor, terminal, browser) with human-like pacing
- **Stack:** Python 3.11+, asyncio, hatchling build
- **Entry point:** `work4me.cli:main` → `work4me start --task "..." --hours 4`

## Project Layout
- `work4me/` — main package
  - `cli.py` — argparse CLI with start/stop/status/doctor subcommands
  - `config.py` — nested dataclasses, TOML loading from `~/.config/work4me/config.toml`
  - `core/` — orchestrator (main loop), state machine, event system
  - `planning/` — task planner (Claude-powered), scheduler (work sessions/breaks)
  - `controllers/` — claude_code, vscode, browser, terminal, editor
  - `behavior/` — typing simulation, mouse, activity monitor, behavior engine
  - `desktop/` — input simulation (ydotool/dotool)
- `tests/` — pytest suite (130+ tests), mirrors source structure
- `docs/` — 13 design docs (00-12), living documentation — keep these updated
- `vscode-extension/` — companion VS Code extension for WebSocket control

## Code Conventions
- `from __future__ import annotations` in every module
- One `logger = logging.getLogger(__name__)` per module (or `"work4me"` in cli)
- Config via nested `@dataclass` classes, not dicts
- Async-first: orchestrator and controllers are async, tests use `@pytest.mark.asyncio`
- Strict mypy (`strict = true` in pyproject.toml)

## Testing
- `python -m pytest tests/ -q` — run all tests
- `python -m pytest tests/test_foo.py -q` — run one file
- `pytest-asyncio` with `asyncio_mode = "auto"` — no need to mark individual async tests
- Mock-heavy: `unittest.mock.AsyncMock` for async controllers, `patch()` for isolation
- Test files: `tests/test_<module>.py` matching `work4me/<module>.py`

## Design Docs (docs/)
These are living documentation — update them when making architectural changes:
- `00-overview.md` through `12-prior-art.md` cover architecture, platform, integration decisions
- `docs/plans/` — implementation plans

## Key Architecture
- Claude Code CLI runs headless → Work4Me replays actions visibly at human speed
- Single asyncio process, all I/O-bound concurrency (no threads except where forced)
- Two modes: "manual" (step-by-step) and "ai-assisted" (autonomous)
- GNOME/Wayland first, Sway second target
