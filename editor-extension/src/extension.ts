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
      telemetry: cfg.get<boolean>("telemetry", true),
      retrieval: {
        ollama: cfg.get<boolean>("useOllamaEmbeddings", false),
        lance: cfg.get<boolean>("useLance", false),
      },
    });
    await client.request("index/sync", {});
    output.appendLine("aircode: initialized + indexed.");
    warmUpModel(cfg); // fire-and-forget: avoid a multi-second cold load on the first completion
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
    vscode.commands.registerCommand("aircode.resync", refreshSuggestions),
    vscode.commands.registerCommand("aircode.inlineEdit", inlineEdit),
    vscode.commands.registerCommand("aircode.completionAccepted", (meta: any) =>
      sendTelemetry({ task: "completion", outcome: "accepted", ...(meta ?? {}) })
    ),
    vscode.window.registerWebviewViewProvider("aircode.chat", new ChatViewProvider(context))
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
  // Packaged app: the daemon is bundled next to the extension (see fork/bundle.mjs).
  const bundled = path.join(context.extensionPath, "bin", exe);
  if (fs.existsSync(bundled)) return bundled;
  // Dev layout: a sibling editor-core/target build.
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

    const model = cfg.get<string>("completionModel", "qwen2.5-coder:1.5b-base");
    const started = Date.now();
    const completion = await generateFromOllama(
      cfg.get<string>("ollamaHost", "http://localhost:11434"),
      model,
      prompt.text,
      token
    );
    if (!completion || token.isCancellationRequested) return;

    const meta = {
      model,
      latency_ms: Date.now() - started,
      prompt_token_estimate: prompt.token_estimate,
      context: { included: prompt.included, dropped: prompt.dropped },
    };
    // Record that a suggestion was shown; the accept command fires if taken.
    sendTelemetry({ task: "completion", outcome: "shown", ...meta });

    const item = new vscode.InlineCompletionItem(completion, new vscode.Range(position, position));
    item.command = { command: "aircode.completionAccepted", title: "", arguments: [meta] };
    return [item];
  }
}

/** Fire-and-forget a telemetry event to the daemon's async sink (off the hot
 *  path; the daemon drops on backpressure). Stamps ts here. */
function sendTelemetry(event: Record<string, unknown>): void {
  client?.notify("telemetry/log", { ts_ms: Date.now(), ...event });
}

/** Apply a chat code block to the active editor: replace the selection if there
 *  is one, otherwise insert at the cursor. */
async function applyCodeToEditor(code: string): Promise<void> {
  const editor = vscode.window.activeTextEditor ?? vscode.window.visibleTextEditors[0];
  if (!editor) {
    vscode.window.showWarningMessage("aircode: open a file to apply the code into.");
    return;
  }
  const sel = editor.selection;
  await editor.edit((eb) => {
    if (sel.isEmpty) eb.insert(sel.active, code);
    else eb.replace(sel, code);
  });
  sendTelemetry({ task: "chat_apply", outcome: "accepted" });
}

/** Load the completion model into memory at startup so the first real
 *  completion doesn't pay the cold-load penalty (~7s -> ~400ms warm). */
function warmUpModel(cfg: vscode.WorkspaceConfiguration): void {
  const host = cfg.get<string>("ollamaHost", "http://localhost:11434");
  const model = cfg.get<string>("completionModel", "qwen2.5-coder:1.5b-base");
  fetch(`${host}/api/generate`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ model, prompt: "", raw: true, stream: false, keep_alive: "30m", options: { num_predict: 1 } }),
  })
    .then(() => output.appendLine(`aircode: warmed model ${model}`))
    .catch(() => output.appendLine(`aircode: model warm-up skipped (Ollama not reachable?)`));
}

/** Stream the FIM completion from Ollama and return as soon as the first
 *  non-empty line is complete. Streaming + early-stop is the latency win: we
 *  stop generating once we have a usable single-line suggestion instead of
 *  waiting for the full 128-token response (~800ms -> ~first-token time). The
 *  abort also fires the instant the user types again. */
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
        stream: true,
        keep_alive: "30m", // keep the model resident; avoids cold loads
        options: { num_predict: 128, stop: ["<|fim_prefix|>", "<|file_sep|>"] },
      }),
      signal: controller.signal,
    });
    if (!resp.ok || !resp.body) {
      output.appendLine(`ollama ${resp.status}`);
      return;
    }

    const reader = resp.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    let out = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let nl: number;
      while ((nl = buf.indexOf("\n")) >= 0) {
        const line = buf.slice(0, nl);
        buf = buf.slice(nl + 1);
        if (!line.trim()) continue;
        try {
          const j = JSON.parse(line);
          if (typeof j.response === "string") out += j.response;
          // Early-stop: once we have a full first line of completion, return it.
          if (out.includes("\n") && out.split("\n")[0].trim().length > 0) {
            controller.abort();
            return out.split("\n")[0];
          }
          if (j.done) return out.replace(/\s+$/, "");
        } catch {
          /* partial JSON line */
        }
      }
    }
    return out.replace(/\s+$/, "");
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

/** Sidebar chat: codebase Q&A. Retrieves context from the daemon, streams an
 *  answer from an Ollama instruct model token-by-token into the webview. */
class ChatViewProvider implements vscode.WebviewViewProvider {
  private history: { role: string; content: string }[] = [];
  /// Workspace file list (relative paths) for @-mention autocomplete.
  private files: string[] = [];
  constructor(private readonly context: vscode.ExtensionContext) {}

  resolveWebviewView(view: vscode.WebviewView): void {
    view.webview.options = { enableScripts: true };
    view.webview.html = this.html();
    view.webview.onDidReceiveMessage(async (msg) => {
      if (msg?.type === "ask" && typeof msg.text === "string") {
        await this.answer(view, msg.text.trim());
      } else if (msg?.type === "reset") {
        this.history = [];
      } else if (msg?.type === "apply" && typeof msg.code === "string") {
        await applyCodeToEditor(msg.code);
      }
    });
    void this.loadFiles(view);
  }

  /// Populate the @-mention file list and push it to the webview.
  private async loadFiles(view: vscode.WebviewView): Promise<void> {
    try {
      const uris = await vscode.workspace.findFiles(
        "**/*",
        "**/{node_modules,.git,target,.agentic,out,dist}/**",
        5000
      );
      this.files = uris
        .map((u) => vscode.workspace.asRelativePath(u, false).replace(/\\/g, "/"))
        .sort();
      view.webview.postMessage({ type: "files", list: this.files });
    } catch (e) {
      output.appendLine(`@-mention file list failed: ${e}`);
    }
  }

  /// Resolve `@path` mentions in the question to file contents (capped).
  private async resolveMentions(question: string): Promise<string> {
    const tokens = [...question.matchAll(/@([\w./\-]+)/g)].map((m) => m[1]);
    const folder = vscode.workspace.workspaceFolders?.[0];
    if (!tokens.length || !folder) return "";
    const seen = new Set<string>();
    const blocks: string[] = [];
    for (const t of tokens) {
      const match = this.files.find(
        (f) => f === t || f.endsWith("/" + t) || f.split("/").pop() === t
      );
      if (!match || seen.has(match)) continue;
      seen.add(match);
      try {
        const bytes = await vscode.workspace.fs.readFile(vscode.Uri.joinPath(folder.uri, match));
        let text = Buffer.from(bytes).toString("utf8");
        const CAP = 8000;
        if (text.length > CAP) text = text.slice(0, CAP) + "\n… (truncated)";
        blocks.push(`// @${match}\n${text}`);
      } catch {
        /* unreadable */
      }
    }
    return blocks.join("\n\n");
  }

  private async answer(view: vscode.WebviewView, question: string): Promise<void> {
    if (!question || !client) return;
    const cfg = vscode.workspace.getConfiguration("aircode");

    // Codebase context via the daemon's retriever.
    let context = "";
    try {
      const s = await client.request<{ file: string; start_row: number; text: string }[]>(
        "retrieve",
        { query: question, k: 5 }
      );
      context = s.map((x) => `// ${x.file}:${x.start_row}\n${x.text}`).join("\n\n");
    } catch (e) {
      output.appendLine(`chat retrieve failed: ${e}`);
    }

    // Explicit @-mentioned files take priority over retrieved snippets.
    const mentioned = await this.resolveMentions(question);

    this.history.push({
      role: "user",
      content:
        (mentioned ? `Mentioned files:\n${mentioned}\n\n` : "") +
        (context ? `Relevant code:\n${context}\n\n` : "") +
        question,
    });
    // Bound the context window: keep the last 6 turns.
    if (this.history.length > 6) this.history = this.history.slice(-6);

    const host = cfg.get<string>("ollamaHost", "http://localhost:11434");
    const model = cfg.get<string>("chatModel", "qwen2.5-coder:7b");
    const system =
      "You are aircode, a coding assistant. Answer questions about the user's codebase using the provided context. Be concise and show code in fenced blocks.";

    view.webview.postMessage({ type: "start" });
    let answer = "";
    try {
      const resp = await fetch(`${host}/api/chat`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          model,
          stream: true,
          keep_alive: "30m",
          messages: [{ role: "system", content: system }, ...this.history],
        }),
      });
      if (!resp.ok || !resp.body) {
        view.webview.postMessage({ type: "token", value: `\n[ollama error ${resp.status}]` });
      } else {
        const reader = resp.body.getReader();
        const dec = new TextDecoder();
        let buf = "";
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += dec.decode(value, { stream: true });
          let nl: number;
          while ((nl = buf.indexOf("\n")) >= 0) {
            const line = buf.slice(0, nl);
            buf = buf.slice(nl + 1);
            if (!line.trim()) continue;
            try {
              const tok = JSON.parse(line)?.message?.content ?? "";
              if (tok) {
                answer += tok;
                view.webview.postMessage({ type: "token", value: tok });
              }
            } catch {
              /* partial line */
            }
          }
        }
      }
    } catch (e) {
      view.webview.postMessage({ type: "token", value: `\n[chat failed: ${e}]` });
    }
    if (answer) this.history.push({ role: "assistant", content: answer });
    view.webview.postMessage({ type: "done" });
  }

  private html(): string {
    // Self-contained; minimal vanilla JS. Streams tokens into the last bubble.
    return `<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
 body{font-family:var(--vscode-font-family);font-size:13px;color:var(--vscode-foreground);margin:0;display:flex;flex-direction:column;height:100vh}
 #log{flex:1;overflow-y:auto;padding:8px}
 .msg{margin:6px 0;padding:6px 8px;border-radius:6px;white-space:pre-wrap;word-break:break-word}
 .user{background:var(--vscode-editor-inactiveSelectionBackground)}
 .bot{background:var(--vscode-textCodeBlock-background)}
 #bar{display:flex;border-top:1px solid var(--vscode-panel-border);padding:6px;gap:6px}
 #q{flex:1;background:var(--vscode-input-background);color:var(--vscode-input-foreground);border:1px solid var(--vscode-input-border);border-radius:4px;padding:6px;resize:none}
 button{background:var(--vscode-button-background);color:var(--vscode-button-foreground);border:none;border-radius:4px;padding:2px 10px;cursor:pointer}
 pre{background:var(--vscode-editor-background);border:1px solid var(--vscode-panel-border);border-radius:4px;padding:6px;overflow-x:auto;margin:4px 0}
 code{font-family:var(--vscode-editor-font-family,monospace)}
 .codehdr{display:flex;justify-content:flex-end;margin-top:6px}
 #ac{position:fixed;left:6px;right:6px;bottom:56px;background:var(--vscode-editorWidget-background,var(--vscode-input-background));border:1px solid var(--vscode-panel-border);border-radius:4px;max-height:160px;overflow-y:auto;display:none;z-index:10}
 #ac div{padding:3px 8px;cursor:pointer;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
 #ac div.sel,#ac div:hover{background:var(--vscode-list-activeSelectionBackground);color:var(--vscode-list-activeSelectionForeground)}
</style></head><body>
 <div id="log"></div>
 <div id="ac"></div>
 <div id="bar"><textarea id="q" rows="2" placeholder="Ask… use @file to add a file to context  (Enter to send)"></textarea><button id="send">Send</button></div>
<script>
 const vscode=acquireVsCodeApi();const log=document.getElementById('log');const q=document.getElementById('q');const ac=document.getElementById('ac');let bot=null;let botText="";let files=[];let sel=-1;
 function add(cls,text){const d=document.createElement('div');d.className='msg '+cls;d.textContent=text;log.appendChild(d);log.scrollTop=log.scrollHeight;return d;}
 function ask(){const t=q.value.trim();if(!t)return;hideAc();add('user',t);q.value='';bot=null;botText="";vscode.postMessage({type:'ask',text:t});}
 document.getElementById('send').onclick=ask;
 // --- @-mention autocomplete ---
 function token(){const v=q.value.slice(0,q.selectionStart);const m=v.match(/@([\\w./\\-]*)$/);return m?m[1]:null;}
 function hideAc(){ac.style.display='none';sel=-1;}
 function showAc(){const t=token();if(t===null){hideAc();return;}
   const q2=t.toLowerCase();const hits=files.filter(f=>f.toLowerCase().includes(q2)).slice(0,8);
   if(!hits.length){hideAc();return;}
   ac.innerHTML='';hits.forEach((f,i)=>{const d=document.createElement('div');d.textContent=f;if(i===0){d.className='sel';sel=0;}d.onmousedown=(e)=>{e.preventDefault();pick(f);};ac.appendChild(d);});
   ac.style.display='block';}
 function pick(f){const v=q.value;const cut=q.selectionStart;const before=v.slice(0,cut).replace(/@([\\w./\\-]*)$/,'@'+f+' ');q.value=before+v.slice(cut);q.focus();hideAc();}
 q.addEventListener('input',showAc);
 q.addEventListener('keydown',e=>{
   const open=ac.style.display==='block';const items=[...ac.children];
   if(open&&(e.key==='ArrowDown'||e.key==='ArrowUp')){e.preventDefault();if(sel>=0)items[sel].className='';sel=(sel+(e.key==='ArrowDown'?1:items.length-1))%items.length;items[sel].className='sel';items[sel].scrollIntoView({block:'nearest'});return;}
   if(open&&(e.key==='Enter'||e.key==='Tab')&&sel>=0){e.preventDefault();pick(items[sel].textContent);return;}
   if(e.key==='Escape'){hideAc();return;}
   if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();ask();}
 });
 // On done, re-render the bot bubble: plain text + code blocks with Apply buttons.
 function render(el,text){
   el.textContent="";el.style.whiteSpace="normal";
   const re=/\`\`\`[^\\n]*\\n?([\\s\\S]*?)\`\`\`/g;let last=0,m;
   const addText=(s)=>{if(!s)return;const span=document.createElement('div');span.style.whiteSpace="pre-wrap";span.textContent=s;el.appendChild(span);};
   while((m=re.exec(text))!==null){
     addText(text.slice(last,m.index));last=re.lastIndex;
     const code=m[1].replace(/\\s+$/,"");
     const hdr=document.createElement('div');hdr.className='codehdr';
     const btn=document.createElement('button');btn.textContent='Apply';btn.onclick=()=>vscode.postMessage({type:'apply',code});
     hdr.appendChild(btn);el.appendChild(hdr);
     const pre=document.createElement('pre');const c=document.createElement('code');c.textContent=code;pre.appendChild(c);el.appendChild(pre);
   }
   addText(text.slice(last));
 }
 window.addEventListener('message',e=>{const m=e.data;
   if(m.type==='files'){files=m.list||[];}
   else if(m.type==='start'){bot=add('bot','');botText="";}
   else if(m.type==='token'){if(!bot){bot=add('bot','');}botText+=m.value;bot.textContent=botText;log.scrollTop=log.scrollHeight;}
   else if(m.type==='done'){if(bot)render(bot,botText);log.scrollTop=log.scrollHeight;}
 });
</script></body></html>`;
  }
}

/** Cmd+K: rewrite the selection (or current line) per a natural-language
 *  instruction, using codebase context from the daemon + an instruct model. */
async function inlineEdit(): Promise<void> {
  const editor = vscode.window.activeTextEditor;
  if (!editor || !client) return;

  const sel = editor.selection;
  const range = sel.isEmpty ? editor.document.lineAt(sel.active.line).range : new vscode.Range(sel.start, sel.end);
  const selectionText = editor.document.getText(range);

  const instruction = await vscode.window.showInputBox({
    prompt: "aircode — describe the edit",
    placeHolder: "e.g. make this async · add error handling · convert to a for-loop",
  });
  if (!instruction) return;

  const cfg = vscode.workspace.getConfiguration("aircode");
  await vscode.window.withProgress(
    { location: vscode.ProgressLocation.Notification, title: "aircode: editing…" },
    async () => {
      // Codebase context (best-effort — proceed even if retrieval fails).
      let context = "";
      try {
        const snippets = await client!.request<{ file: string; start_row: number; text: string }[]>(
          "retrieve",
          { query: `${instruction}\n${selectionText}`, k: 4 }
        );
        context = snippets.map((s) => `// ${s.file}:${s.start_row}\n${s.text}`).join("\n\n");
      } catch (e) {
        output.appendLine(`retrieve failed (continuing without context): ${e}`);
      }

      const produced = await editViaOllamaStream(
        editor,
        range,
        cfg,
        editor.document.languageId,
        context,
        instruction,
        selectionText
      );
      if (!produced) {
        vscode.window.showWarningMessage("aircode: no edit produced (Ollama reachable? model pulled?).");
      }
    }
  );
}

/** Strip a single ```lang … ``` markdown fence if the model wrapped its output. */
function stripCodeFence(s: string): string {
  const m = s.match(/^\s*```[^\n]*\n([\s\S]*?)\n```\s*$/);
  return (m ? m[1] : s).replace(/\s+$/, "");
}

/** Stream an instruct-model rewrite of the selection, writing tokens into the
 *  editor as they arrive (throttled) so the user sees it "type" instead of
 *  waiting for the whole response. Returns true if any text was produced. */
async function editViaOllamaStream(
  editor: vscode.TextEditor,
  range: vscode.Range,
  cfg: vscode.WorkspaceConfiguration,
  lang: string,
  context: string,
  instruction: string,
  code: string
): Promise<boolean> {
  const host = cfg.get<string>("ollamaHost", "http://localhost:11434");
  const model = cfg.get<string>("editModel", "qwen2.5-coder:7b");
  const system =
    "You are a precise code editor. Rewrite the user's selected code to satisfy the instruction. " +
    "Output ONLY the replacement code — no markdown fences, no explanation, preserve surrounding indentation.";
  const user =
    (context ? `Relevant context:\n${context}\n\n` : "") +
    `Instruction: ${instruction}\n\nLanguage: ${lang}\nSelected code:\n${code}`;

  const startOffset = editor.document.offsetAt(range.start);
  let prevLen = code.length; // current length of the region we own (starts as the selection)
  let acc = "";
  let applying = false;

  // Replace the region we own with the latest stripped accumulation.
  const apply = async () => {
    applying = true;
    const text = stripCodeFence(acc);
    const endPos = editor.document.positionAt(startOffset + prevLen);
    await editor.edit((eb) => eb.replace(new vscode.Range(range.start, endPos), text), {
      undoStopBefore: false,
      undoStopAfter: false,
    });
    prevLen = text.length;
    applying = false;
  };

  try {
    const resp = await fetch(`${host}/api/chat`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        model,
        stream: true,
        keep_alive: "30m",
        messages: [
          { role: "system", content: system },
          { role: "user", content: user },
        ],
      }),
    });
    if (!resp.ok || !resp.body) {
      output.appendLine(`ollama chat ${resp.status}`);
      return false;
    }

    const reader = resp.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    let lastFlush = 0;
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let nl: number;
      while ((nl = buf.indexOf("\n")) >= 0) {
        const line = buf.slice(0, nl);
        buf = buf.slice(nl + 1);
        if (!line.trim()) continue;
        try {
          const tok = JSON.parse(line)?.message?.content ?? "";
          if (tok) acc += tok;
        } catch {
          /* partial line */
        }
      }
      // Throttle editor writes to ~16/s and never overlap edits.
      const now = Date.now();
      if (!applying && acc && now - lastFlush > 60) {
        lastFlush = now;
        await apply();
      }
    }
    if (acc) await apply(); // final flush
    return acc.length > 0;
  } catch (e) {
    output.appendLine(`ollama chat failed: ${e}`);
    return acc.length > 0;
  }
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
