# Technical Spec — Symbol Graph

Status: **Design** (paper). Supersedes the schema currently in
`src/symbols/store.rs`. Differences from the implemented v0 are called out
inline as **[MIGRATION]** so the team knows what changes when this lands.

## 1. Purpose

The symbol graph is the structural index that powers three consumers:

- **Retrieval** — pull definitions of symbols referenced near the cursor.
- **Next Edit Prediction (ADR-002)** — find call sites cheaply (SQL), and
  classify a user's edit as *mechanical rename* (free, no model) vs *semantic
  signature change* (needs the model).
- **Navigation** — go-to-definition / find-references in the editor.

Everything is driven by the Merkle `SyncDelta`: only `added` + `modified`
files are re-parsed; `removed` files cascade-delete. The graph never scans the
whole repo.

## 2. Schema (SQLite, WAL)

```sql
PRAGMA journal_mode = WAL;       -- readers (completion) never block the writer (sync)
PRAGMA synchronous  = NORMAL;
PRAGMA foreign_keys = ON;        -- enables ON DELETE CASCADE below

-- [MIGRATION] v0 denormalizes file as a TEXT column on every row.
-- v1 normalizes into a files table: smaller rows, integer joins, and a
-- file rename becomes a single UPDATE instead of rewriting every symbol/ref.
CREATE TABLE files (
    id            INTEGER PRIMARY KEY,
    path          TEXT    NOT NULL UNIQUE,  -- workspace-relative, forward slashes
    lang          TEXT    NOT NULL,         -- 'rust' | 'python' | ...
    content_hash  TEXT    NOT NULL,         -- blake3 from Merkle; lets the graph
                                            -- assert it parsed the same bytes
    indexed_at    INTEGER NOT NULL          -- epoch ms (passed in from caller)
);

CREATE TABLE symbols (
    id              INTEGER PRIMARY KEY,
    file_id         INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    name            TEXT    NOT NULL,
    kind            TEXT    NOT NULL,        -- 'function' | 'struct' | 'class' | ...
    parent_id       INTEGER REFERENCES symbols(id) ON DELETE CASCADE,
    qualified_name  TEXT    NOT NULL,        -- file::A::B::name (collision-free)

    -- Definition span (whole item) — go-to-def + body extraction.
    start_byte      INTEGER NOT NULL,
    end_byte        INTEGER NOT NULL,
    start_row       INTEGER NOT NULL,

    -- [MIGRATION] NEW. Exact identifier span of the *name token* within the
    -- definition. Needed to mechanically rename the definition site itself,
    -- not just its call sites.
    name_start_byte INTEGER NOT NULL,
    name_end_byte   INTEGER NOT NULL,

    signature       TEXT    NOT NULL,        -- first line, trimmed (human-facing)

    -- [MIGRATION] NEW. blake3 of the *normalized* signature (name token
    -- replaced by a placeholder, whitespace collapsed). This is the crux of
    -- ADR-002: a rename leaves signature_hash UNCHANGED, a param/return-type
    -- change FLIPS it. One cheap comparison decides mechanical vs semantic.
    signature_hash  TEXT    NOT NULL
);

CREATE TABLE refs (
    id              INTEGER PRIMARY KEY,
    file_id         INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    name            TEXT    NOT NULL,        -- callee identifier (as written)

    -- [MIGRATION] NEW. Resolved definition, when we can resolve it. NULL means
    -- "unresolved / cross-module / external". See §5 on why this matters for
    -- SAFE rename — name-only matching over-matches.
    target_symbol_id INTEGER REFERENCES symbols(id) ON DELETE SET NULL,

    -- Exact identifier span. v0 stored only start_byte; [MIGRATION] adds
    -- end_byte so a mechanical replace can target [start_byte, end_byte)
    -- precisely without re-parsing.
    start_byte      INTEGER NOT NULL,
    end_byte        INTEGER NOT NULL,
    start_row       INTEGER NOT NULL,

    ref_kind        TEXT    NOT NULL          -- 'call' | 'import' | 'type' | ...
);

CREATE INDEX idx_symbols_name   ON symbols(name);
CREATE INDEX idx_symbols_file   ON symbols(file_id);
CREATE INDEX idx_symbols_qname  ON symbols(qualified_name);
CREATE INDEX idx_refs_name      ON refs(name);
CREATE INDEX idx_refs_file      ON refs(file_id);
CREATE INDEX idx_refs_target    ON refs(target_symbol_id);
```

### Column-by-column against ADR-002

| Column | Why ADR-002 needs it |
|---|---|
| `refs.start_byte` + `end_byte` | Exact span to replace on a mechanical rename. |
| `symbols.name_start_byte/end_byte` | Rename the definition site itself, not only its uses. |
| `symbols.signature_hash` | Classify edit: same hash + different name → **rename** (free); different hash → **signature change** (model). |
| `symbols.parent_id` + `qualified_name` | Disambiguate `Foo::bar` from `Baz::bar`; structural matching across an edit (§4). |
| `refs.target_symbol_id` | Rename only the call sites that actually resolve to the renamed symbol (§5). |

## 3. Write path (per-file, transactional)

Re-indexing a file is **delete-then-insert in one transaction** so the graph
never reflects a half-parsed file:

```
BEGIN;
  UPDATE/INSERT files row for path (get file_id);
  DELETE FROM symbols WHERE file_id = ?;   -- refs cascade is per-file too
  DELETE FROM refs    WHERE file_id = ?;
  INSERT symbols (parent_id patched in a second pass once ids exist);
  INSERT refs;
COMMIT;
```

Parsing (tree-sitter `extract`) is pure and runs on the rayon pool; inserts are
serial on the owner thread (SQLite is single-writer). This is already how v0
works — only the column set changes.

## 4. Next Edit Prediction — edit classification (ADR-002)

This algorithm lives in a future `nextedit` module; the schema above exists to
serve it. When a sync reports file `F` modified:

1. Load `OLD` = symbols of `F` from the DB; compute `NEW` = freshly parsed defs.
2. **Match OLD↔NEW structurally** — by `(parent path excluding leaf, kind,
   sibling ordinal)`. We cannot match on name because the name is exactly what
   may have changed.
3. For each matched pair:
   - `old.name != new.name` **and** `old.signature_hash == new.signature_hash`
     → **RENAME**. Mechanical: `SELECT ... FROM refs WHERE target_symbol_id =
     old.id` (or by name in v1), replace each `[start_byte,end_byte)` with the
     new name. **Zero model tokens.**
   - `signature_hash` changed (name same or not) → **SIGNATURE_CHANGE**.
     Semantic: each call site is handed to the Apply model to generate a
     non-mechanical edit (e.g. supply a new argument with a sensible default).
4. Unmatched `NEW` = added, unmatched `OLD` = removed (no propagation).

The editor renders results nearest-cursor-first as "Tab to jump" targets.

## 5. Resolution & the safe-rename caveat (honest limitation)

**v1 ships with name-only call-site matching** (`refs.name = ?`). This is what
v0 does today and it is *good enough for prediction* but **not safe for blind
apply**: two unrelated `parse()` functions in different modules collide.

- `target_symbol_id` is **NULL in v1** and populated in **v2** by a resolution
  pass (scope + import resolution per language).
- Until v2, mechanical rename must be **confirmed per call site by the user**
  (the "Tab to jump" UX already implies this), and we must `log()` that matching
  was name-based, not resolved — **no silent over-matching**.

This is a deliberate staged risk, not an oversight.

## 6. ADR-001 logging — keep it off the query path

Context/accept-reject logging must **never** touch the retrieval or symbol
queries. Decision:

- **Capture at the editor** on user accept/reject of a completion or edit.
- **Send to core as a batched JSON-RPC *notification*** (`telemetry/completion`,
  no `id` → no response, fire-and-forget) every N events or T seconds.
- Core appends to an **append-only sink on a dedicated background thread** — a
  separate `telemetry.db` (or JSONL), never the symbol DB, never synchronously.

Event shape (provenance for the future fine-tuning flywheel):

```json
{
  "ts": 0,
  "task": "completion|nextedit|apply",
  "outcome": "accepted|rejected|partial",
  "model": "qwen-3b|sonnet-4-6|...",
  "latency_ms": 0,
  "prompt_token_estimate": 0,
  "context": { "included_snippets": [/* SnippetRef[] from ContextBuilder */] }
}
```

No code is generated from this until the data volume justifies fine-tuning
(ADR-001: defer, don't never).
