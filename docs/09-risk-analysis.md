# Risk Analysis

## Technical Risks

| Risk | Severity | Likelihood | Mitigation |
|---|---|---|---|
| **GNOME screenshots require user consent every time** | High | High | Use ScreenCast portal with persistent restore tokens (one-time consent). For self-monitoring only — not critical for MVP. |
| **ydotool daemon instability** | Medium | Medium | Systemd user service with auto-restart. dotool as alternative. Health check in watchdog. |
| **Claude Code API rate limits / cost overruns** | High | Medium | `--max-budget-usd` per invocation. Cache outputs. Reuse sessions via `--resume`. |
| **Time tracker updates detection heuristics** | High | Low | ActivityMonitor with conservative thresholds. All behavior parameters are configurable. |
| **Wayland compositor differences break assumptions** | Medium | High | Compositor abstraction layer. MVP targets GNOME only. Test each compositor before claiming support. |
| **tmux send-keys timing issues** | Low | Medium | Verify output after each command. Retry with exponential backoff. |
| **Neovim RPC disconnection** | Medium | Low | Health check + auto-restart in tmux pane. Reconnect pynvim client. |
| **Browser crash mid-session** | Medium | Medium | Re-launch Chromium with same debug port. Restore from last URL in state file. |
| **State corruption on crash** | High | Low | Atomic state writes (write tmp, rename). JSON schema validation on load. |
| **Long-running Python process memory leaks** | Medium | Medium | Periodic memory checks in watchdog. Asyncio is well-suited but must avoid closure leaks and unbounded caches. |
| **Claude Code changes CLI interface** | Medium | Low | Version pin Claude Code. Abstract CLI interaction behind ClaudeCodeManager. |
| **User accidentally interacts during session** | Low | High | Interrupt detection (unexpected input). Agent backs off, resumes when user leaves. |

## Known Limitations

1. **GNOME window management is limited** — no native CLI for move/resize/focus. Must rely on D-Bus extensions or AT-SPI accessibility APIs. This is the weakest part of GNOME automation.

2. **Neovim is effectively required for visible coding** — VS Code automation is significantly harder without a custom extension. Users who prefer VS Code will need to accept Neovim for the visible work (the actual code is the same regardless).

3. **Node.js is a dependency** regardless of Python stack choice — Claude Code CLI is a Node.js application installed via npm.

4. **First-run requires user consent** for RemoteDesktop portal session (screen sharing dialog). With persistent restore tokens, this is one-time only.

5. **uinput requires initial sudo** for udev rule installation. This is a one-time setup step in the install script.

6. **Playwright for Python spawns Node.js** internally — slight overhead and an additional runtime dependency.

7. **Activity simulation is statistical, not perfect** — sophisticated statistical analysis of keystroke timing could potentially distinguish simulated from real typing. Current time trackers don't do this level of analysis.

8. **Single-task focus** — Work4Me handles one task at a time. It cannot simulate the multi-tasking of a developer working on PRs from different repos simultaneously.

## Security Considerations

### System Access
Work4Me has significant system access:
- `/dev/uinput` — can inject keyboard/mouse input to any application
- Claude Code with `--dangerously-skip-permissions` — can read/write any file, run any command
- Browser control via CDP — full access to browser state
- tmux — can read terminal output including sensitive information

### Guardrails Needed
1. **Sandboxed working directory** — Claude Code should only operate within the specified project directory
2. **`--disallowedTools`** — block dangerous tools (e.g., `Bash(rm -rf *)`, `Bash(curl * | bash)`)
3. **Cost limits** — always set `--max-budget-usd` to prevent runaway API costs
4. **Process isolation** — Work4Me daemon should run as the user, not root
5. **No credential access** — Claude Code should not access `.env` files, SSH keys, or credential stores
6. **Activity logging** — all actions are logged to JSONL for audit

### User Trust Model
- The user explicitly starts Work4Me and provides the task
- The user trusts Claude Code to operate in their project
- Work4Me acts within the scope the user defines
- All activity is logged and reviewable post-session

## Failure Modes and Recovery

### Graceful Degradation Chain

```
RemoteDesktop portal fails → Fall back to ydotool
Kitty IPC fails → Fall back to tmux send-keys
Neovim RPC fails → Fall back to tmux send-keys to nvim pane
Playwright connection fails → Fall back to direct CDP WebSocket
Browser crashes → Re-launch, restore last URL
tmux session dies → Re-create session, restore panes
Claude Code times out → Retry with adjusted prompt
Claude Code gives bad output → Skip activity, replan
```

### Unrecoverable Failures

| Failure | Impact | User Action Required |
|---|---|---|
| Claude API key invalid/expired | Cannot do any work | Update API key in config |
| Disk full | Cannot write code or state | Free disk space |
| uinput access lost | Cannot simulate input | Re-run install script, re-login |
| Compositor crashed | Desktop is gone | Wait for compositor recovery |
| All retry attempts exhausted | Activity stuck | Check `work4me log`, restart |
