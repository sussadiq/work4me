# Terminal & Editor Control

## VS Code + Custom WebSocket Extension (Primary)

VS Code is the primary visible IDE, controlled via the `work4me-bridge` WebSocket extension.

### Architecture

```
VS Code ←── work4me-bridge extension (WebSocket server, port 9876)
   ↑                    ↑
   |                    |
   |            Work4Me Python ──→ VSCodeController (websockets client)
   |
   +── Integrated Terminal (visible commands)
   +── Editor (visible file editing)
```

### Extension Commands

| Command | Params | Action |
|---|---|---|
| `openFile` | `path`, `line` | Open file at line |
| `typeText` | `text` | Insert text at cursor |
| `navigateTo` | `line`, `col` | Move cursor |
| `saveFile` | — | Save active file |
| `getActiveFile` | — | Get current file info |
| `getVisibleText` | — | Get visible editor text |
| `runTerminalCommand` | `cmd`, `name` | Run command in integrated terminal |
| `showTerminal` | — | Focus terminal panel |
| `focusEditor` | — | Focus editor panel |
| `newFile` | `path` | Create and open new file |
| `replaceFileContent` | `content` | Replace active file content |
| `ping` | — | Health check |

### Protocol

JSON over WebSocket: `{id, command, ...params}` → `{id, success, result?, error?}`

### Python Controller

`work4me/controllers/vscode.py` — `VSCodeController` class with methods mapping to each command above, plus `launch()`, `connect()`, `health_check()`, and `cleanup()`.

### Extension Packaging

The extension uses esbuild to bundle `ws` and all code into a single `out/extension.js`, then `@vscode/vsce` creates a `.vsix` for standard installation.

```bash
cd vscode-extension
npm install            # install dev dependencies
npm run compile        # dev build (with sourcemaps)
npm run compile:types  # type-check only (tsc --noEmit)
npm run vsix           # production build + create .vsix
code --install-extension work4me-bridge-0.1.0.vsix
```

The `doctor.py` module can also build and install automatically via `DoctorChecks.install_vscode_extension()`.

---

## tmux (Fallback Terminal Layer)

tmux is the fallback control layer — works with any terminal emulator.

### Setup

```bash
# Create session with two panes
tmux new-session -d -s work4me -x 200 -y 50
tmux split-window -t work4me -h                    # Editor pane (right)
tmux send-keys -t work4me:0.1 'nvim --listen /tmp/work4me-nvim.sock' Enter
```

### Key Operations

| Action | Command |
|---|---|
| Send keystrokes | `tmux send-keys -t work4me:0.0 'git status' Enter` |
| Read output | `tmux capture-pane -t work4me:0.0 -p` |
| Switch panes | `tmux select-pane -t work4me:0.1` |
| Create pane | `tmux split-window -t work4me -v` |
| Resize pane | `tmux resize-pane -t work4me:0.0 -R 20` |
| New window | `tmux new-window -t work4me -n "tests"` |
| Rename window | `tmux rename-window -t work4me:0 "editor"` |
| List panes | `tmux list-panes -t work4me -F '#{pane_id} #{pane_current_command}'` |
| Get pane size | `tmux display-message -t work4me -p '#{pane_width}x#{pane_height}'` |

### Targeting: `-t session:window.pane`

```
-t work4me:0.0    # Session "work4me", window 0, pane 0
-t work4me:0.1    # Session "work4me", window 0, pane 1
```

### Python API: libtmux

```python
import libtmux

server = libtmux.Server()
session = server.new_session(session_name='work4me', kill_session=True)
window = session.active_window
pane_shell = window.active_pane
pane_editor = window.split(direction=libtmux.constants.PaneDirection.Right)

# Send keystrokes
pane_shell.send_keys('git status')

# Read output
output = pane_shell.capture_pane()  # Returns list of lines

# Launch Neovim in editor pane
pane_editor.send_keys('nvim --listen /tmp/work4me-nvim.sock')
```

`libtmux` v0.53, actively maintained. Typed Python API: Server → Session → Window → Pane.

### Control Mode

`tmux -C` starts control mode for structured programmatic interaction (used internally by libtmux).

---

## Kitty Terminal (Rich IPC — Recommended Terminal)

Requires `allow_remote_control yes` in `kitty.conf`.

### Key Commands

| Command | What It Does |
|---|---|
| `kitten @ launch --type=tab --title "Editor"` | Open a new tab |
| `kitten @ send-text --match 'title:Editor' 'vim main.py\n'` | Send text to specific window |
| `kitten @ send-key --match 'title:Editor' ctrl+s` | Send keyboard shortcuts |
| `kitten @ focus-window --match 'title:Editor'` | Switch focus |
| `kitten @ focus-tab --match 'title:Terminal'` | Switch tabs |
| `kitten @ scroll-window 5` | Scroll a window |
| `kitten @ get-text --match 'title:Editor'` | Read window content |
| `kitten @ ls` | List all windows/tabs as JSON |
| `kitten @ resize-window` | Resize |
| `kitten @ close-window` | Close |
| `kitten @ set-tab-title "Building..."` | Rename tab |

### Window Matching

`--match` supports: `title:regex`, `id:N`, `pid:N`, `cwd:/path`, `cmdline:regex`, `env:KEY=VALUE`, and boolean operators (`and`, `or`, `not`).

### Remote Targeting

`--to unix:/path/to/socket` targets a specific Kitty instance.

---

## WezTerm Terminal (Alternative Rich IPC)

### Key CLI Commands

| Command | What It Does |
|---|---|
| `wezterm cli spawn -- bash` | Launch new program in tab |
| `wezterm cli split-pane --right` | Split pane |
| `wezterm cli send-text --pane-id 0 "text"` | Send text to pane |
| `wezterm cli list` | Show window/tab/pane hierarchy |
| `wezterm cli activate-pane --pane-id 1` | Focus a pane |
| `wezterm cli get-text --pane-id 0` | Read pane content |
| `wezterm cli kill-pane --pane-id 1` | Close pane |

Uses `--pane-id` for targeting. Defaults to `$WEZTERM_PANE` env var.

WezTerm config is Lua — can script complex layouts and behaviors.

---

## Other Terminals

- **Alacritty:** No remote control. Not suitable.
- **GNOME Terminal:** Limited D-Bus interface. Mainly supports creating windows/tabs, not sending text. Not recommended.

---

## Neovim (Primary Visible Editor)

### Launch as Server

```bash
nvim --listen /tmp/work4me-nvim.sock
```

### Remote Commands (CLI)

```bash
# Open file
nvim --server /tmp/work4me-nvim.sock --remote main.py

# Open in new tab
nvim --server /tmp/work4me-nvim.sock --remote-tab test.py

# Send keystrokes
nvim --server /tmp/work4me-nvim.sock --remote-send ':e src/auth.ts<CR>'

# Evaluate expression
nvim --server /tmp/work4me-nvim.sock --remote-expr 'line(".")'
```

### Python Control (pynvim)

```python
import pynvim

nvim = pynvim.attach('socket', path='/tmp/work4me-nvim.sock')

# Open file
nvim.command(':e src/middleware/auth.ts')

# Go to line
nvim.command(':42')

# Feed keystrokes
nvim.feedkeys('gg')  # Go to top

# Get buffer content
lines = nvim.current.buffer[:]

# Get cursor position
row, col = nvim.current.window.cursor

# Execute Lua
nvim.exec_lua('vim.lsp.buf.definition()')
```

### neovim-remote (nvr) Tool

```bash
pip install neovim-remote
nvr --servername /tmp/work4me-nvim.sock --remote main.py
nvr --servername /tmp/work4me-nvim.sock --remote-send ':wqa<CR>'
```

### Visible Typing Strategy

**Critical distinction:** Use tmux `send-keys` to type in the Neovim pane (visible on screen). Use pynvim RPC only to query state (cursor position, buffer content, window info).

```python
# VISIBLE: type in Neovim via tmux (seen by screen capture)
await terminal.send_keys_to_pane(editor_pane, 'ifunction authenticate(req) {\n')

# HIDDEN: query state via RPC (not visible)
cursor = nvim.current.window.cursor
buffer_content = nvim.current.buffer[:]
```

---

## VS Code (Alternative Editor)

### CLI Commands

| Command | What It Does |
|---|---|
| `code file.py` | Open a file |
| `code -g file.py:42:10` | Open file at line:column |
| `code -d file1.py file2.py` | Diff two files |
| `code -r .` | Reuse last window, open folder |
| `code -n .` | New window |
| `code --install-extension ext.id` | Install extension |

### Limitations

- No external keystroke injection API (without custom extension)
- Actual editing must go through input simulation (ydotool/portal)
- URL protocol: `vscode://file/{path}:line:column` opens files from external processes

### Custom Extension (Future)

A VS Code extension with WebSocket listener could receive commands from Work4Me:
- `vscode.commands.executeCommand()` for any VS Code command
- Open files, navigate, make edits, run tasks
- Control integrated terminal
- Report current state back

---

## Making Coding Activity Look Natural

### File Exploration Pattern
1. Open project root in editor
2. Browse file tree (navigate directories)
3. Open a few files, scroll through them
4. Focus on one file for editing

### Editing Pattern
1. Open file at specific line
2. Scroll to relevant section (gradual)
3. Make small edits with pauses between changes
4. Save periodically
5. Switch to terminal, run tests/builds
6. Switch back to fix issues

### Terminal Pattern
1. `git status` / `git diff` (review changes)
2. Run tests: `npm test` or `pytest`
3. Build: `npm run build` or `make`
4. Check logs, grep for errors
5. Commit when ready

### Split Pane Layout
- Left: editor (Neovim)
- Right top: terminal for commands
- Right bottom: test output or logs

### Timing
- 2-5 seconds between keystrokes when "thinking"
- 50-150ms between keystrokes when "typing code"
- 5-15 second pauses between logical actions
- Terminal commands every 2-5 minutes
