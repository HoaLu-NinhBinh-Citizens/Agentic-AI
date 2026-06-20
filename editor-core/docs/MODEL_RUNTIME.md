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
| `selection`     | Which model, on which endpoint — wraps the ADR-003 inference router.   |
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

## How it plugs in without changing the Execution Runtime

The executor already owns the seam that turns assembled context into concrete
edits: the `EditProvider` trait. `ModelRuntime` *is* the real implementation of
that seam. The executor is constructed exactly as before —
`Executor::with_options(engine, policy, &model_runtime, dry_run)` — so the
Planner, Capability Layer, Tool Registry, and Execution Runtime are untouched.
What was a `NoEdits` stub is now: select → assemble → invoke → stream → validate,
with validated edits flowing back through the executor's verifying apply path.

## Scope

This milestone deliberately stops at the boundary above. No reflection, no retry,
no memory, no multi-agent behavior. See ADR-004.
