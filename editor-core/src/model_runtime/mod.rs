//! Model Runtime — language models as first-class runtime components.
//!
//! ```text
//! Planner → Capability Layer → Execution Runtime → Model Runtime → LLM Provider
//! ```
//!
//! Everything above this layer is deterministic. The Model Runtime is the *only*
//! component that interacts with a language model, and it concentrates that
//! interaction into five separable concerns, one module each:
//!
//! * [`selection`] — which model, on which endpoint (wraps the inference router).
//! * [`prompt`] — assembling the structured [`Prompt`] (system + capability +
//!   semantic context + user request + execution metadata).
//! * [`invocation`] — driving the chosen [`provider`] to generate.
//! * [`provider`] — the common interface every model lives behind, plus streaming.
//! * [`validation`] — gating the model's output before any mutation.
//!
//! ## How it plugs in without changing the Execution Runtime
//!
//! The executor already owns one seam to "turn assembled context into concrete
//! edits": the [`EditProvider`] trait. The Model Runtime *is* the real
//! implementation of that seam. The executor is constructed exactly as before —
//! `Executor::with_options(engine, policy, &model_runtime, dry_run)` — so the
//! Planner, Capability Layer, Tool Registry, and Execution Runtime are untouched.
//! What used to be a `NoEdits` stub is now: select → assemble → invoke → stream →
//! validate, with the validated edits flowing back through the executor's existing
//! verifying `apply_fix` path.
//!
//! Determinism is preserved end to end: selection, assembly, and validation are
//! pure; the single nondeterministic input is the provider's own output, exactly
//! as the milestone requires.
//!
//! This milestone deliberately stops here: no reflection, no retry, no memory, no
//! multi-agent. A rejected or empty response yields no edits (the task is honestly
//! skipped) — it is never retried or fabricated.

pub mod invocation;
pub mod prompt;
pub mod provider;
pub mod selection;
pub mod validation;

use crate::context::BuiltPrompt;
use crate::execution::{EditProvider, FileEdits};
use crate::inference::{Route, UserPolicy};
use crate::planner::PlanTask;

use invocation::Invoker;
use prompt::{Prompt, PromptAssembler};
use provider::{ModelResponse, ProviderRegistry, TokenSink, NullSink};
use selection::ModelSelector;
use validation::{ResponseValidator, Validated};

/// The result of running the full Model Runtime pipeline for one task. Richer than
/// the `Option<Vec<FileEdits>>` the [`EditProvider`] seam returns, so callers that
/// want the prompt, the raw response, or the rejection reason can observe them.
pub struct ModelRun {
    /// The route the selector resolved (model + endpoint).
    pub route: Route,
    /// The assembled prompt, present whenever a model was selected.
    pub prompt: Option<Prompt>,
    /// The raw model response, present whenever a provider was invoked.
    pub response: Option<ModelResponse>,
    /// The validation outcome (the gate before any mutation).
    pub outcome: RunOutcome,
}

/// The terminal classification of a [`ModelRun`].
pub enum RunOutcome {
    /// No model is needed for this task (read/verify capability).
    NoModel,
    /// A model was selected but no provider serves it.
    ProviderUnavailable,
    /// The provider produced nothing (e.g. the default null provider).
    Empty,
    /// The response was present but failed validation; carries the reason.
    Rejected(String),
    /// Validated, structurally sound edits ready for the verifying apply path.
    Edits(Vec<FileEdits>),
}

/// The Model Runtime. Constructed per run with the active policy and the set of
/// providers; used as the executor's [`EditProvider`].
pub struct ModelRuntime {
    policy: UserPolicy,
    providers: ProviderRegistry,
}

impl ModelRuntime {
    /// A runtime with the default ([`ProviderRegistry::with_defaults`]) providers:
    /// wired end-to-end but producing no edits until a real provider is registered.
    pub fn new(policy: UserPolicy) -> Self {
        Self { policy, providers: ProviderRegistry::with_defaults() }
    }

    /// A runtime over a caller-supplied provider registry.
    pub fn with_providers(policy: UserPolicy, providers: ProviderRegistry) -> Self {
        Self { policy, providers }
    }

    /// The route this runtime would select for `task` — selection without invoking.
    pub fn select(&self, task: &PlanTask) -> Route {
        ModelSelector::select(task, self.policy)
    }

    /// Run the full pipeline for `task`, streaming any output to `sink`:
    /// select → assemble → invoke → validate. Pure except for the provider call.
    pub fn run(&self, task: &PlanTask, context: Option<&BuiltPrompt>, sink: &mut dyn TokenSink) -> ModelRun {
        let route = self.select(task);

        let Some(model) = route.model else {
            return ModelRun { route, prompt: None, response: None, outcome: RunOutcome::NoModel };
        };

        let prompt = PromptAssembler::assemble(task, context, &route, self.policy);

        let response = match Invoker::new(&self.providers).invoke(model, &prompt, sink) {
            Ok(r) => r,
            Err(_) => {
                return ModelRun {
                    route,
                    prompt: Some(prompt),
                    response: None,
                    outcome: RunOutcome::ProviderUnavailable,
                };
            }
        };

        // The gate: nothing the model produced reaches the workspace unvalidated.
        let outcome = match ResponseValidator::validate_edits(&response) {
            Validated::Edits(e) => RunOutcome::Edits(e),
            Validated::Empty => RunOutcome::Empty,
            Validated::Rejected(reason) => RunOutcome::Rejected(reason),
        };

        ModelRun { route, prompt: Some(prompt), response: Some(response), outcome }
    }
}

impl EditProvider for ModelRuntime {
    /// The seam the Execution Runtime calls. Runs the pipeline and hands back only
    /// validated edits; every other outcome (no model, no provider, empty,
    /// rejected) yields `None`, which the executor records as an honest skip.
    fn edits_for(&self, task: &PlanTask, context: Option<&BuiltPrompt>) -> Option<Vec<FileEdits>> {
        match self.run(task, context, &mut NullSink).outcome {
            RunOutcome::Edits(edits) => Some(edits),
            _ => None,
        }
    }
}
