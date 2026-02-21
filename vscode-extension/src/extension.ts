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
