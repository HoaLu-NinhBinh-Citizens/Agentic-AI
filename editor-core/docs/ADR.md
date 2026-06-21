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

---

## ADR-004 — The Model Runtime: LLMs as first-class runtime components

**Status:** Accepted · **Context date:** 2026-06-20

### Context
Through ADR-003 the model call was a stub seam (`NoEdits`) reached from the
executor. That couples deterministic orchestration to nondeterministic inference
the moment model concerns (selection, prompting, streaming, validation) start to
matter. A model is not just an external service to call — it is a runtime
component with a lifecycle.

### Decision
- Introduce a **Model Runtime** as the only component that interacts with a
  language model:
  `Planner → Capability Layer → Execution Runtime → Model Runtime → LLM Provider`.
- Split the five concerns into one module each: **selection** (wraps the ADR-003
  router), **prompt** assembly, **provider** interface + streaming, **invocation**,
  and **validation**.
- A prompt is a structured **`Prompt` object**, not a string — system + capability
  + semantic context + user request + execution metadata, rendered per provider.
- Multiple providers live behind one `ModelProvider` trait, resolved by a
  `ProviderRegistry`. The default `NullProvider` keeps the runtime wired but
  edit-free until a real backend is registered.
- **Validation gates every mutation**: malformed, empty, or truncated output is
  rejected before any edit reaches the workspace. The executor's `apply_fix` diff
  is the second gate.
- **Dependency direction is inverted via neutral DTOs.** The Model Runtime owns
  `ModelTask`, `PromptContext`, `ModelEdit` and exposes one port, `ModelBackend`.
  The Execution Runtime depends on the Model Runtime (not the reverse), adapting
  its types at the boundary. The runtime imports only `inference`.
- **Routing has a single source.** `Capability::inference_task()` is the one
  intent→task mapping; `ModelSelector::select` is the one caller of
  `inference::plan`. The executor asks `ModelBackend::route_for`; it no longer
  routes.
- **Wired into production.** `execute_plan` runs through a real `ModelRuntime`
  (default `NullProvider`), so the live `plan/execute` path flows through the
  Model Runtime.

### Consequences
- (+) Every model concern lives in one auditable layer with one responsibility each.
- (+) Determinism holds end to end; the provider's output is the only variable.
- (+) New providers are additive — one `Box<dyn ModelProvider>`, no runtime change.
- (+) Untrusted model output cannot mutate the workspace unvalidated.
- (+) The layering arrow points down only; the runtime has no upward imports.
- (−) The Execution Runtime now depends on the Model Runtime's DTOs/port — a
  deliberate, correct coupling that replaced the old in-`execution` `EditProvider`.
- (−) New *models* (not providers) still require touching the closed
  `inference::Model` enum + router — a known limit, not addressed here.
- (−) No reflection/retry/memory/multi-agent yet — a rejected response is skipped,
  not recovered. Deliberate: those are later milestones.
