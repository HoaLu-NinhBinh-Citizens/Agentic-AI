import * as fs from "fs";
import * as path from "path";
import * as vscode from "vscode";

import { DaemonClient } from "./daemonClient";

// --- daemon payload shapes (mirror editor-core) ---
interface BuiltPrompt {
  text: string;
  token_estimate: number;
  included: { file: string; start_row: number; kind: string }[];
  dropped: number;
}
interface Replacement {
  file: string;
  start_byte: number;
  end_byte: number;
  new_text: string;
}
interface EditSite {
  file: string;
  start_row: number;
  start_byte: number;
  end_byte: number;
}
interface EditSuggestion {
  kind: string;
  old_name: string;
  new_name: string;
  mechanical: boolean;
  edits: Replacement[];
  sites: EditSite[];
}
interface SyncResult {
  suggestions: EditSuggestion[];
}

let client: DaemonClient | undefined;
let latestSuggestions: EditSuggestion[] = [];
let output: vscode.OutputChannel;
let suggestionDecoration: vscode.TextEditorDecorationType;

export async function activate(context: vscode.ExtensionContext): Promise<void> {
  output = vscode.window.createOutputChannel("aircode");
  suggestionDecoration = vscode.window.createTextEditorDecorationType({
    after: { contentText: "  ⇥ rename", color: new vscode.ThemeColor("editorCodeLens.foreground") },
  });

  const folder = vscode.workspace.workspaceFolders?.[0];
  if (!folder) {
    output.appendLine("No workspace folder; aircode inactive.");
    return;
  }
  const workspaceRoot = folder.uri.fsPath;

  const daemonPath = resolveDaemonPath(context);
  if (!daemonPath) {
    vscode.window.showErrorMessage("aircode: aircore daemon binary not found. Set aircode.daemonPath.");
    return;
  }

  client = new DaemonClient(daemonPath, (l) => output.appendLine(`[daemon] ${l}`));
  client.start();

  const cfg = vscode.workspace.getConfiguration("aircode");
  try {
    await client.request("initialize", {
      workspaceRoot,
      retrieval: {
        ollama: cfg.get<boolean>("useOllamaEmbeddings", false),
        lance: cfg.get<boolean>("useLance", false),
      },
    });
    await client.request("index/sync", {});
    output.appendLine("aircode: initialized + indexed.");
  } catch (e) {
    output.appendLine(`aircode init failed: ${e}`);
  }

  // Inline completion.
  context.subscriptions.push(
    vscode.languages.registerInlineCompletionItemProvider(
      { pattern: "**" },
      new AirInlineProvider()
    )
  );

  // Re-index + Next-Edit suggestions on save.
  context.subscriptions.push(
    vscode.workspace.onDidSaveTextDocument(async () => {
      await refreshSuggestions();
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("aircode.applyNextEdits", applyNextEdits),
    vscode.commands.registerCommand("aircode.resync", refreshSuggestions)
  );

  context.subscriptions.push({ dispose: () => client?.stop() });
}

export function deactivate(): void {
  client?.stop();
}

function resolveDaemonPath(context: vscode.ExtensionContext): string | undefined {
  const configured = vscode.workspace.getConfiguration("aircode").get<string>("daemonPath");
  if (configured && fs.existsSync(configured)) return configured;
  const exe = process.platform === "win32" ? "aircore.exe" : "aircore";
  // Look under a sibling editor-core/target (dev layout).
  const root = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath ?? "";
  for (const profile of ["release", "debug"]) {
    const candidate = path.join(root, "editor-core", "target", profile, exe);
    if (fs.existsSync(candidate)) return candidate;
  }
  return undefined;
}

/** UTF-8 byte offset of a position (the daemon speaks byte offsets). */
function cursorByteOffset(document: vscode.TextDocument, position: vscode.Position): number {
  const before = document.getText(new vscode.Range(new vscode.Position(0, 0), position));
  return Buffer.byteLength(before, "utf8");
}

/** Convert a UTF-8 byte offset back to a Position for applying edits. */
function byteToPosition(document: vscode.TextDocument, byteOffset: number): vscode.Position {
  const buf = Buffer.from(document.getText(), "utf8");
  const utf16Index = buf.subarray(0, byteOffset).toString("utf8").length;
  return document.positionAt(utf16Index);
}

class AirInlineProvider implements vscode.InlineCompletionItemProvider {
  async provideInlineCompletionItems(
    document: vscode.TextDocument,
    position: vscode.Position,
    _context: vscode.InlineCompletionContext,
    token: vscode.CancellationToken
  ): Promise<vscode.InlineCompletionItem[] | undefined> {
    if (!client) return;
    const cfg = vscode.workspace.getConfiguration("aircode");
    const file = vscode.workspace.asRelativePath(document.uri, false).replace(/\\/g, "/");

    let prompt: BuiltPrompt;
    try {
      prompt = await client.request<BuiltPrompt>("context/completion", {
        file,
        cursorByte: cursorByteOffset(document, position),
        maxTokens: cfg.get<number>("maxContextTokens", 2000),
      });
    } catch (e) {
      output.appendLine(`context/completion failed: ${e}`);
      return;
    }
    if (token.isCancellationRequested) return;

    const completion = await generateFromOllama(
      cfg.get<string>("ollamaHost", "http://localhost:11434"),
      cfg.get<string>("completionModel", "qwen2.5-coder:3b"),
      prompt.text,
      token
    );
    if (!completion || token.isCancellationRequested) return;

    return [new vscode.InlineCompletionItem(completion, new vscode.Range(position, position))];
  }
}

/** Send the FIM prompt to Ollama's raw generate endpoint. */
async function generateFromOllama(
  host: string,
  model: string,
  prompt: string,
  token: vscode.CancellationToken
): Promise<string | undefined> {
  const controller = new AbortController();
  token.onCancellationRequested(() => controller.abort());
  try {
    const resp = await fetch(`${host}/api/generate`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        model,
        prompt,
        raw: true, // the FIM prompt already carries the model's control tokens
        stream: false,
        options: { num_predict: 128, stop: ["<|fim_prefix|>", "<|file_sep|>"] },
      }),
      signal: controller.signal,
    });
    if (!resp.ok) {
      output.appendLine(`ollama ${resp.status}`);
      return;
    }
    const data: any = await resp.json();
    return typeof data.response === "string" ? data.response : undefined;
  } catch (e) {
    if (!controller.signal.aborted) output.appendLine(`ollama generate failed: ${e}`);
    return;
  }
}

async function refreshSuggestions(): Promise<void> {
  if (!client) return;
  try {
    const result = await client.request<SyncResult>("index/sync", {});
    latestSuggestions = result.suggestions ?? [];
  } catch (e) {
    output.appendLine(`sync failed: ${e}`);
    latestSuggestions = [];
  }
  await vscode.commands.executeCommand(
    "setContext",
    "aircode.hasSuggestions",
    latestSuggestions.some((s) => s.mechanical)
  );
  decorateSuggestions();
}

function decorateSuggestions(): void {
  const editor = vscode.window.activeTextEditor;
  if (!editor) return;
  const file = vscode.workspace.asRelativePath(editor.document.uri, false).replace(/\\/g, "/");
  const ranges: vscode.Range[] = [];
  for (const s of latestSuggestions) {
    if (!s.mechanical) continue;
    for (const site of s.sites) {
      if (site.file !== file) continue;
      const line = editor.document.lineAt(Math.min(site.start_row, editor.document.lineCount - 1));
      ranges.push(line.range);
    }
  }
  editor.setDecorations(suggestionDecoration, ranges);
}

/** Apply all mechanical (rename) edits across files via a single WorkspaceEdit. */
async function applyNextEdits(): Promise<void> {
  const edit = new vscode.WorkspaceEdit();
  const folder = vscode.workspace.workspaceFolders?.[0];
  if (!folder) return;

  let count = 0;
  for (const s of latestSuggestions) {
    if (!s.mechanical) continue;
    // Group edits by file so each document is opened once.
    const byFile = new Map<string, Replacement[]>();
    for (const e of s.edits) {
      const arr = byFile.get(e.file) ?? [];
      arr.push(e);
      byFile.set(e.file, arr);
    }
    for (const [rel, reps] of byFile) {
      const uri = vscode.Uri.joinPath(folder.uri, rel);
      let doc: vscode.TextDocument;
      try {
        doc = await vscode.workspace.openTextDocument(uri);
      } catch {
        continue;
      }
      // Apply from the end backwards so earlier byte offsets stay valid.
      reps.sort((a, b) => b.start_byte - a.start_byte);
      for (const r of reps) {
        const range = new vscode.Range(
          byteToPosition(doc, r.start_byte),
          byteToPosition(doc, r.end_byte)
        );
        edit.replace(uri, range, r.new_text);
        count++;
      }
    }
  }

  if (count === 0) {
    vscode.window.showInformationMessage("aircode: no mechanical edits to apply.");
    return;
  }
  await vscode.workspace.applyEdit(edit);
  latestSuggestions = [];
  await vscode.commands.executeCommand("setContext", "aircode.hasSuggestions", false);
  decorateSuggestions();
  vscode.window.showInformationMessage(`aircode: applied ${count} edit(s).`);
}
