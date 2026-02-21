# Work4Me Architecture Revision — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement the revised architecture: dual operating modes (Manual Developer + AI-Assisted Developer), VS Code + custom extension as visible IDE, interleaved per-activity Claude Code execution, browser automation, and full planning module.

**Architecture:** Work4Me orchestrates visible desktop activity across VS Code (custom WebSocket extension), Chromium (Playwright/CDP), and terminal (tmux fallback). Claude Code runs per-activity (not batch). Two modes: Mode A replays headless Claude Code output visibly; Mode B types prompts into visible Claude Code session.

**Tech Stack:** Python 3.11+/asyncio, TypeScript (VS Code extension), websockets (Python), ws (Node.js), Playwright, libtmux, pynvim (fallback)

**Existing Codebase:** ~1700 LOC across 18 Python files. Core modules (state machine, event bus, typing simulation, behavior engine, Claude Code manager, terminal controller, input simulation) are fully implemented. Planning module is empty. No VS Code, browser, mouse, or activity monitor code exists yet.

---

## Task 1: Update Config for New Architecture

**Files:**
- Modify: `work4me/config.py`
- Create: `tests/test_config.py`

**Step 1: Write tests for new config fields**

```python
# tests/test_config.py
from work4me.config import Config, DesktopConfig, ClaudeConfig, BrowserConfig, VSCodeConfig

def test_config_has_mode():
    config = Config()
    assert config.mode in ("manual", "ai-assisted")
    assert config.mode == "manual"  # default

def test_vscode_config_defaults():
    config = VSCodeConfig()
    assert config.websocket_port == 9876
    assert config.extension_dir != ""
    assert config.launch_on_start is True

def test_browser_config_defaults():
    config = BrowserConfig()
    assert config.chromium_path == "chromium"
    assert config.debug_port == 9222
    assert config.enabled is True

def test_claude_config_no_budget_cap():
    config = ClaudeConfig()
    assert config.max_budget_usd == 0.0  # 0 means unlimited (Max plan)

def test_desktop_config_editor_is_vscode():
    config = DesktopConfig()
    assert config.editor == "vscode"
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/sadiq/Desktop/cowork && python -m pytest tests/test_config.py -v`
Expected: FAIL (VSCodeConfig, BrowserConfig don't exist, mode field missing)

**Step 3: Implement config changes**

Add to `work4me/config.py`:

```python
@dataclass
class VSCodeConfig:
    websocket_port: int = 9876
    extension_dir: str = ""  # auto-detect from package
    launch_on_start: bool = True
    executable: str = "code"

@dataclass
class BrowserConfig:
    chromium_path: str = "chromium"
    debug_port: int = 9222
    enabled: bool = True
    ozone_platform: str = "wayland"

# Update existing:
@dataclass
class ClaudeConfig:
    # ... existing fields ...
    max_budget_usd: float = 0.0  # 0 = unlimited (Max plan)

@dataclass
class DesktopConfig:
    # ... existing fields ...
    editor: str = "vscode"  # was "neovim"

@dataclass
class Config:
    # ... existing fields ...
    mode: str = "manual"  # "manual" or "ai-assisted"
    vscode: VSCodeConfig = field(default_factory=VSCodeConfig)
    browser: BrowserConfig = field(default_factory=BrowserConfig)
```

**Step 4: Run tests to verify they pass**

Run: `cd /home/sadiq/Desktop/cowork && python -m pytest tests/test_config.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add work4me/config.py tests/test_config.py
git commit -m "feat(config): add VSCode, browser, and mode config fields"
```

---

## Task 2: Create VS Code Extension (TypeScript)

**Files:**
- Create: `vscode-extension/package.json`
- Create: `vscode-extension/tsconfig.json`
- Create: `vscode-extension/src/extension.ts`

**Step 1: Create package.json**

```json
{
  "name": "work4me-bridge",
  "displayName": "Work4Me Bridge",
  "description": "WebSocket bridge for Work4Me desktop agent",
  "version": "0.1.0",
  "publisher": "work4me",
  "engines": { "vscode": "^1.74.0" },
  "activationEvents": ["onStartupFinished"],
  "main": "./out/extension.js",
  "contributes": {
    "commands": [{
      "command": "work4me.status",
      "title": "Work4Me: Connection Status"
    }]
  },
  "scripts": {
    "vscode:prepublish": "npm run compile",
    "compile": "tsc -p ./",
    "watch": "tsc -watch -p ./"
  },
  "dependencies": {
    "ws": "^8.14.0"
  },
  "devDependencies": {
    "@types/vscode": "^1.74.0",
    "@types/ws": "^8.5.0",
    "@types/node": "^20.0.0",
    "typescript": "^5.0.0"
  }
}
```

**Step 2: Create tsconfig.json**

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "module": "commonjs",
    "lib": ["ES2020"],
    "outDir": "./out",
    "rootDir": "./src",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true
  },
  "include": ["src/**/*"],
  "exclude": ["node_modules"]
}
```

**Step 3: Write extension.ts with full command handler**

```typescript
// vscode-extension/src/extension.ts
import * as vscode from 'vscode';
import { WebSocketServer, WebSocket } from 'ws';

let wss: WebSocketServer | null = null;

interface Command {
  id: string;
  command: string;
  [key: string]: unknown;
}

interface Response {
  id: string;
  success: boolean;
  result?: unknown;
  error?: string;
}

export function activate(context: vscode.ExtensionContext) {
  const port = vscode.workspace.getConfiguration('work4me').get<number>('port', 9876);

  wss = new WebSocketServer({ port });
  console.log(`Work4Me bridge listening on ws://localhost:${port}`);

  wss.on('connection', (ws: WebSocket) => {
    ws.on('message', async (data: Buffer) => {
      let cmd: Command;
      try {
        cmd = JSON.parse(data.toString());
      } catch {
        ws.send(JSON.stringify({ id: '', success: false, error: 'Invalid JSON' }));
        return;
      }
      const response = await handleCommand(cmd);
      ws.send(JSON.stringify(response));
    });
  });

  context.subscriptions.push({ dispose: () => wss?.close() });
}

async function handleCommand(cmd: Command): Promise<Response> {
  try {
    const result = await dispatch(cmd);
    return { id: cmd.id, success: true, result };
  } catch (err: unknown) {
    return { id: cmd.id, success: false, error: String(err) };
  }
}

async function dispatch(cmd: Command): Promise<unknown> {
  switch (cmd.command) {
    case 'openFile': {
      const path = cmd.path as string;
      const line = (cmd.line as number) || 1;
      const doc = await vscode.workspace.openTextDocument(path);
      const editor = await vscode.window.showTextDocument(doc);
      const pos = new vscode.Position(Math.max(0, line - 1), 0);
      editor.selection = new vscode.Selection(pos, pos);
      editor.revealRange(new vscode.Range(pos, pos), vscode.TextEditorRevealType.InCenter);
      return { opened: path, line };
    }

    case 'typeText': {
      const editor = vscode.window.activeTextEditor;
      if (!editor) throw new Error('No active editor');
      const text = cmd.text as string;
      await editor.edit(edit => {
        edit.insert(editor.selection.active, text);
      });
      return { typed: text.length };
    }

    case 'navigateTo': {
      const editor = vscode.window.activeTextEditor;
      if (!editor) throw new Error('No active editor');
      const line = Math.max(0, (cmd.line as number) - 1);
      const col = Math.max(0, (cmd.col as number) || 0);
      const pos = new vscode.Position(line, col);
      editor.selection = new vscode.Selection(pos, pos);
      editor.revealRange(new vscode.Range(pos, pos), vscode.TextEditorRevealType.InCenter);
      return { line: line + 1, col };
    }

    case 'saveFile': {
      const editor = vscode.window.activeTextEditor;
      if (!editor) throw new Error('No active editor');
      await editor.document.save();
      return { saved: editor.document.fileName };
    }

    case 'getActiveFile': {
      const editor = vscode.window.activeTextEditor;
      if (!editor) return { file: null };
      const pos = editor.selection.active;
      return {
        file: editor.document.fileName,
        line: pos.line + 1,
        col: pos.character,
        lineCount: editor.document.lineCount,
        isDirty: editor.document.isDirty,
      };
    }

    case 'getVisibleText': {
      const editor = vscode.window.activeTextEditor;
      if (!editor) throw new Error('No active editor');
      const ranges = editor.visibleRanges;
      const texts = ranges.map(r => editor.document.getText(r));
      return { text: texts.join('\n'), ranges: ranges.map(r => ({ start: r.start.line + 1, end: r.end.line + 1 })) };
    }

    case 'runTerminalCommand': {
      const name = (cmd.name as string) || 'Work4Me';
      let terminal = vscode.window.terminals.find(t => t.name === name);
      if (!terminal) {
        terminal = vscode.window.createTerminal(name);
      }
      terminal.show();
      terminal.sendText(cmd.cmd as string);
      return { sent: cmd.cmd };
    }

    case 'showTerminal': {
      await vscode.commands.executeCommand('workbench.action.terminal.focus');
      return { focused: 'terminal' };
    }

    case 'focusEditor': {
      await vscode.commands.executeCommand('workbench.action.focusActiveEditorGroup');
      return { focused: 'editor' };
    }

    case 'newFile': {
      const path = cmd.path as string;
      const uri = vscode.Uri.file(path);
      const edit = new vscode.WorkspaceEdit();
      edit.createFile(uri, { ignoreIfExists: true });
      await vscode.workspace.applyEdit(edit);
      const doc = await vscode.workspace.openTextDocument(uri);
      await vscode.window.showTextDocument(doc);
      return { created: path };
    }

    case 'replaceFileContent': {
      const editor = vscode.window.activeTextEditor;
      if (!editor) throw new Error('No active editor');
      const fullRange = new vscode.Range(
        new vscode.Position(0, 0),
        editor.document.lineAt(editor.document.lineCount - 1).range.end
      );
      await editor.edit(edit => {
        edit.replace(fullRange, cmd.content as string);
      });
      return { replaced: true };
    }

    case 'ping': {
      return { pong: true, timestamp: Date.now() };
    }

    default:
      throw new Error(`Unknown command: ${cmd.command}`);
  }
}

export function deactivate() {
  if (wss) {
    wss.close();
    wss = null;
  }
}
```

**Step 4: Build the extension**

```bash
cd /home/sadiq/Desktop/cowork/vscode-extension
npm install
npm run compile
```

**Step 5: Verify extension compiles without errors**

Expected: `out/extension.js` created, zero TypeScript errors

**Step 6: Commit**

```bash
git add vscode-extension/
git commit -m "feat: add VS Code WebSocket bridge extension"
```

---

## Task 3: VS Code Python Controller

**Files:**
- Create: `work4me/controllers/vscode.py`
- Create: `tests/test_vscode_controller.py`

**Step 1: Write failing tests**

```python
# tests/test_vscode_controller.py
import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from work4me.controllers.vscode import VSCodeController
from work4me.config import VSCodeConfig

@pytest.fixture
def config():
    return VSCodeConfig(websocket_port=9876)

@pytest.fixture
def controller(config):
    return VSCodeController(config)

def test_controller_init(controller):
    assert controller._ws is None
    assert controller._port == 9876

@pytest.mark.asyncio
async def test_send_command_returns_result(controller):
    mock_ws = AsyncMock()
    mock_ws.recv = AsyncMock(return_value=json.dumps({
        "id": "1", "success": True, "result": {"opened": "test.py"}
    }))
    controller._ws = mock_ws
    controller._msg_id = 0

    result = await controller.send_command("openFile", path="test.py")
    assert result["opened"] == "test.py"
    mock_ws.send.assert_called_once()

@pytest.mark.asyncio
async def test_open_file(controller):
    controller.send_command = AsyncMock(return_value={"opened": "test.py", "line": 1})
    await controller.open_file("test.py", line=1)
    controller.send_command.assert_called_with("openFile", path="test.py", line=1)

@pytest.mark.asyncio
async def test_type_text(controller):
    controller.send_command = AsyncMock(return_value={"typed": 5})
    await controller.type_text("hello")
    controller.send_command.assert_called_with("typeText", text="hello")

@pytest.mark.asyncio
async def test_save_file(controller):
    controller.send_command = AsyncMock(return_value={"saved": "test.py"})
    await controller.save_file()
    controller.send_command.assert_called_with("saveFile")

@pytest.mark.asyncio
async def test_run_terminal_command(controller):
    controller.send_command = AsyncMock(return_value={"sent": "npm test"})
    await controller.run_terminal_command("npm test")
    controller.send_command.assert_called_with("runTerminalCommand", cmd="npm test")

@pytest.mark.asyncio
async def test_health_check_no_connection(controller):
    assert await controller.health_check() is False

@pytest.mark.asyncio
async def test_health_check_with_connection(controller):
    controller.send_command = AsyncMock(return_value={"pong": True})
    controller._ws = MagicMock()
    assert await controller.health_check() is True
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/sadiq/Desktop/cowork && python -m pytest tests/test_vscode_controller.py -v`
Expected: FAIL (module not found)

**Step 3: Implement VSCodeController**

```python
# work4me/controllers/vscode.py
"""VS Code controller via WebSocket bridge extension."""

import asyncio
import json
import logging
from typing import Any

from work4me.config import VSCodeConfig

logger = logging.getLogger(__name__)


class VSCodeController:
    """Controls VS Code via the work4me-bridge WebSocket extension."""

    def __init__(self, config: VSCodeConfig):
        self._port = config.websocket_port
        self._executable = config.executable
        self._extension_dir = config.extension_dir
        self._ws: Any = None  # websockets connection
        self._msg_id = 0
        self._launch_on_start = config.launch_on_start

    async def connect(self, retries: int = 5, delay: float = 2.0) -> None:
        """Connect to the VS Code WebSocket bridge."""
        try:
            import websockets
        except ImportError:
            raise RuntimeError("websockets package required: pip install websockets")

        uri = f"ws://localhost:{self._port}"
        for attempt in range(retries):
            try:
                self._ws = await websockets.connect(uri)
                logger.info("Connected to VS Code bridge at %s", uri)
                return
            except (ConnectionRefusedError, OSError):
                if attempt < retries - 1:
                    logger.debug("VS Code bridge not ready, retry %d/%d", attempt + 1, retries)
                    await asyncio.sleep(delay)
        raise ConnectionError(f"Cannot connect to VS Code bridge at {uri} after {retries} attempts")

    async def launch(self, working_dir: str = ".") -> None:
        """Launch VS Code with the bridge extension loaded."""
        cmd = [self._executable, "--new-window", working_dir]
        if self._extension_dir:
            cmd.extend(["--extensions-dir", self._extension_dir])
        logger.info("Launching VS Code: %s", " ".join(cmd))
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        # Don't wait — VS Code runs independently
        logger.info("VS Code launched (pid=%d)", proc.pid)

    async def send_command(self, command: str, **kwargs: Any) -> dict:
        """Send a command to the VS Code extension and return the result."""
        if self._ws is None:
            raise ConnectionError("Not connected to VS Code bridge")

        self._msg_id += 1
        msg = {"id": str(self._msg_id), "command": command, **kwargs}
        await self._ws.send(json.dumps(msg))
        raw = await self._ws.recv()
        response = json.loads(raw)

        if not response.get("success"):
            raise RuntimeError(f"VS Code command failed: {response.get('error')}")
        return response.get("result", {})

    async def open_file(self, path: str, line: int = 1) -> None:
        """Open a file in the editor at the given line."""
        await self.send_command("openFile", path=path, line=line)

    async def type_text(self, text: str) -> None:
        """Insert text at the current cursor position."""
        await self.send_command("typeText", text=text)

    async def navigate_to(self, line: int, col: int = 0) -> None:
        """Move cursor to line:col."""
        await self.send_command("navigateTo", line=line, col=col)

    async def save_file(self) -> None:
        """Save the active file."""
        await self.send_command("saveFile")

    async def get_active_file(self) -> dict:
        """Get info about the currently active file."""
        return await self.send_command("getActiveFile")

    async def get_visible_text(self) -> str:
        """Get the currently visible text in the editor."""
        result = await self.send_command("getVisibleText")
        return result.get("text", "")

    async def run_terminal_command(self, cmd: str, name: str = "Work4Me") -> None:
        """Run a command in the VS Code integrated terminal."""
        await self.send_command("runTerminalCommand", cmd=cmd, name=name)

    async def show_terminal(self) -> None:
        """Focus the integrated terminal panel."""
        await self.send_command("showTerminal")

    async def focus_editor(self) -> None:
        """Focus the editor panel."""
        await self.send_command("focusEditor")

    async def new_file(self, path: str) -> None:
        """Create and open a new file."""
        await self.send_command("newFile", path=path)

    async def replace_file_content(self, content: str) -> None:
        """Replace the entire content of the active file."""
        await self.send_command("replaceFileContent", content=content)

    async def health_check(self) -> bool:
        """Check if the VS Code bridge is responsive."""
        if self._ws is None:
            return False
        try:
            result = await self.send_command("ping")
            return result.get("pong", False)
        except Exception:
            return False

    async def cleanup(self) -> None:
        """Close the WebSocket connection."""
        if self._ws:
            await self._ws.close()
            self._ws = None
```

**Step 4: Run tests to verify they pass**

Run: `cd /home/sadiq/Desktop/cowork && python -m pytest tests/test_vscode_controller.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add work4me/controllers/vscode.py tests/test_vscode_controller.py
git commit -m "feat: add VS Code WebSocket controller"
```

---

## Task 4: Task Planner

**Files:**
- Create: `work4me/planning/task_planner.py`
- Create: `tests/test_task_planner.py`

**Step 1: Write failing tests**

```python
# tests/test_task_planner.py
import json
import pytest
from unittest.mock import AsyncMock, patch
from work4me.planning.task_planner import TaskPlanner, Activity, ActivityKind, TaskPlan
from work4me.config import ClaudeConfig

@pytest.fixture
def planner():
    return TaskPlanner(ClaudeConfig())

def test_activity_kind_values():
    assert ActivityKind.CODING.value == "CODING"
    assert ActivityKind.BROWSER.value == "BROWSER"
    assert ActivityKind.TERMINAL.value == "TERMINAL"
    assert ActivityKind.READING.value == "READING"
    assert ActivityKind.THINKING.value == "THINKING"

def test_activity_dataclass():
    a = Activity(
        kind=ActivityKind.CODING,
        description="Write auth middleware",
        estimated_minutes=20,
        files_involved=["src/auth.ts"],
        commands=["npm test"],
        search_queries=[],
        dependencies=[],
    )
    assert a.kind == ActivityKind.CODING
    assert a.estimated_minutes == 20

def test_task_plan_total_minutes():
    plan = TaskPlan(
        task_description="Build API",
        activities=[
            Activity(ActivityKind.CODING, "Write code", 30, [], [], [], []),
            Activity(ActivityKind.TERMINAL, "Run tests", 10, [], [], [], []),
        ],
    )
    assert plan.total_estimated_minutes == 40

@pytest.mark.asyncio
async def test_decompose_parses_claude_json(planner):
    fake_json = json.dumps([
        {
            "kind": "CODING",
            "description": "Implement auth",
            "estimated_minutes": 25,
            "files_involved": ["src/auth.ts"],
            "commands": [],
            "search_queries": [],
            "dependencies": [],
        },
        {
            "kind": "TERMINAL",
            "description": "Run tests",
            "estimated_minutes": 10,
            "files_involved": [],
            "commands": ["npm test"],
            "search_queries": [],
            "dependencies": ["0"],
        },
    ])
    mock_result = type("R", (), {"raw_text": fake_json, "exit_code": 0, "error": None, "actions": []})()

    with patch.object(planner._claude, "execute", new_callable=AsyncMock, return_value=mock_result):
        plan = await planner.decompose("Build JWT auth", time_budget_hours=4, working_dir="/tmp")

    assert len(plan.activities) == 2
    assert plan.activities[0].kind == ActivityKind.CODING
    assert plan.activities[1].dependencies == ["0"]
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/sadiq/Desktop/cowork && python -m pytest tests/test_task_planner.py -v`
Expected: FAIL (module not found)

**Step 3: Implement TaskPlanner**

```python
# work4me/planning/task_planner.py
"""Task decomposition via Claude Code."""

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from work4me.config import ClaudeConfig
from work4me.controllers.claude_code import ClaudeCodeManager

logger = logging.getLogger(__name__)


class ActivityKind(Enum):
    CODING = "CODING"
    READING = "READING"
    TERMINAL = "TERMINAL"
    BROWSER = "BROWSER"
    THINKING = "THINKING"


@dataclass
class Activity:
    kind: ActivityKind
    description: str
    estimated_minutes: float
    files_involved: list[str]
    commands: list[str]
    search_queries: list[str]
    dependencies: list[str]


@dataclass
class TaskPlan:
    task_description: str
    activities: list[Activity]

    @property
    def total_estimated_minutes(self) -> float:
        return sum(a.estimated_minutes for a in self.activities)


DECOMPOSITION_PROMPT = """You are a senior software engineer planning a coding task. Decompose the following task into a sequence of developer activities. Each activity should represent a natural unit of work (15-45 minutes).

Task: {task_description}
Time Budget: {hours} hours
Working Directory: {working_dir}

For each activity, specify:
1. kind: one of CODING, READING, TERMINAL, BROWSER, THINKING
2. description: what the developer does
3. estimated_minutes: how long it should take
4. files_involved: which files will be created/modified/read
5. commands: any terminal commands to run
6. search_queries: any web searches needed (for BROWSER activities)
7. dependencies: indices (as strings) of activities that must complete first

Return ONLY a JSON array. No explanation. The total estimated_minutes should equal approximately {target_minutes} (70% of budget — rest is breaks/transitions/thinking)."""


class TaskPlanner:
    """Decomposes a high-level task into structured activities using Claude Code."""

    def __init__(self, config: ClaudeConfig):
        self._claude = ClaudeCodeManager(config)

    async def decompose(
        self,
        task_description: str,
        time_budget_hours: float,
        working_dir: str,
        project_context: str = "",
    ) -> TaskPlan:
        """Ask Claude Code to decompose a task into activities."""
        target_minutes = int(time_budget_hours * 60 * 0.70)
        prompt = DECOMPOSITION_PROMPT.format(
            task_description=task_description,
            hours=time_budget_hours,
            working_dir=working_dir,
            target_minutes=target_minutes,
        )
        if project_context:
            prompt += f"\n\nProject context:\n{project_context}"

        result = await self._claude.execute(
            prompt=prompt,
            working_dir=working_dir,
            max_turns=3,
        )

        if result.error:
            raise RuntimeError(f"Task decomposition failed: {result.error}")

        return self._parse_plan(task_description, result.raw_text)

    def _parse_plan(self, task_description: str, raw_text: str) -> TaskPlan:
        """Parse Claude's JSON response into a TaskPlan."""
        # Extract JSON array from response (may have surrounding text)
        text = raw_text.strip()
        start = text.find("[")
        end = text.rfind("]") + 1
        if start == -1 or end == 0:
            raise ValueError(f"No JSON array found in Claude response: {text[:200]}")

        data = json.loads(text[start:end])
        activities = []
        for item in data:
            kind_str = item.get("kind", "CODING").upper()
            try:
                kind = ActivityKind(kind_str)
            except ValueError:
                logger.warning("Unknown activity kind %r, defaulting to CODING", kind_str)
                kind = ActivityKind.CODING

            activities.append(Activity(
                kind=kind,
                description=item.get("description", ""),
                estimated_minutes=float(item.get("estimated_minutes", 15)),
                files_involved=item.get("files_involved", []),
                commands=item.get("commands", []),
                search_queries=item.get("search_queries", []),
                dependencies=[str(d) for d in item.get("dependencies", [])],
            ))

        logger.info("Decomposed task into %d activities (%.0f min total)",
                     len(activities), sum(a.estimated_minutes for a in activities))
        return TaskPlan(task_description=task_description, activities=activities)
```

**Step 4: Run tests to verify they pass**

Run: `cd /home/sadiq/Desktop/cowork && python -m pytest tests/test_task_planner.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add work4me/planning/task_planner.py tests/test_task_planner.py
git commit -m "feat(planning): add task decomposition via Claude Code"
```

---

## Task 5: Scheduler

**Files:**
- Create: `work4me/planning/scheduler.py`
- Create: `tests/test_scheduler.py`

**Step 1: Write failing tests**

```python
# tests/test_scheduler.py
import pytest
from work4me.planning.scheduler import Scheduler, Schedule, WorkSession
from work4me.planning.task_planner import Activity, ActivityKind, TaskPlan
from work4me.config import SessionConfig

@pytest.fixture
def activities():
    return [
        Activity(ActivityKind.BROWSER, "Research JWT", 10, [], [], ["jwt express middleware"], []),
        Activity(ActivityKind.READING, "Review project", 8, ["src/"], [], [], []),
        Activity(ActivityKind.CODING, "Write auth middleware", 20, ["src/auth.ts"], [], [], ["0", "1"]),
        Activity(ActivityKind.CODING, "Write auth routes", 15, ["src/routes/auth.ts"], [], [], ["2"]),
        Activity(ActivityKind.TERMINAL, "Install deps", 3, [], ["npm install jsonwebtoken"], [], []),
        Activity(ActivityKind.CODING, "Write tests", 15, ["tests/auth.test.ts"], [], [], ["2", "3"]),
        Activity(ActivityKind.TERMINAL, "Run tests", 10, [], ["npm test"], [], ["5"]),
        Activity(ActivityKind.TERMINAL, "Git commit", 3, [], ["git commit"], [], ["6"]),
    ]

@pytest.fixture
def plan(activities):
    return TaskPlan(task_description="Build JWT auth", activities=activities)

@pytest.fixture
def scheduler():
    return Scheduler(SessionConfig())

def test_build_schedule_creates_sessions(scheduler, plan):
    schedule = scheduler.build_schedule(plan, total_minutes=240)
    assert len(schedule.sessions) >= 2
    assert len(schedule.sessions) <= 5

def test_schedule_covers_all_activities(scheduler, plan):
    schedule = scheduler.build_schedule(plan, total_minutes=240)
    all_activities = []
    for session in schedule.sessions:
        all_activities.extend(session.activities)
    assert len(all_activities) == len(plan.activities)

def test_sessions_have_breaks(scheduler, plan):
    schedule = scheduler.build_schedule(plan, total_minutes=240)
    for session in schedule.sessions[:-1]:  # all but last
        assert session.break_after_minutes > 0

def test_schedule_respects_dependencies(scheduler, plan):
    schedule = scheduler.build_schedule(plan, total_minutes=240)
    seen_indices: set[int] = set()
    for session in schedule.sessions:
        for activity in session.activities:
            idx = plan.activities.index(activity)
            for dep in activity.dependencies:
                assert int(dep) in seen_indices, f"Activity {idx} depends on {dep} which hasn't been scheduled yet"
            seen_indices.add(idx)

def test_total_time_within_budget(scheduler, plan):
    schedule = scheduler.build_schedule(plan, total_minutes=240)
    total = sum(s.duration_minutes + s.break_after_minutes for s in schedule.sessions)
    assert total <= 260  # some slack for noise
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/sadiq/Desktop/cowork && python -m pytest tests/test_scheduler.py -v`
Expected: FAIL

**Step 3: Implement Scheduler**

```python
# work4me/planning/scheduler.py
"""Session scheduling with human-like time distribution."""

import logging
import random
from dataclasses import dataclass, field

from work4me.config import SessionConfig
from work4me.planning.task_planner import Activity, TaskPlan

logger = logging.getLogger(__name__)


@dataclass
class WorkSession:
    activities: list[Activity]
    duration_minutes: float
    break_after_minutes: float
    session_number: int


@dataclass
class Schedule:
    sessions: list[WorkSession]
    total_budget_minutes: float


# Session templates: (mean_duration, sigma, min, max)
SESSION_TEMPLATES = [
    (52, 5, 35, 75),
    (45, 5, 30, 60),
    (48, 5, 35, 65),
    (38, 5, 25, 50),
]

# Break templates: (mean, sigma, min, max)
BREAK_TEMPLATES = [
    (6.5, 1.5, 3, 12),
    (5.0, 1.5, 3, 8),
    (12.0, 2.0, 8, 18),
    (0, 0, 0, 0),  # no break after last session
]


class Scheduler:
    """Maps activities onto work sessions with breaks."""

    def __init__(self, config: SessionConfig):
        self._config = config
        self._rng = random.Random()

    def build_schedule(self, plan: TaskPlan, total_minutes: float) -> Schedule:
        """Create a schedule of work sessions from a task plan."""
        # Generate session durations with noise
        session_durations = self._generate_session_durations(total_minutes)
        num_sessions = len(session_durations)

        # Topological sort respecting dependencies
        ordered = self._topological_sort(plan.activities)

        # Distribute activities across sessions
        sessions: list[WorkSession] = []
        activity_idx = 0

        for i, (dur, brk) in enumerate(session_durations):
            session_activities: list[Activity] = []
            session_time = 0.0

            while activity_idx < len(ordered) and session_time + ordered[activity_idx].estimated_minutes <= dur * 1.2:
                session_activities.append(ordered[activity_idx])
                session_time += ordered[activity_idx].estimated_minutes
                activity_idx += 1

            # If last session, grab remaining
            if i == num_sessions - 1:
                while activity_idx < len(ordered):
                    session_activities.append(ordered[activity_idx])
                    session_time += ordered[activity_idx].estimated_minutes
                    activity_idx += 1

            sessions.append(WorkSession(
                activities=session_activities,
                duration_minutes=max(dur, session_time),
                break_after_minutes=brk,
                session_number=i + 1,
            ))

        logger.info("Scheduled %d activities across %d sessions (%.0f min total)",
                     len(plan.activities), len(sessions), total_minutes)
        return Schedule(sessions=sessions, total_budget_minutes=total_minutes)

    def _generate_session_durations(self, total_minutes: float) -> list[tuple[float, float]]:
        """Generate session durations with Gaussian noise, scaled to budget."""
        scale = total_minutes / 240.0  # templates designed for 4 hours
        results = []
        for (mean, sigma, lo, hi), (bmean, bsigma, blo, bhi) in zip(SESSION_TEMPLATES, BREAK_TEMPLATES):
            dur = max(lo, min(hi, self._rng.gauss(mean, sigma))) * scale
            brk = max(blo, min(bhi, self._rng.gauss(bmean, bsigma))) * scale if bmean > 0 else 0
            results.append((dur, brk))
        return results

    def _topological_sort(self, activities: list[Activity]) -> list[Activity]:
        """Sort activities respecting dependencies."""
        n = len(activities)
        visited = [False] * n
        result: list[Activity] = []

        def visit(i: int) -> None:
            if visited[i]:
                return
            visited[i] = True
            for dep_str in activities[i].dependencies:
                dep = int(dep_str)
                if 0 <= dep < n:
                    visit(dep)
            result.append(activities[i])

        for i in range(n):
            visit(i)
        return result
```

**Step 4: Run tests to verify they pass**

Run: `cd /home/sadiq/Desktop/cowork && python -m pytest tests/test_scheduler.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add work4me/planning/scheduler.py tests/test_scheduler.py
git commit -m "feat(planning): add session scheduler with Gaussian noise"
```

---

## Task 6: Browser Controller

**Files:**
- Create: `work4me/controllers/browser.py`
- Create: `tests/test_browser_controller.py`

**Step 1: Write failing tests**

```python
# tests/test_browser_controller.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from work4me.controllers.browser import BrowserController
from work4me.config import BrowserConfig

@pytest.fixture
def config():
    return BrowserConfig()

@pytest.fixture
def controller(config):
    return BrowserController(config)

def test_controller_init(controller):
    assert controller._browser is None
    assert controller._page is None

@pytest.mark.asyncio
async def test_navigate_calls_goto(controller):
    mock_page = AsyncMock()
    controller._page = mock_page
    await controller.navigate("https://example.com")
    mock_page.goto.assert_called_with("https://example.com", wait_until="domcontentloaded")

@pytest.mark.asyncio
async def test_search_types_query(controller):
    mock_page = AsyncMock()
    mock_page.url = "https://www.google.com"
    controller._page = mock_page
    controller.navigate = AsyncMock()
    await controller.search("jwt middleware express")
    controller.navigate.assert_called()

@pytest.mark.asyncio
async def test_scroll_down(controller):
    mock_page = AsyncMock()
    controller._page = mock_page
    await controller.scroll_down(pixels=300)
    mock_page.mouse.wheel.assert_called()

@pytest.mark.asyncio
async def test_get_page_text(controller):
    mock_page = AsyncMock()
    mock_page.inner_text = AsyncMock(return_value="Hello world content")
    controller._page = mock_page
    text = await controller.get_page_text()
    assert "Hello" in text

@pytest.mark.asyncio
async def test_health_check_no_browser(controller):
    assert await controller.health_check() is False
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/sadiq/Desktop/cowork && python -m pytest tests/test_browser_controller.py -v`
Expected: FAIL

**Step 3: Implement BrowserController**

```python
# work4me/controllers/browser.py
"""Browser automation via Chromium CDP/Playwright."""

import asyncio
import logging
import random
from typing import Any, Optional

from work4me.config import BrowserConfig

logger = logging.getLogger(__name__)


class BrowserController:
    """Controls a visible Chromium browser via Playwright/CDP."""

    def __init__(self, config: BrowserConfig):
        self._config = config
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None
        self._process: Optional[asyncio.subprocess.Process] = None

    async def launch(self) -> None:
        """Launch Chromium with remote debugging and connect via Playwright."""
        # Launch Chromium
        cmd = [
            self._config.chromium_path,
            f"--remote-debugging-port={self._config.debug_port}",
            f"--ozone-platform={self._config.ozone_platform}",
            "--no-first-run",
            "--no-default-browser-check",
        ]
        self._process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        logger.info("Chromium launched (pid=%d) on port %d", self._process.pid, self._config.debug_port)
        await asyncio.sleep(2)  # wait for browser to start

        # Connect via Playwright
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise RuntimeError("playwright required: pip install playwright && playwright install chromium")

        self._playwright = await async_playwright().__aenter__()
        self._browser = await self._playwright.chromium.connect_over_cdp(
            f"http://localhost:{self._config.debug_port}"
        )
        self._context = self._browser.contexts[0]
        self._page = self._context.pages[0] if self._context.pages else await self._context.new_page()
        logger.info("Connected to Chromium via CDP")

    async def navigate(self, url: str) -> None:
        """Navigate to a URL."""
        if not self._page:
            raise RuntimeError("Browser not launched")
        await self._page.goto(url, wait_until="domcontentloaded")
        logger.debug("Navigated to %s", url)

    async def search(self, query: str, engine: str = "google") -> None:
        """Perform a web search."""
        if engine == "google":
            await self.navigate(f"https://www.google.com/search?q={query.replace(' ', '+')}")
        elif engine == "stackoverflow":
            await self.navigate(f"https://stackoverflow.com/search?q={query.replace(' ', '+')}")
        else:
            await self.navigate(f"https://www.google.com/search?q={query.replace(' ', '+')}")

    async def type_in_search(self, selector: str, query: str, delay_ms: int = 85) -> None:
        """Type a search query character by character with human-like delay."""
        if not self._page:
            raise RuntimeError("Browser not launched")
        await self._page.click(selector)
        await self._page.type(selector, query, delay=delay_ms)

    async def scroll_down(self, pixels: int = 300) -> None:
        """Scroll down with natural variation."""
        if not self._page:
            raise RuntimeError("Browser not launched")
        steps = max(1, pixels // 100)
        for _ in range(steps):
            delta = random.randint(80, 150)
            await self._page.mouse.wheel(0, delta)
            await asyncio.sleep(random.uniform(0.2, 0.5))

    async def get_page_text(self) -> str:
        """Get the visible text content of the page."""
        if not self._page:
            raise RuntimeError("Browser not launched")
        return await self._page.inner_text("body")

    async def new_tab(self, url: str = "about:blank") -> None:
        """Open a new tab."""
        if not self._context:
            raise RuntimeError("Browser not launched")
        self._page = await self._context.new_page()
        if url != "about:blank":
            await self.navigate(url)

    async def close_tab(self) -> None:
        """Close the current tab and switch to the previous one."""
        if self._page:
            await self._page.close()
        pages = self._context.pages if self._context else []
        self._page = pages[-1] if pages else None

    async def health_check(self) -> bool:
        """Check if the browser is responsive."""
        if not self._page:
            return False
        try:
            await self._page.evaluate("1 + 1")
            return True
        except Exception:
            return False

    async def cleanup(self) -> None:
        """Disconnect from browser (don't close it)."""
        if self._browser:
            await self._browser.disconnect()  # NOT close — keeps browser visible
            self._browser = None
        if hasattr(self, '_playwright') and self._playwright:
            await self._playwright.__aexit__(None, None, None)
        if self._process:
            self._process.terminate()
            self._process = None
```

**Step 4: Run tests to verify they pass**

Run: `cd /home/sadiq/Desktop/cowork && python -m pytest tests/test_browser_controller.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add work4me/controllers/browser.py tests/test_browser_controller.py
git commit -m "feat: add browser controller via Playwright/CDP"
```

---

## Task 7: Activity Monitor

**Files:**
- Create: `work4me/behavior/activity_monitor.py`
- Create: `tests/test_activity_monitor.py`

**Step 1: Write failing tests**

```python
# tests/test_activity_monitor.py
import time
import pytest
from work4me.behavior.activity_monitor import ActivityMonitor, ActivityHealth, BehaviorAdjustment
from work4me.config import ActivityConfig

@pytest.fixture
def monitor():
    return ActivityMonitor(ActivityConfig())

def test_empty_monitor_ratio_is_zero(monitor):
    assert monitor.activity_ratio() == 0.0

def test_record_events_increases_ratio(monitor):
    now = time.time()
    for i in range(30):
        monitor.record_event("keyboard", now - 600 + i * 10)
    ratio = monitor.activity_ratio(window_seconds=600)
    assert 0.0 < ratio < 1.0

def test_variance_requires_data(monitor):
    assert monitor.variance() == 0.0

def test_is_within_bounds_empty(monitor):
    health = monitor.is_within_bounds()
    assert health.activity_ok  # no activity is "ok" (not flagged as too high)
    assert health.variance_ok

def test_keyboard_mouse_balance(monitor):
    now = time.time()
    for i in range(50):
        monitor.record_event("keyboard", now - 3000 + i * 30)
    # All keyboard, no mouse
    kb, mouse = monitor.keyboard_mouse_balance()
    assert kb > 0.9
    assert mouse < 0.1

def test_recommended_adjustment_too_high(monitor):
    now = time.time()
    # Simulate very high activity
    for i in range(580):
        monitor.record_event("keyboard", now - 600 + i)
    adj = monitor.recommended_adjustment()
    assert adj == BehaviorAdjustment.SLOW_DOWN

def test_recommended_adjustment_too_low(monitor):
    now = time.time()
    # Simulate very low activity
    for i in range(5):
        monitor.record_event("keyboard", now - 600 + i * 100)
    adj = monitor.recommended_adjustment()
    assert adj == BehaviorAdjustment.SPEED_UP
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/sadiq/Desktop/cowork && python -m pytest tests/test_activity_monitor.py -v`
Expected: FAIL

**Step 3: Implement ActivityMonitor**

```python
# work4me/behavior/activity_monitor.py
"""Activity monitoring and anti-detection constraint enforcement."""

import logging
import time
from dataclasses import dataclass
from enum import Enum

from work4me.config import ActivityConfig

logger = logging.getLogger(__name__)


class BehaviorAdjustment(Enum):
    NONE = "none"
    SLOW_DOWN = "slow_down"
    SPEED_UP = "speed_up"
    ADD_IDLE = "add_idle"
    ADD_MOUSE = "add_mouse"
    ADD_VARIATION = "add_variation"


@dataclass
class ActivityHealth:
    activity_ok: bool
    variance_ok: bool
    balance_ok: bool
    details: str = ""


class ActivityMonitor:
    """Tracks activity statistics and enforces human-plausible bounds."""

    def __init__(self, config: ActivityConfig):
        self._config = config
        self._events: list[tuple[str, float]] = []  # (kind, timestamp)
        self._max_history = 7200  # 2 hours

    def record_event(self, kind: str, timestamp: float | None = None) -> None:
        """Record an input event (keyboard or mouse)."""
        ts = timestamp or time.time()
        self._events.append((kind, ts))
        self._prune()

    def _prune(self) -> None:
        """Remove events older than max history."""
        cutoff = time.time() - self._max_history
        self._events = [(k, t) for k, t in self._events if t >= cutoff]

    def activity_ratio(self, window_seconds: int = 600) -> float:
        """Active seconds / window seconds. Target: 0.40-0.70."""
        now = time.time()
        cutoff = now - window_seconds
        active_seconds = set()
        for _, ts in self._events:
            if ts >= cutoff:
                active_seconds.add(int(ts))
        if window_seconds == 0:
            return 0.0
        return len(active_seconds) / window_seconds

    def variance(self, window_seconds: int = 5400) -> float:
        """Activity ratio variance over the window. Must be >0.04."""
        now = time.time()
        # Split into 10-min sub-windows
        sub_window = 600
        ratios = []
        for i in range(0, window_seconds, sub_window):
            start = now - window_seconds + i
            end = start + sub_window
            active = set()
            for _, ts in self._events:
                if start <= ts < end:
                    active.add(int(ts))
            ratios.append(len(active) / sub_window)

        if len(ratios) < 2:
            return 0.0
        mean = sum(ratios) / len(ratios)
        return sum((r - mean) ** 2 for r in ratios) / len(ratios)

    def keyboard_mouse_balance(self, window_seconds: int = 3000) -> tuple[float, float]:
        """(keyboard_ratio, mouse_ratio) of events in window."""
        now = time.time()
        cutoff = now - window_seconds
        kb = sum(1 for k, t in self._events if t >= cutoff and k == "keyboard")
        mouse = sum(1 for k, t in self._events if t >= cutoff and k == "mouse")
        total = kb + mouse
        if total == 0:
            return (0.0, 0.0)
        return (kb / total, mouse / total)

    def is_within_bounds(self) -> ActivityHealth:
        """Check all anti-detection constraints."""
        ratio = self.activity_ratio()
        var = self.variance()
        kb, mouse = self.keyboard_mouse_balance()

        activity_ok = ratio <= 0.85 or len(self._events) == 0
        variance_ok = var >= 0.04 or len(self._events) < 60
        balance_ok = not (kb > 0.95 and mouse < 0.05 and len(self._events) > 100)

        details = f"ratio={ratio:.2f} var={var:.4f} kb={kb:.2f} mouse={mouse:.2f}"
        return ActivityHealth(
            activity_ok=activity_ok,
            variance_ok=variance_ok,
            balance_ok=balance_ok,
            details=details,
        )

    def recommended_adjustment(self) -> BehaviorAdjustment:
        """Suggest behavior adjustment based on current metrics."""
        ratio = self.activity_ratio()
        var = self.variance()
        kb, mouse = self.keyboard_mouse_balance()

        if ratio > 0.80:
            return BehaviorAdjustment.SLOW_DOWN
        if ratio < 0.30 and len(self._events) > 10:
            return BehaviorAdjustment.SPEED_UP
        if var < 0.04 and len(self._events) > 60:
            return BehaviorAdjustment.ADD_VARIATION
        if kb > 0.90 and mouse < 0.10 and len(self._events) > 100:
            return BehaviorAdjustment.ADD_MOUSE
        return BehaviorAdjustment.NONE
```

**Step 4: Run tests to verify they pass**

Run: `cd /home/sadiq/Desktop/cowork && python -m pytest tests/test_activity_monitor.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add work4me/behavior/activity_monitor.py tests/test_activity_monitor.py
git commit -m "feat(behavior): add activity monitor with anti-detection constraints"
```

---

## Task 8: Mouse Simulation

**Files:**
- Create: `work4me/behavior/mouse.py`
- Create: `tests/test_mouse.py`

**Step 1: Write failing tests**

```python
# tests/test_mouse.py
import math
import pytest
from work4me.behavior.mouse import HumanMouse, Point

def test_point_distance():
    a = Point(0, 0)
    b = Point(3, 4)
    assert abs(a.distance_to(b) - 5.0) < 0.001

def test_bezier_path_has_endpoints():
    mouse = HumanMouse()
    start = Point(0, 0)
    end = Point(100, 200)
    path = mouse.bezier_path(start, end)
    assert len(path) >= 2
    assert abs(path[0].x - start.x) < 1
    assert abs(path[0].y - start.y) < 1
    assert abs(path[-1].x - end.x) < 5  # allow overshoot correction
    assert abs(path[-1].y - end.y) < 5

def test_bezier_path_length_scales_with_distance():
    mouse = HumanMouse()
    short_path = mouse.bezier_path(Point(0, 0), Point(10, 10))
    long_path = mouse.bezier_path(Point(0, 0), Point(1000, 1000))
    assert len(long_path) > len(short_path)

def test_fitts_duration_positive():
    mouse = HumanMouse()
    dur = mouse.fitts_duration(distance=500, target_width=50)
    assert dur > 0

def test_fitts_duration_larger_for_small_targets():
    mouse = HumanMouse()
    dur_small = mouse.fitts_duration(distance=500, target_width=10)
    dur_large = mouse.fitts_duration(distance=500, target_width=100)
    assert dur_small > dur_large

def test_micro_movement_small():
    mouse = HumanMouse()
    p = mouse.micro_movement(Point(500, 500))
    assert abs(p.x - 500) < 20
    assert abs(p.y - 500) < 20
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/sadiq/Desktop/cowork && python -m pytest tests/test_mouse.py -v`
Expected: FAIL

**Step 3: Implement HumanMouse**

```python
# work4me/behavior/mouse.py
"""Human-like mouse movement simulation using Bezier curves and Fitts's law."""

import math
import random
from dataclasses import dataclass


@dataclass
class Point:
    x: float
    y: float

    def distance_to(self, other: "Point") -> float:
        return math.sqrt((self.x - other.x) ** 2 + (self.y - other.y) ** 2)


class HumanMouse:
    """Generate human-like mouse movement paths."""

    def __init__(self, overshoot_probability: float = 0.15):
        self._rng = random.Random()
        self._overshoot_prob = overshoot_probability

    def bezier_path(self, start: Point, end: Point, steps_per_100px: int = 8) -> list[Point]:
        """Generate a cubic Bezier curve path from start to end."""
        dist = start.distance_to(end)
        if dist < 1:
            return [start, end]

        # Generate 2 control points offset perpendicular to straight line
        ctrl_points = self._generate_control_points(start, end, dist)

        # Number of steps proportional to distance
        num_steps = max(5, int(dist / 100 * steps_per_100px))
        path = []
        for i in range(num_steps + 1):
            t = i / num_steps
            p = self._cubic_bezier(t, start, ctrl_points[0], ctrl_points[1], end)
            path.append(p)

        # Add overshoot
        if self._rng.random() < self._overshoot_prob and dist > 50:
            overshoot_dist = self._rng.uniform(5, min(20, dist * 0.05))
            dx = end.x - start.x
            dy = end.y - start.y
            norm = math.sqrt(dx * dx + dy * dy) or 1
            overshoot = Point(end.x + dx / norm * overshoot_dist, end.y + dy / norm * overshoot_dist)
            path.append(overshoot)
            # Micro-corrections back to target
            for _ in range(self._rng.randint(1, 3)):
                correction = Point(
                    end.x + self._rng.gauss(0, 2),
                    end.y + self._rng.gauss(0, 2),
                )
                path.append(correction)

        return path

    def fitts_duration(self, distance: float, target_width: float) -> float:
        """Fitts's law: T = a + b * log2(D/W + 1). Returns seconds."""
        a = 0.05  # base reaction time
        b = 0.15  # movement time coefficient
        if target_width <= 0:
            target_width = 1
        return a + b * math.log2(distance / target_width + 1)

    def micro_movement(self, current: Point, max_delta: int = 15) -> Point:
        """Small idle mouse movement (anti-idle)."""
        dx = self._rng.gauss(0, max_delta / 3)
        dy = self._rng.gauss(0, max_delta / 3)
        return Point(current.x + dx, current.y + dy)

    def _generate_control_points(self, start: Point, end: Point, dist: float) -> list[Point]:
        """Generate 2 control points for cubic Bezier."""
        mid_x = (start.x + end.x) / 2
        mid_y = (start.y + end.y) / 2
        # Perpendicular offset
        dx = end.x - start.x
        dy = end.y - start.y
        norm = math.sqrt(dx * dx + dy * dy) or 1
        perp_x = -dy / norm
        perp_y = dx / norm

        offset_scale = dist * 0.2  # 20% of distance
        cp1 = Point(
            start.x + dx * 0.3 + perp_x * self._rng.gauss(0, offset_scale),
            start.y + dy * 0.3 + perp_y * self._rng.gauss(0, offset_scale),
        )
        cp2 = Point(
            start.x + dx * 0.7 + perp_x * self._rng.gauss(0, offset_scale),
            start.y + dy * 0.7 + perp_y * self._rng.gauss(0, offset_scale),
        )
        return [cp1, cp2]

    def _cubic_bezier(self, t: float, p0: Point, p1: Point, p2: Point, p3: Point) -> Point:
        """Evaluate cubic Bezier curve at parameter t."""
        u = 1 - t
        x = u**3 * p0.x + 3 * u**2 * t * p1.x + 3 * u * t**2 * p2.x + t**3 * p3.x
        y = u**3 * p0.y + 3 * u**2 * t * p1.y + 3 * u * t**2 * p2.y + t**3 * p3.y
        return Point(x, y)
```

**Step 4: Run tests to verify they pass**

Run: `cd /home/sadiq/Desktop/cowork && python -m pytest tests/test_mouse.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add work4me/behavior/mouse.py tests/test_mouse.py
git commit -m "feat(behavior): add Bezier curve mouse simulation with Fitts's law"
```

---

## Task 9: Revise Orchestrator for Dual-Mode Interleaved Execution

This is the largest task — the orchestrator must be substantially rewritten to support:
- Interleaved per-activity Claude Code execution (not batch)
- Mode A (Manual Developer): replay Claude output in VS Code
- Mode B (AI-Assisted Developer): type prompts into visible Claude Code session
- VS Code integration (replacing Neovim as primary)
- Browser activity during BROWSER phases
- Activity monitor integration

**Files:**
- Modify: `work4me/core/orchestrator.py` (539 lines → rewrite)
- Create: `tests/test_orchestrator.py`

**Step 1: Write failing tests for the new orchestrator interface**

```python
# tests/test_orchestrator.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from work4me.core.orchestrator import Orchestrator
from work4me.config import Config
from work4me.planning.task_planner import Activity, ActivityKind, TaskPlan
from work4me.planning.scheduler import Schedule, WorkSession

@pytest.fixture
def config():
    return Config()

@pytest.fixture
def orchestrator(config):
    return Orchestrator(config)

def test_orchestrator_has_mode(orchestrator):
    assert orchestrator._mode in ("manual", "ai-assisted")

def test_orchestrator_has_vscode_controller(orchestrator):
    from work4me.controllers.vscode import VSCodeController
    assert isinstance(orchestrator._vscode, VSCodeController)

def test_orchestrator_has_browser_controller(orchestrator):
    from work4me.controllers.browser import BrowserController
    assert isinstance(orchestrator._browser, BrowserController)

def test_orchestrator_has_activity_monitor(orchestrator):
    from work4me.behavior.activity_monitor import ActivityMonitor
    assert isinstance(orchestrator._activity_monitor, ActivityMonitor)

def test_orchestrator_has_planner(orchestrator):
    from work4me.planning.task_planner import TaskPlanner
    assert isinstance(orchestrator._planner, TaskPlanner)

@pytest.mark.asyncio
async def test_execute_activity_coding_mode_a(orchestrator):
    activity = Activity(
        ActivityKind.CODING, "Write auth", 20,
        ["src/auth.ts"], [], [], [],
    )
    orchestrator._mode = "manual"
    orchestrator._claude = AsyncMock()
    orchestrator._claude.execute = AsyncMock(return_value=MagicMock(
        actions=[], raw_text="done", exit_code=0, error=None
    ))
    orchestrator._vscode = AsyncMock()
    orchestrator._behavior = AsyncMock()
    orchestrator._activity_monitor = MagicMock()
    orchestrator._activity_monitor.recommended_adjustment = MagicMock(return_value=MagicMock(value="none"))

    await orchestrator._execute_activity(activity, working_dir="/tmp")
    orchestrator._claude.execute.assert_called_once()

@pytest.mark.asyncio
async def test_execute_activity_browser(orchestrator):
    activity = Activity(
        ActivityKind.BROWSER, "Research JWT", 10,
        [], [], ["jwt express middleware"], [],
    )
    orchestrator._browser_ctrl = AsyncMock()
    orchestrator._behavior = AsyncMock()
    orchestrator._activity_monitor = MagicMock()
    orchestrator._activity_monitor.recommended_adjustment = MagicMock(return_value=MagicMock(value="none"))

    await orchestrator._execute_activity(activity, working_dir="/tmp")
    orchestrator._browser_ctrl.search.assert_called()
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/sadiq/Desktop/cowork && python -m pytest tests/test_orchestrator.py -v`
Expected: FAIL (old orchestrator doesn't have new attributes)

**Step 3: Rewrite orchestrator**

The new orchestrator.py replaces the existing file entirely. Key changes:
- Constructor creates VSCodeController, BrowserController, TaskPlanner, Scheduler, ActivityMonitor
- `run()` follows: INITIALIZING → PLANNING → per-activity WORKING loop → WRAPPING_UP → COMPLETED
- `_execute_activity()` dispatches based on activity kind and mode
- Mode A: `_execute_coding_manual()` — runs Claude headless, replays in VS Code
- Mode B: `_execute_coding_ai_assisted()` — types prompts into visible Claude session
- `_execute_browser()` — opens browser, navigates, scrolls, reads
- `_execute_terminal()` — runs commands in VS Code terminal
- Activity monitor checked between activities, adjusts pacing

This file is ~400-500 lines. The full implementation replaces `work4me/core/orchestrator.py`. Due to length, the exact code should be written during execution using the patterns from the existing orchestrator (state transitions, event emission, error handling) combined with the new controllers.

**Key method signatures:**

```python
class Orchestrator:
    def __init__(self, config: Config): ...

    async def run(self, task_description: str, time_budget_minutes: int, working_dir: str = ".") -> None:
        """Main entry point."""

    async def _initialize(self, working_dir: str) -> None:
        """Launch VS Code, browser, connect controllers."""

    async def _plan(self, task_description: str, time_budget_minutes: int, working_dir: str) -> Schedule:
        """Decompose task and build schedule."""

    async def _execute_session(self, session: WorkSession, working_dir: str) -> None:
        """Execute all activities in a work session."""

    async def _execute_activity(self, activity: Activity, working_dir: str) -> None:
        """Dispatch activity based on kind and mode."""

    async def _execute_coding_manual(self, activity: Activity, working_dir: str) -> None:
        """Mode A: headless Claude → replay in VS Code."""

    async def _execute_coding_ai_assisted(self, activity: Activity, working_dir: str) -> None:
        """Mode B: type prompts into visible Claude Code."""

    async def _execute_browser(self, activity: Activity) -> None:
        """Browse URLs from activity.search_queries."""

    async def _execute_terminal(self, activity: Activity, working_dir: str) -> None:
        """Run commands in VS Code terminal."""

    async def _execute_reading(self, activity: Activity) -> None:
        """Open and scroll through files in VS Code."""

    async def _replay_edit_in_vscode(self, action: CapturedAction) -> None:
        """Type code into VS Code for new files, reload for edits."""

    async def _take_break(self, duration_minutes: float) -> None:
        """Simulate break with minimal activity."""

    async def _wrap_up(self, working_dir: str) -> None:
        """Git commit, final cleanup."""

    async def _check_activity_health(self) -> None:
        """Consult ActivityMonitor and adjust behavior if needed."""

    async def _cleanup(self) -> None:
        """Close all connections."""
```

**Step 4: Run tests to verify they pass**

Run: `cd /home/sadiq/Desktop/cowork && python -m pytest tests/test_orchestrator.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add work4me/core/orchestrator.py tests/test_orchestrator.py
git commit -m "feat(core): rewrite orchestrator for dual-mode interleaved execution"
```

---

## Task 10: Update CLI for Mode Selection and New Dependencies

**Files:**
- Modify: `work4me/cli.py`
- Modify: `work4me/pyproject.toml`
- Create: `tests/test_cli.py`

**Step 1: Write failing tests**

```python
# tests/test_cli.py
import pytest
from work4me.cli import build_parser

def test_start_accepts_mode_flag():
    parser = build_parser()
    args = parser.parse_args(["start", "--task", "Build API", "--hours", "4", "--mode", "ai-assisted"])
    assert args.mode == "ai-assisted"

def test_start_default_mode_is_manual():
    parser = build_parser()
    args = parser.parse_args(["start", "--task", "Build API", "--hours", "4"])
    assert args.mode == "manual"

def test_start_accepts_working_dir():
    parser = build_parser()
    args = parser.parse_args(["start", "--task", "Build API", "--hours", "4", "--dir", "/tmp/project"])
    assert args.dir == "/tmp/project"
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/sadiq/Desktop/cowork && python -m pytest tests/test_cli.py -v`
Expected: FAIL (mode flag doesn't exist yet)

**Step 3: Update CLI**

Add to the `start` subparser in `build_parser()`:
- `--mode` flag with choices `["manual", "ai-assisted"]`, default `"manual"`
- `--dir` flag for working directory, default `"."`

Update `cmd_start()` to pass mode and working_dir to Orchestrator.

**Step 4: Update pyproject.toml dependencies**

```toml
dependencies = [
    "libtmux>=0.37",
    "pynvim>=0.5",
    "numpy>=1.26",
    "websockets>=12.0",
    "playwright>=1.40",
]
```

**Step 5: Run tests to verify they pass**

Run: `cd /home/sadiq/Desktop/cowork && python -m pytest tests/test_cli.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add work4me/cli.py pyproject.toml tests/test_cli.py
git commit -m "feat(cli): add --mode and --dir flags, update dependencies"
```

---

## Task 11: Integration Smoke Test

**Files:**
- Create: `tests/test_integration.py`

This test verifies the complete flow using mocked external services (Claude Code, VS Code, Chromium). It ensures all modules wire together correctly.

**Step 1: Write integration test**

```python
# tests/test_integration.py
"""Integration test: verify full orchestration flow with mocked externals."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from work4me.config import Config
from work4me.core.orchestrator import Orchestrator
from work4me.planning.task_planner import Activity, ActivityKind, TaskPlan
from work4me.planning.scheduler import Schedule, WorkSession

@pytest.fixture
def mock_schedule():
    activities = [
        Activity(ActivityKind.BROWSER, "Research", 5, [], [], ["test query"], []),
        Activity(ActivityKind.CODING, "Write code", 10, ["test.py"], [], [], ["0"]),
        Activity(ActivityKind.TERMINAL, "Run tests", 3, [], ["pytest"], [], ["1"]),
    ]
    session = WorkSession(
        activities=activities,
        duration_minutes=20,
        break_after_minutes=0,
        session_number=1,
    )
    return Schedule(sessions=[session], total_budget_minutes=30)

@pytest.mark.asyncio
async def test_full_flow_mode_a(mock_schedule):
    config = Config(mode="manual")
    orch = Orchestrator(config)

    # Mock all external controllers
    orch._vscode = AsyncMock()
    orch._browser_ctrl = AsyncMock()
    orch._terminal = AsyncMock()
    orch._behavior = AsyncMock()
    orch._claude = AsyncMock()
    orch._claude.execute = AsyncMock(return_value=MagicMock(
        actions=[], raw_text="done", exit_code=0, error=None, session_id="test"
    ))
    orch._planner = AsyncMock()
    orch._planner.decompose = AsyncMock(return_value=TaskPlan(
        "Test task", mock_schedule.sessions[0].activities
    ))
    orch._scheduler = MagicMock()
    orch._scheduler.build_schedule = MagicMock(return_value=mock_schedule)
    orch._activity_monitor = MagicMock()
    orch._activity_monitor.recommended_adjustment = MagicMock(return_value=MagicMock(value="none"))
    orch._activity_monitor.is_within_bounds = MagicMock(return_value=MagicMock(
        activity_ok=True, variance_ok=True, balance_ok=True
    ))

    # Mock initialization
    orch._initialize = AsyncMock()
    orch._wrap_up = AsyncMock()
    orch._cleanup = AsyncMock()

    await orch.run("Test task", time_budget_minutes=30, working_dir="/tmp")

    orch._initialize.assert_called_once()
    orch._planner.decompose.assert_called_once()
    orch._wrap_up.assert_called_once()
    orch._cleanup.assert_called_once()
```

**Step 2: Run integration test**

Run: `cd /home/sadiq/Desktop/cowork && python -m pytest tests/test_integration.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: add integration smoke test for full orchestration flow"
```

---

## Task 12: Update Living Documentation

**Files:**
- Modify: `docs/03-architecture.md` — update process architecture, module breakdown, data flow
- Modify: `docs/06-terminal-editor-control.md` — add VS Code extension section
- Modify: `docs/10-implementation-roadmap.md` — revise phases to match new plan

**Step 1: Update docs/03-architecture.md**

Update the process architecture diagram, module breakdown, and data flow sections to reflect:
- VS Code + extension replacing Neovim as primary editor
- Dual-mode execution
- Browser controller
- Planning module (now implemented)
- Activity monitor

**Step 2: Update docs/10-implementation-roadmap.md**

Replace the 5-phase plan with a plan matching this implementation document's task order.

**Step 3: Commit**

```bash
git add docs/03-architecture.md docs/06-terminal-editor-control.md docs/10-implementation-roadmap.md
git commit -m "docs: update architecture and roadmap to match revised design"
```

---

## Summary

| Task | Component | New Files | Test Files | Est. LOC |
|------|-----------|-----------|------------|----------|
| 1 | Config updates | — | test_config.py | ~50 |
| 2 | VS Code extension (TS) | 3 files | — | ~250 |
| 3 | VS Code Python controller | vscode.py | test_vscode_controller.py | ~180 |
| 4 | Task planner | task_planner.py | test_task_planner.py | ~130 |
| 5 | Scheduler | scheduler.py | test_scheduler.py | ~120 |
| 6 | Browser controller | browser.py | test_browser_controller.py | ~150 |
| 7 | Activity monitor | activity_monitor.py | test_activity_monitor.py | ~130 |
| 8 | Mouse simulation | mouse.py | test_mouse.py | ~120 |
| 9 | Orchestrator rewrite | orchestrator.py | test_orchestrator.py | ~500 |
| 10 | CLI + deps update | — | test_cli.py | ~50 |
| 11 | Integration test | — | test_integration.py | ~60 |
| 12 | Docs update | — | — | ~200 |
| **Total** | | **~9 new Python + 3 TS** | **~8 test files** | **~1940** |

Dependencies between tasks: 1 → 2 → 3 → 9, 4 → 5 → 9, 6 → 9, 7 → 9, 8 → 9, 9 → 10 → 11 → 12. Tasks 2-8 can be parallelized after Task 1.
