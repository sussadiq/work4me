# Technology Stack Recommendation

## Chosen: Python 3.11+ with asyncio

## Comparison Table

| Criterion | Python | Node.js/TS | Rust | Go |
|---|---|---|---|---|
| D-Bus Support | **Excellent** (dbus-next, dasbus) | Poor (unmaintained libs) | Excellent (zbus v5) | Good (godbus v5) |
| Desktop Automation | **Best** (dogtail, pyatspi2, hzy) | None native | Minimal | None |
| Child Process Mgmt | Good (asyncio subprocess) | Excellent (execa) | Good (Tokio) | Good (os/exec) |
| Terminal Control | **Best** (libtmux, pynvim) | Shell-out only | Shell-out only | Shell-out only |
| Browser Automation | Good (Playwright bindings) | Best (Playwright native) | Poor | Poor |
| Development Speed | **Fastest** | Fast | Slow (3-5x penalty) | Moderate |
| Long-Running Daemon | Very Good (asyncio mature) | Good (needs memory care) | Excellent | Excellent |
| Packaging | Good (PyInstaller, pipx) | Good (SEA) | Best (static binary) | Very Good |

## Detailed Analysis

### Python (Chosen)

**D-Bus:**
- `dbus-next` — pure Python, native asyncio support, zero dependencies. Best for modern async code.
- `dasbus` — wrapper around GDBus+pygobject, used by Anaconda (Red Hat's installer). Requires GLib event loop.
- `dbus-python` (freedesktop.org) — deprecated for over a decade, do not use.
- **Recommendation:** `dbus-next` for asyncio compatibility.

**Desktop Automation:**
- `dogtail 1.0+` (released Aug 2024) — Wayland-enabled accessibility-based automation. Uses AT-SPI + ScreenCast/RemoteDesktop portal. Works on both X11 and Wayland (GNOME + GTK apps).
- `pyatspi2` — lower-level accessibility API.
- `hzy` — Python bindings for libei (Wayland input emulation standard). Reached 1.0 in 2023.
- `wayland-automation` (v0.2.6, Jan 2026) — new library for mouse/keyboard on Wayland. Multi-compositor.

**Terminal/Editor Control:**
- `libtmux` (v0.53) — typed Python API for tmux: Server → Session → Window → Pane objects. Actively maintained.
- `pynvim` — full async RPC to Neovim via Unix socket. Open files, send keys, query state.

**Subprocess Management:**
- `asyncio.create_subprocess_exec()` — solid async subprocess control.
- Manage Claude Code CLI, tmux, ydotool as child processes.

**Packaging:**
- PyInstaller — bundles Python interpreter + dependencies into single file/directory. ~4.76M monthly downloads.
- Nuitka — compiles to C then native. 2-4x faster but overkill for I/O-bound work.
- `pipx` — for distribution as a Python package (requires Python on system).

**Daemon Stability:**
- asyncio event loop is solid for long-running processes.
- Memory management with refcount + cyclic GC is predictable.
- GIL is irrelevant — workload is 100% I/O-bound (subprocesses, timers, D-Bus).
- Python 3.14 has free-threading but unnecessary for this use case.

### Node.js/TypeScript (Alternative)

**Strengths:**
- Playwright is native to Node.js (Python version spawns a Node subprocess internally).
- `execa` library provides excellent child process management with structured IPC.
- TypeScript type system is stronger than Python's for complex state machines.
- Async scheduling ecosystem: BullMQ, node-schedule, Agenda.

**Weaknesses:**
- D-Bus libraries are unmaintained: `dbus-next` (4 years old), `dbus-native` (7 years old).
- No desktop automation libraries for Wayland.
- PM2 has memory issues (230MB on 512MB machine). Better to run under systemd directly.
- Node.js SEA (Single Executable Applications) still has native module issues.

**When to choose Node.js instead:** If browser automation is the dominant use case and D-Bus interaction is minimal.

### Rust (Not Recommended)

**Strengths:**
- `wayland-rs` / `smithay-client-toolkit` — real Wayland client bindings.
- `zbus` v5 — excellent pure Rust D-Bus with async support.
- Single static binary distribution.
- Memory safety for long-running processes.

**Weaknesses:**
- Development speed 3-5x slower than Python for orchestration code.
- No desktop automation ecosystem (no dogtail equivalent).
- Borrow checker/lifetimes add complexity for zero benefit in I/O-bound orchestration.

### Go (Not Recommended)

**Strengths:**
- `godbus` v5 — solid D-Bus library.
- goroutines for concurrency.
- Single static binary.

**Weaknesses:**
- Wayland bindings exist but immature.
- No desktop automation ecosystem at all.

### Hybrid Approach (Considered, Not Recommended for MVP)

- PyO3/maturin for Rust↔Python FFI is mature (50k+ downloads/day).
- Only justified if writing a custom uinput driver or libei client.
- If delegating input simulation to ydotool/dotool (subprocess calls), no need for Rust.

## Key Python Libraries

| Library | Purpose | Version/Status |
|---|---|---|
| `dbus-next` | D-Bus (RemoteDesktop portal, AT-SPI) | Pure Python, asyncio native |
| `libtmux` | tmux programmatic control | v0.53, actively maintained |
| `pynvim` | Neovim RPC | Stable, async support |
| `playwright` | Browser automation (Chromium CDP) | Python bindings by Microsoft |
| `dogtail` | Accessibility-based UI automation | v1.0+, Wayland support |
| `numpy` | Gaussian noise, Bezier curves | Stable |
| `tomli` / `tomllib` | TOML config parsing | stdlib in 3.11+ |

## Trade-offs Accepted

1. Playwright for Python spawns a Node.js subprocess internally (slight overhead vs native Node.js).
2. Type safety is weaker than TypeScript — mitigated with mypy/pyright.
3. Node.js is still a dependency regardless — Claude Code CLI requires it.
