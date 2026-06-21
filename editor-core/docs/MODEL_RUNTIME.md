# Model Runtime

The Model Runtime is the only component that interacts with a language model.
Everything above it is deterministic; the model's own output is the single point
of nondeterminism in the system.

```text
Planner → Capability Layer → Execution Runtime → Model Runtime → LLM Provider
```

## Why a runtime, not a service call

Earlier milestones treated "call the model" as a stub seam (`NoEdits`) reached
from the executor. That is fine until models become first-class: once selection,
prompting, streaming, and validation all matter, scattering them across the
executor couples deterministic orchestration to nondeterministic inference. The
Model Runtime concentrates every model concern in one layer with one
responsibility each.

## The five concerns (one module each)

| Module          | Responsibility                                                        |
| --------------- | --------------------------------------------------------------------- |
| `dto`           | Neutral DTOs (`ModelTask`, `PromptContext`, `ModelEdit`) the runtime speaks in. |
| `selection`     | Which model, on which endpoint — the single caller of the ADR-003 router. |
| `prompt`        | Assembles the structured `Prompt` object (not a string).              |
| `provider`      | The common `ModelProvider` interface + token streaming.              |
| `invocation`    | Resolves model → provider and drives one generation.                 |
| `validation`    | Gates the model's output before any mutation reaches the workspace.   |

## The Prompt object

A prompt is **not a string**. It is a structured object combining five inputs,
each owned by a different layer, kept apart so a provider renders them in its own
dialect (system/user roles, a FIM string, a chat array):

1. **system** — who the model is.
2. **capability** — what the Capability Layer requested.
3. **semantic context** — the budgeted code context the Semantic Engine built.
4. **user request** — the task's natural-language goal.
5. **metadata** — execution facts (task id, capability, policy, model, endpoint).

`Prompt::render()` is the one canonical flattening, for string-only providers and
inspection.

## Providers behind one interface

Every model — local Qwen, cloud Haiku/Sonnet, a future backend — implements
`ModelProvider`. The `ProviderRegistry` resolves a selected `Model` to a concrete
provider; adding a provider is registering one more `Box<dyn ModelProvider>`. The
default registry holds a single `NullProvider` that serves every model but emits
nothing — the runtime is wired end-to-end yet produces no edits until a real
provider is registered (the honest analogue of the executor's old `NoEdits`).

Output streams token-by-token through a `TokenSink`; the full text is also
returned, so a non-streaming caller passes `NullSink`. A provider must guarantee
the streamed chunks concatenate to the returned text.

## Validation is the gate

The model's output is the one untrusted input. For a mutating capability the
model must return the edit JSON the system prompt specifies; `ResponseValidator`
parses it, rejects anything malformed, empty, **or truncated** (a length-capped
response could end in a partial-but-plausible edit), and only then yields
`FileEdits`. This is the *first* of two gates — the Execution Runtime's
`apply_fix` path then re-checks bounds and the detector diff. A rejected response
yields no edits; the task is honestly skipped, never retried or fabricated.

## Dependency direction & the `ModelBackend` port

The Model Runtime depends on nothing above it. It speaks only in its own neutral
DTOs and exposes one port, `ModelBackend`:

```rust
trait ModelBackend {
    fn generate_edits(&self, task: &ModelTask, ctx: Option<&PromptContext>) -> Option<Vec<ModelEdit>>;
    fn route_for(&self, task: &ModelTask, policy: UserPolicy) -> Route { ModelSelector::select(task, policy) }
}
```

The **Execution Runtime depends on the Model Runtime** (correct direction): it
adapts its `PlanTask`/`BuiltPrompt` *into* `ModelTask`/`PromptContext`, calls the
port, and adapts `ModelEdit`s *back* into its own apply type (`execution::model_task`,
`execution::prompt_context`, `execution::to_engine_edits`). The runtime never
imports a planner, capability, or execution type — only `inference`, the
foundational router it integrates.

## Routing lives in one place

`Capability::inference_task()` is the **single** mapping from intent to the
router's vocabulary; `ModelSelector::select` is the **single** caller of
`inference::plan`. The executor no longer routes — it asks `model.route_for(...)`.
So "which model" is decided exactly once and cannot drift.

## Wired into production

`IndexEngine::execute_plan` constructs a real `ModelRuntime` (default
`NullProvider`) and runs the executor against it via `Executor::with_backend`. The
live JSON-RPC `plan/execute` path therefore flows through the Model Runtime today;
registering a real provider is the only remaining step to produce edits.

## Scope

This milestone deliberately stops at the boundary above. No reflection, no retry,
no memory, no multi-agent behavior. See ADR-004.
