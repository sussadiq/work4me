# Claude Code CLI Integration

## Invocation

```bash
claude -p "prompt" \
  --output-format stream-json \
  --dangerously-skip-permissions \
  --max-turns 10 \
  --max-budget-usd 1.0 \
  --model sonnet
```

## Complete Flag Reference

### Core Invocation Patterns

| Command | Description |
|---|---|
| `claude` | Start interactive REPL |
| `claude "query"` | Start REPL with initial prompt |
| `claude -p "query"` | Non-interactive print mode — run, print result, exit |
| `cat file \| claude -p "query"` | Process piped content via stdin |
| `claude -c` | Continue most recent conversation |
| `claude -r "session" "query"` | Resume a specific session by ID or name |

### Key Flags for Automation

| Flag | Purpose |
|---|---|
| `--print`, `-p` | Non-interactive mode |
| `--dangerously-skip-permissions` | Skip ALL permission prompts (auto-approve everything) |
| `--allowedTools` | Tools that execute without prompting (e.g., `"Bash(git log *)" "Read"`) |
| `--disallowedTools` | Tools completely removed from context |
| `--tools` | Restrict which built-in tools are available (e.g., `"Bash,Edit,Read"`) |
| `--model` | Select model (`sonnet`, `opus`, or full model ID) |
| `--max-budget-usd` | Cost cap before stopping (print mode only) |
| `--max-turns` | Limit agentic turns (print mode only) |
| `--output-format` | `text`, `json`, or `stream-json` |
| `--continue`, `-c` | Continue most recent conversation |
| `--resume`, `-r` | Resume a specific session by ID or name |
| `--session-id` | Use a specific UUID for the session |
| `--append-system-prompt` | Add instructions while keeping defaults |
| `--system-prompt` | Completely replace the system prompt |
| `--mcp-config` | Load MCP servers from a JSON file |
| `--json-schema` | Get validated JSON output matching a schema |
| `--verbose` | Full turn-by-turn logging |
| `--permission-mode` | `default`, `acceptEdits`, `plan`, `dontAsk`, `bypassPermissions` |
| `--fallback-model` | Fallback model when primary is overloaded |
| `--no-session-persistence` | Don't save session to disk |
| `--add-dir` | Add additional working directories |
| `--worktree`, `-w` | Start in an isolated git worktree |
| `--input-format stream-json` | Feed structured input programmatically |
| `--fork-session` | Create new session ID when resuming |

## Output Formats

### stream-json (Primary for Work4Me)

Real-time newline-delimited JSON events:

```bash
claude -p "Write auth middleware" \
  --output-format stream-json \
  --verbose \
  --include-partial-messages
```

Filter for text deltas:
```bash
claude -p "Write a poem" --output-format stream-json --verbose --include-partial-messages | \
  jq -rj 'select(.type == "stream_event" and .event.delta.type? == "text_delta") | .event.delta.text'
```

Key event types to capture:
- `tool_use` where tool is `Edit` → code to replay visibly
- `tool_use` where tool is `Bash` → command to replay visibly
- `result` → final summary with `session_id` for resumption

### json (For Structured Output)

```bash
claude -p "Extract function names" \
  --output-format json \
  --json-schema '{"type":"object","properties":{"functions":{"type":"array","items":{"type":"string"}}}}'
```

Returns: `result`, `session_id`, usage metadata. Structured result in `structured_output` field.

## Session Management

### Continue/Resume

```bash
# Continue most recent
claude -c -p "Check for errors"

# Resume specific session
session_id=$(claude -p "Start review" --output-format json | jq -r '.session_id')
claude -p "Continue review" --resume "$session_id"

# Fixed session ID
claude --session-id "550e8400-e29b-41d4-a716-446655440000" -p "query"

# Fork (preserves original)
claude --fork-session --resume "$session_id" -p "try alternative"
```

### CLAUDE.md Files

Persistent context across sessions. Read at start of every session.

| Location | Scope |
|---|---|
| `~/.claude/CLAUDE.md` | Global — personal preferences |
| `./CLAUDE.md` or `./.claude/CLAUDE.md` | Project — team conventions (committed to git) |
| `./.claude/CLAUDE.local.md` | Local project — personal notes (gitignored) |

Supports `@path/to/import` syntax for importing other files.

**For Work4Me:** Use CLAUDE.md for persistent project context (architecture, build commands, coding standards) without consuming conversation tokens.

## Permission System

### Permission Tiers

| Tool Type | Example | Approval Required |
|---|---|---|
| Read-only | File reads, Grep, Glob | No |
| Bash commands | Shell execution | Yes |
| File modification | Edit/Write | Yes |

### Permission Modes

| Mode | Behavior |
|---|---|
| `default` | Prompts on first use |
| `acceptEdits` | Auto-accepts file edits |
| `plan` | Read-only, no modifications |
| `dontAsk` | Auto-denies unless pre-approved |
| `bypassPermissions` | Skips all prompts (requires `--dangerously-skip-permissions`) |

### Settings Files

- `~/.claude/settings.json` — user-level
- `.claude/settings.json` — project-level (shared)
- `.claude/settings.local.json` — local project
- `/etc/claude-code/managed-settings.json` — system-wide

```json
{
  "permissions": {
    "allow": ["Bash(npm run *)", "Bash(git commit *)", "Read", "Edit"],
    "deny": ["Bash(git push *)", "Bash(rm -rf *)"]
  }
}
```

### AllowedTools Syntax

Uses glob patterns: `"Bash(git diff *)"` allows any command starting with `git diff `. The space before `*` matters.

**Known bug:** `--allowedTools` may be ignored in non-interactive mode with `bypassPermissions`. Use `--disallowedTools` (works correctly) or `--dangerously-skip-permissions`.

## MCP (Model Context Protocol)

Claude Code fully supports MCP servers.

```bash
# Add MCP server
claude mcp add --transport stdio my-server -- npx -y my-package
claude mcp add --transport http my-api https://api.example.com/mcp

# Config file: .mcp.json
{
  "mcpServers": {
    "my-server": {
      "command": "/path/to/server",
      "args": [],
      "env": {}
    }
  }
}

# Load at startup
claude --mcp-config ./mcp.json -p "query"

# Claude Code as MCP server
claude mcp serve
```

**For Work4Me:** Could expose an MCP server giving Claude Code additional tools (project management queries, browser automation, terminal state).

## Error Handling

### Exit Codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | General error |
| 2 | Configuration error |
| 126 | Permission denied |
| 127 | Command not found |
| 130 | Interrupted (SIGINT) |

### Programmatic Error Handling

```python
proc = await asyncio.create_subprocess_exec(
    'claude', '-p', prompt,
    '--output-format', 'stream-json',
    '--dangerously-skip-permissions',
    '--max-turns', str(max_turns),
    '--max-budget-usd', str(max_budget),
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
    cwd=working_dir
)

async for line in proc.stdout:
    event = json.loads(line)
    # Process stream-json events...

await proc.wait()
if proc.returncode != 0:
    stderr = await proc.stderr.read()
    # Handle error based on return code
```

## API Alternative

### When to Use Anthropic API Directly

| Aspect | Claude Code CLI | Anthropic API |
|---|---|---|
| Tool use | Built-in (Read, Edit, Bash, Glob, Grep) | Define your own tools |
| Agent loop | Automatic with retry/context management | Build your own |
| Session mgmt | Built-in (continue, resume) | Manual |
| Computer Use | Not applicable | Beta tool for GUI control |
| Token efficiency | Higher overhead (system prompt, tools) | 37% reduction possible |
| Cost control | `--max-budget-usd` | Manual tracking |

**Recommendation for Work4Me:** Use Claude Code CLI for software engineering tasks (already has all tools). Use API directly only for Computer Use GUI interaction or to minimize token costs on specific workflows.

## Model Configuration

Work4Me supports separate models for task planning and coding:

- **`claude.model`** (default: `sonnet`) — used by the main `ClaudeCodeManager` for coding activities
- **`claude.planning_model`** (default: `sonnet`) — used by `TaskPlanner` for task decomposition

The planning invocation uses `--disallowedTools` to prevent Claude from exploring the codebase (Edit, Bash, Read, etc.) instead of returning a JSON plan. Without this, Claude may spend all `max_turns` on tool calls and return empty text. The planner also sets `max_turns=1` as an additional safeguard.

This split saves costs since planning/decomposition doesn't need a powerful model. Configure via TOML:

```toml
[claude]
model = "sonnet"           # For coding
planning_model = "sonnet"  # For task decomposition (can use "haiku" to save costs)
```

Or via CLI flags:

```bash
work4me start --task "..." --model sonnet --planning-model haiku
```

## Claude Code Prompt Templates

### Task Decomposition Prompt

```
You are a senior software engineer planning a coding task. Decompose the following task into a sequence of developer activities.

Task: {task_description}
Time Budget: {hours} hours
Project Context: {project_context}

For each activity, specify:
1. kind: one of CODING, READING, TERMINAL, BROWSER, THINKING
2. description: what the developer does
3. estimated_minutes: how long it should take
4. files_involved: which files will be created/modified/read
5. commands: any terminal commands to run
6. search_queries: any web searches needed
7. dependencies: IDs of activities that must complete first

Return as JSON array. Total estimated_minutes ≈ {hours * 60 * 0.70} (70% of budget).
```

### Coding Activity Prompt

```
You are working on: {activity.description}

Project directory: {working_dir}
Files to modify: {activity.files_involved}

Write the code. Use Edit tool for file changes and Bash tool for terminal commands.
Follow the project's existing style and conventions.
{project_context_from_claude_md}
```

## Claude Code VS Code Extension (Sidebar Mode)

### Overview

The primary operating mode drives the Claude Code VS Code extension sidebar directly. This looks like a real developer using AI tools in 2026.

### Extension Bridge Commands

The work4me-bridge VS Code extension exposes these commands via WebSocket:

| Command | Action | Response |
|---|---|---|
| `checkClaudeExtension` | Check if Claude Code extension is installed/active | `{installed, active}` |
| `openClaudeCode` | Validate extension, activate if needed, open sidebar | `{opened, extensionActive, extensionVersion}` — throws if not installed or activation fails |
| `focusClaudeInput` | Focus the Claude Code input box | `{focused}` |
| `blurClaudeInput` | Remove focus from input box | `{blurred}` |
| `newClaudeConversation` | Start a fresh conversation | `{newConversation}` |
| `acceptDiff` | Accept the currently proposed diff | `{accepted}` |
| `rejectDiff` | Reject the currently proposed diff | `{rejected}` |
| `sendClaudePrompt` | Paste prompt + submit via clipboard (focus + paste with trailing `\n` + restore) | `{prompted, length, submitted}` |
| `configureClaudePermissions` | Set `claudeCode.initialPermissionMode` in VS Code settings | `{configured, mode}` |
| `startClaudeWatch` | Start monitoring file changes | `{watching}` |
| `stopClaudeWatch` | Stop monitoring, return summary | `{totalChanges, lastChangeTimestamp}` |
| `getClaudeStatus` | Get current activity status | `{fileChanges, lastChangeTimestamp, idleMs}` |

### Sidebar Interaction Flow

```
0. Configure perms:    configureClaudePermissions("acceptEdits") — non-fatal
1. Pre-check:          checkClaudeExtension → fail fast if not installed
2. Open sidebar:       openClaudeCode (validates + activates extension, then opens)
3. New conversation:   newClaudeConversation
4. Paste prompt + submit: sendClaudePrompt (clipboard with trailing `\n` triggers submit)
5. Start monitoring:   startClaudeWatch
6. Wait for completion: 15s grace period, then poll getClaudeStatus until idleMs > 5000
7. Stop monitoring:    stopClaudeWatch → log file changes
8. Review diffs:       if totalChanges > 0: 2-8s pause, then acceptDiff (95%) or rejectDiff (5%)
9. Review files:       Open changed files in editor
```

### Completion Detection

Since we can't introspect the Claude Code extension's internal state, completion is detected via file change quiescence:
- **Grace period:** 15 seconds of idle time before polling begins, allowing Claude to start processing
- **startClaudeWatch** resets counters and starts tracking `onDidChangeTextDocument` and `onDidCreateFiles` events
- **getClaudeStatus** returns `idleMs` — time since last file change
- When `idleMs > 5000` (no changes for 5 seconds), Claude is considered idle
- Maximum wait timeout: `min(estimated_minutes * 60 * 0.8, 300)`
- **Zero-change guard:** If `totalChanges == 0`, diff review is skipped and a warning is logged (Claude may not have started)

### Prompt Submission

Prompts are pasted via the VS Code clipboard API (`sendClaudePrompt`) with a trailing `\n` appended to the clipboard text. The Claude sidebar's input field treats a pasted newline as a submit trigger, so paste and submission happen in a single operation. This avoids both ydotool keycode translation bugs in webviews and the limitation that VS Code's `type` command does not reach webview inputs.

### Permission Configuration

The `configureClaudePermissions` command sets `claudeCode.initialPermissionMode` in VS Code global settings before each sidebar conversation. Default mode is `"acceptEdits"`, which prevents "Ask before edits" prompts from blocking autonomous operation. Valid modes: `default`, `acceptEdits`, `plan`, `bypassPermissions`. Failure is non-fatal (older extension versions may not support this setting).

### Fallback Strategy

Any exception during sidebar commands causes automatic fallback to manual mode (headless Claude Code) for that activity. This ensures Work4Me never breaks when the Claude Code extension isn't installed or behaves unexpectedly.
