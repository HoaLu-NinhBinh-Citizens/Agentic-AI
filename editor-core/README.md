# aircore

Local editor core daemon for the AI code assistant — the Rust hot path that the
editor (VS Code fork) talks to. One process per workspace, JSON-RPC 2.0 over
stdio with LSP-style `Content-Length` framing (so the editor reuses
`vscode-jsonrpc`).

## Strategy (read first)

Three decisions shape everything — full records in [docs/ADR.md](docs/ADR.md):

- **ADR-001** — No self-hosted fine-tuning early. Off-the-shelf Qwen2.5-Coder +
  great context engineering. Log accept/reject for a future data flywheel.
- **ADR-002** — Next Edit Prediction = cheap SQL over the symbol graph (where to
  edit) + the model only for non-mechanical edits (what to edit).
- **ADR-003** — Privacy is legal (BAA/ZDR), not location. A Policy Layer picks
  the endpoint; a separate Inference Router picks the model. Completion is
  always local for latency.

### Design docs

- [docs/SYMBOL_GRAPH_SPEC.md](docs/SYMBOL_GRAPH_SPEC.md) — SQLite schema, write
  path, edit classification, the safe-rename caveat.
- [docs/CONTEXT_BUILDER.md](docs/CONTEXT_BUILDER.md) — FIM/chat prompt assembly;
  proximity-ordered (not RRF-ordered) snippet placement.
- [docs/POLICY_LAYER.md](docs/POLICY_LAYER.md) — policy ↔ router split, routing
  tables, sequence diagram.

## Status

### Phase 1 — foundation (done)

- **IPC** (`src/ipc.rs`, `src/protocol.rs`): framed JSON-RPC read/write loop.
- **Merkle index engine** (`src/index/`): gitignore-aware parallel walk
  (`ignore` crate), `(mtime, size)`-gated blake3 content hashing (only changed
  files are re-hashed), delta detection, atomic persisted snapshot.

### Phase 2 — symbol graph (done)

- **Tree-sitter extraction** (`src/symbols/`): definitions + call-site refs for
  Rust and Python; parent nesting via byte-range containment (`File::Class::method`
  qualified names, no collisions).
- **SQLite (WAL) store**: per-file transactional upsert; `find_symbol` and
  `call_sites` queries. `call_sites` is the cheap SQL that powers Next Edit
  Prediction (find where to edit; the model fills in non-mechanical edits).
- **Delta-driven**: only `added` + `modified` files are parsed; `removed` are
  dropped. Consistency guard forces a full reindex if the symbol DB and Merkle
  snapshot diverge.

### RPC methods

| Method             | Params               | Result                       |
|--------------------|----------------------|------------------------------|
| `initialize`       | `{ workspaceRoot }`  | `{ ok, status }`             |
| `index/sync`       | `{}`                 | `SyncResult`                 |
| `index/status`     | `{}`                 | `IndexStatus`                |
| `symbol/find`      | `{ name }`           | `SymbolRow[]`                |
| `symbol/callSites` | `{ name }`           | `RefRow[]`                   |
| `shutdown`         | `{}`                 | `{ ok: true }`               |

`SyncResult` = `{ ...SyncDelta, symbols: SymbolSyncStats }`.
`SyncDelta` = `{ added[], modified[], removed[], root, total_files, hashed_files, elapsed_ms }`.

## Build & test

**Build requirement:** LanceDB's `lance-encoding` compiles protobuf, so a
`protoc` binary must be available. Install it (`winget install Google.Protobuf`,
`brew install protobuf`, or `apt install protobuf-compiler`) and, if it isn't on
`PATH`, point the build at it:

```bash
export PROTOC=/path/to/protoc        # e.g. .../WinGet/Packages/Google.Protobuf.../bin/protoc.exe
cargo build
cargo test                            # the live Ollama test is #[ignore]
cargo build --release                 # opt-level 3 + thin LTO for the hot path
```

### Retrieval backends

`initialize` accepts an optional `retrieval` config; absent ⇒ offline defaults
(HashEmbedder + in-memory store):

```jsonc
"retrieval": {
  "ollama": true,                 // use OllamaEmbedder instead of HashEmbedder
  "ollamaModel": "nomic-embed-text",
  "ollamaDim": 768,
  "ollamaHost": "http://localhost:11434",
  "lance": true                   // persist vectors in .agentic/index/vectors.lance
}
```

State is persisted under `<workspace>/.agentic/index/merkle.json`.

## Roadmap (next phases)

1. **Embeddings → LanceDB** + **Tantivy** lexical index → hybrid retrieval
   (consumes the same delta).
2. **Inference router** + cancellation manager. Routes by `(task, latency)`;
   a separate policy layer picks the cloud endpoint (ZDR vs standard). Local
   model only for the air-gapped tier — privacy is legal (BAA/ZDR), not
   location. No self-hosted fine-tuning early; log accept/reject for a future
   data flywheel.
3. **Completion engine** (FIM, <300ms budget) using Qwen2.5-Coder off-the-shelf.
4. **Next Edit Prediction**: diff the user's last edit → `call_sites` SQL →
   mechanical renames apply for free; signature changes generate via the model.
5. **Apply engine** (tree-sitter validated, atomic, rollback).

See the design spec in the conversation history for the full architecture.
