# Architecture Decision Records

The three decisions that shape the product. Each is **Accepted** (2026-06-16).

---

## ADR-001 — No self-hosted fine-tuning early; build the data flywheel instead

**Status:** Accepted · **Context date:** 2026-06-16

### Context
Self-hosting a fine-tuned completion model (the original Phase 3) is expensive
(GPU infra, training data, MLOps) and has low ROI *now* because we have no
proprietary training signal. Off-the-shelf Qwen2.5-Coder is already strong.

### Decision
- Use **off-the-shelf Qwen2.5-Coder** for completion. Spend engineering on
  **context construction** (see ADR + `CONTEXT_BUILDER.md`), not training.
- **Log accept/reject + the exact context used** from day one, captured at the
  editor and shipped to core as **batched notifications** — never on the query
  path (`SYMBOL_GRAPH_SPEC.md` §6).
- Revisit fine-tuning only when usage data volume makes ROI positive — **defer,
  not never**.

### Consequences
- (+) No GPU/MLOps cost early; faster path to a working product.
- (+) The flywheel data is accumulating, so fine-tuning is unblocked later.
- (−) We're bounded by the base model's quality until then — mitigated by
  context engineering being the larger lever at this stage.

---

## ADR-002 — Next Edit Prediction is built on the symbol graph (cheap SQL + selective model)

**Status:** Accepted · **Context date:** 2026-06-16

### Context
Cursor's "magic" is predicting the *next* edit after the user changes something
(e.g. rename a function → update its call sites). Doing this with the model on
every site is slow and expensive.

### Decision
Two layers:
1. **Where to edit** = cheap SQL over the symbol graph (`call_sites(name)` /
   `target_symbol_id`). Instant, free.
2. **What to edit**:
   - **Mechanical rename** (name changed, `signature_hash` unchanged) → byte-span
     replace at each ref. **Zero model tokens.**
   - **Semantic change** (`signature_hash` flipped) → the Apply model generates a
     non-mechanical edit per site.

The schema exists to serve this: `signature_hash`, exact `start/end_byte` on
refs, `name_start/end_byte` on defs, `parent_id`/`qualified_name` for structural
edit-matching. See `SYMBOL_GRAPH_SPEC.md` §4.

### Consequences
- (+) Most propagations (pure renames) cost nothing and feel instant.
- (+) Model spend is reserved for genuinely non-mechanical edits.
- (−) Safe *blind* rename needs `target_symbol_id` resolution (v2); v1 matches by
  name and must confirm per site — a deliberate staged risk, logged, not silent.

---

## ADR-003 — Privacy is legal, not a location; Policy Layer is separate from the Router

**Status:** Accepted · **Context date:** 2026-06-16

### Context
Equating "privacy mode" with "local model" is a trap: a power user on a 1M-LOC
repo forced onto a local 3B model gets bad answers and blames the tool. Most
regulated buyers want *contractual* guarantees (BAA, zero data retention), not a
weaker local model.

### Decision
- Three tiers: **air_gap** → Local; **compliance** → Cloud ZDR (BAA signed);
  **cloud** → Cloud Standard.
- A **Policy Layer** maps `user_policy → Endpoint`. A separate **Inference
  Router** maps `(task, Endpoint) → (Model, Endpoint)`. The router can never
  override policy because it only sees the already-collapsed endpoint.
- Completion is **always local** (latency), independent of tier. Local model is
  only the *fallback for chat/apply* under `air_gap`. See `POLICY_LAYER.md`.

### Consequences
- (+) Policy changes (sign a BAA, toggle air-gap) are one auditable function.
- (+) Most enterprises get frontier-model quality *and* a compliance story.
- (+) Both layers are pure lookup tables → unit-testable offline.
- (−) Air-gap users accept lower chat quality (local 7B) — acceptable for a
  niche (defense/classified) market.
