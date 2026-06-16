# IPC Contract — Next Edit Prediction ("Tab to jump")

Status: **Implemented (core side)** · editor render requires the VS Code fork.

## Where the data comes from

After the editor saves a file it calls `index/sync`. The response now carries a
`suggestions` array alongside the Merkle delta and symbol stats. Each suggestion
is what powers a "Tab to jump" indicator.

The core does the hard part (detect the edit, find every site, pre-compute
mechanical replacements). The editor only renders and applies — no model call on
the editor side for mechanical renames.

## `index/sync` result shape

```jsonc
{
  // ...SyncDelta fields (added, modified, removed, root, ...)...
  "symbols": { "files_parsed": 1, "symbols": 12, "refs": 30, "elapsed_ms": 7 },
  "suggestions": [
    {
      "kind": "rename",            // "rename" | "signature_change"
      "old_name": "area",
      "new_name": "surface",
      "mechanical": true,          // true => apply verbatim, no model
      "edits": [                   // populated for mechanical renames
        { "file": "main.rs", "start_byte": 16, "end_byte": 20, "new_text": "surface" },
        { "file": "main.rs", "start_byte": 31, "end_byte": 35, "new_text": "surface" }
      ],
      "sites": [                   // jump targets (always present)
        { "file": "main.rs", "start_row": 1, "start_byte": 16, "end_byte": 20 },
        { "file": "main.rs", "start_row": 2, "start_byte": 31, "end_byte": 35 }
      ]
    }
  ]
}
```

## Editor behavior (VS Code fork)

1. On the `index/sync` response, for each suggestion render a **"Tab to jump"**
   indicator at the `sites`, ordered nearest-cursor-first.
2. **`mechanical: true`** → pressing Tab jumps to the site and applies the
   corresponding `edits` entry verbatim (overwrite `[start_byte, end_byte)` with
   `new_text`). Zero latency, zero tokens.
3. **`mechanical: false`** (signature change) → jump to each `site` and request a
   model-generated edit for that site (`edits` is empty by design); the model
   supplies the non-mechanical change (e.g. a new argument).
4. After accept/reject, emit a `telemetry/completion` notification (see
   `ADR.md` / telemetry sink) so the data flywheel records the outcome.

## Guarantees & limits

- Byte spans are exact identifier ranges — applying `edits` cannot corrupt
  surrounding code.
- v1 matches call sites by **name** (no cross-module resolution yet), so a
  mechanical rename may include same-named symbols from unrelated modules. The
  per-site Tab-to-jump confirmation is the safety net; do **not** auto-apply all
  edits silently. Resolution (`target_symbol_id`) is the v2 fix
  (`SYMBOL_GRAPH_SPEC.md` §5).
