# aircode — VS Code extension

The editor integration layer for the aircore daemon. Runs as a standard VS Code
extension today; it is the same code that will be folded into the VS Code **fork**
later (the fork adds deeper UX — true Tab-to-jump chaining, custom diff UI — that
the extension API can't fully express).

## What it does

- **Spawns the aircore daemon** (one per workspace) and speaks JSON-RPC over
  stdio (`src/daemonClient.ts`, Content-Length framing matching `editor-core`).
- **Inline completion** — on keystroke, asks the daemon for a budgeted FIM
  prompt (`context/completion`, proximity-ordered context) and sends it to a
  local model via Ollama's raw `generate` endpoint. Cancellable per keystroke.
- **Next Edit Prediction** — on save, calls `index/sync`; mechanical-rename
  suggestions are decorated (`⇥ rename`) and applied across files by
  `aircode.applyNextEdits` (bound to Tab when suggestions exist), via a single
  `WorkspaceEdit`. Byte spans from the daemon are mapped back to positions.

## Prerequisites

1. Build the daemon: in `editor-core`, `cargo build --release` (or debug). The
   extension auto-discovers `editor-core/target/{release,debug}/aircore[.exe]`,
   or set `aircode.daemonPath`.
2. For completion: a running [Ollama](https://ollama.com) with a code model,
   e.g. `ollama pull qwen2.5-coder:3b` (configurable via
   `aircode.completionModel`).

## Run it

```bash
npm install
npm run compile          # tsc -> out/
```

Then press **F5** in VS Code to launch an Extension Development Host with this
extension loaded. Open a folder, edit a file, and completions appear inline;
rename a function and save to see Next-Edit `⇥ rename` markers (Tab to apply).

## Settings

| Setting | Default | Meaning |
|---|---|---|
| `aircode.daemonPath` | `""` | Daemon binary path (empty = auto-discover). |
| `aircode.completionModel` | `qwen2.5-coder:3b` | Ollama model for inline completion. |
| `aircode.ollamaHost` | `http://localhost:11434` | Ollama endpoint. |
| `aircode.maxContextTokens` | `2000` | Completion context budget. |
| `aircode.useLance` | `false` | Persist embeddings in LanceDB (daemon must be built with it). |
| `aircode.useOllamaEmbeddings` | `false` | Use Ollama embeddings instead of the offline default. |

## Verified

`tsc` compiles clean, and the daemon client is verified end-to-end against a
real `aircore` process (initialize → sync → context/completion returns a FIM
prompt with cross-file context). The inline-completion and Tab-to-jump UX must
be exercised in the Extension Development Host (F5).

## Scope note

This is the **integration extension**, not yet the rebranded Electron fork.
Cloning + building the full VS Code fork is a separate packaging step; this code
is the behavior layer that drives it.
