# Design — ContextBuilder

Status: **Design** (paper). Signatures only, no implementation.

> **Thesis (where the engineering money goes):** Qwen-3B with *well-constructed*
> context beats Qwen-7B with poor context. The model is a commodity; the prompt
> is the product. `ContextBuilder` is the single place that decides what the
> model sees.

## 1. Responsibility

Take `(file, cursor, optional query)` and return a **complete, budgeted prompt**
— FIM for completion, chat-format for chat — plus the **provenance** of what was
included (feeds the ADR-001 log).

It is the only component that talks to retrieval + symbol graph for the purpose
of prompt assembly. The inference router never assembles context itself.

## 2. Types (Rust)

```rust
/// What we're building context for. Drives layout and budget.
pub enum Task {
    Completion,   // FIM, tight budget, latency-critical
    NextEdit,     // edit-site context for a propagated change
    Chat,         // free-form Q&A, larger budget, has a query
}

pub struct BuildRequest<'a> {
    pub task: Task,
    pub file: &'a str,        // workspace-relative
    pub cursor_byte: usize,   // byte offset of the caret
    pub query: Option<&'a str>, // Chat only; None for Completion/NextEdit
    pub max_tokens: usize,    // hard budget for the whole prompt
}

/// How close a retrieved snippet is to the cursor — the ORDERING key, not RRF.
pub enum Proximity {
    SameFile { byte_distance: usize }, // nearest of all
    SameModule,                        // sibling files / same dir
    CrossModule,                       // elsewhere in the repo
}

/// A candidate snippet from hybrid retrieval (vector ⊕ lexical, fused by RRF).
pub struct RetrievedSnippet {
    pub file: String,
    pub start_row: usize,
    pub text: String,
    pub rrf_score: f32,       // used ONLY to SELECT candidates, not to ORDER them
    pub proximity: Proximity, // used to ORDER and to place in the prompt
}

/// A symbol definition pulled in because it's referenced near the cursor.
pub struct RelevantDef {
    pub qualified_name: String,
    pub signature: String,
    pub body: String,
    pub proximity: Proximity,
}

/// Provenance of one included item — logged verbatim for ADR-001.
pub struct SnippetRef {
    pub file: String,
    pub start_row: usize,
    pub kind: &'static str,   // "retrieved" | "definition" | "local"
}

/// The finished prompt handed to the inference router.
pub struct BuiltPrompt {
    pub text: String,
    pub token_estimate: usize,
    pub included: Vec<SnippetRef>, // what made the cut → ADR-001 log
    pub dropped: usize,            // budget-truncated count — NEVER silent (log it)
}

pub trait ContextBuilder {
    /// Assemble a budgeted prompt. Pure w.r.t. the index (reads only).
    fn build(&self, req: &BuildRequest) -> anyhow::Result<BuiltPrompt>;
}
```

## 3. Assembly algorithm (the important part)

### 3.1 Select vs order — two different keys

- **Select** candidates by `rrf_score` (best hybrid-retrieval hits).
- **Order** the selected candidates by `proximity`, **not** by score.

> **Rule (per your direction):** snippets are placed so the one *nearest the
> cursor* sits *nearest the FIM middle*. The model attends most strongly to
> tokens adjacent to the insertion point; the most relevant context must live
> there, not at the top of the prompt where it's diluted ("lost in the middle").

### 3.2 FIM layout for `Task::Completion`

```
┌─ prefix region ──────────────────────────────────────────────┐
│ // context (farthest → nearest), as comments:                 │
│   [CrossModule snippets]        ← least relevant, top          │
│   [SameModule snippets]                                        │
│   [RelevantDef bodies]                                         │
│   [SameFile snippets, ascending byte_distance]                 │
│   ...local code immediately above the cursor (verbatim)...     │ ← nearest
├─ <fim_middle> (completion goes here) ─────────────────────────┤
│ ...local code immediately below the cursor (verbatim)...      │
└─ suffix region ───────────────────────────────────────────────┘
```

Wire tokens are model-specific (`<|fim_prefix|>…<|fim_suffix|>…<|fim_middle|>`
for Qwen-Coder). Retrieved context rides inside the prefix as a comment header,
ordered far→near so the nearest snippet abuts the verbatim local prefix.

### 3.3 Budget packing

1. Reserve a fixed slice of `max_tokens` for the **local prefix/suffix** (these
   are non-negotiable — the model needs the immediate code).
2. Fill the remainder greedily with ordered items (defs + snippets), nearest
   first so the closest context survives truncation.
3. Whatever doesn't fit increments `dropped`. **`dropped > 0` is logged**, never
   hidden — silent truncation reads as "we gave the model everything" when we
   didn't.

### 3.4 Chat layout for `Task::Chat`

Standard system + context + history + user `query`. Same select/order split;
proximity matters less, so ordering falls back to `rrf_score` when the request
has no meaningful cursor (e.g. a repo-wide question).

## 4. What ContextBuilder does NOT do

- Does not pick the model or endpoint (that's Policy Layer + Router).
- Does not call the model.
- Does not write telemetry (it only *returns* `included`/`dropped`; the editor
  emits the log on accept/reject).
