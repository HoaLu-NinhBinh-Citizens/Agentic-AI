//! Model Runtime — language models as first-class runtime components.
//!
//! ```text
//! Planner → Capability Layer → Execution Runtime → Model Runtime → LLM Provider
//! ```
//!
//! Everything above this layer is deterministic. The Model Runtime is the *only*
//! component that interacts with a language model, and it concentrates that
//! interaction into separable concerns, one module each:
//!
//! * [`selection`] — which model, on which endpoint (the single route decision).
//! * [`prompt`] — assembling the composable [`Prompt`](prompt::Prompt) tree.
//! * [`provider`] — the common interface every model lives behind, the streaming
//!   sink, and the [`ProviderManager`](provider::ProviderManager) (selection,
//!   retry, circuit-breaking).
//! * [`validation`] — the layered validators gating output before any mutation.
//! * [`session`] — the [`ModelSession`](session::ModelSession) →
//!   [`Conversation`](session::Conversation) → invocation abstraction (no memory
//!   or multi-agent behavior yet).
//!
//! ## One generic invocation
//!
//! The port is [`ModelBackend::run`]: it takes a neutral [`ModelRequest`] and
//! returns a [`ModelResult`] whose [`ModelOutcome`] carries whatever the task's
//! [`OutputExpectation`] asked for — `Edits`, free-form `Text` (explain / review /
//! report / plan), or (later) `ToolCalls`. The runtime is no longer edit-centric;
//! one path serves every capability.
//!
//! ## Dependency direction
//!
//! This layer depends on nothing above it. It speaks in its own neutral
//! [`dto`]s — [`ModelTask`], [`PromptContext`], [`ModelEdit`]. The Execution
//! Runtime depends on *this* module: it adapts its `PlanTask`/`BuiltPrompt` into
//! the DTOs, calls the port, and adapts [`ModelEdit`]s back. The only thing the
//! runtime shares with the rest of the system is [`inference`](crate::inference) —
//! the foundational router (ADR-003), a peer, not an upper layer.
//!
//! ## Determinism
//!
//! Selection, assembly, and validation are pure; the single nondeterministic input
//! is the provider's own output. Retries are immediate (no wall-clock backoff). A
//! rejected or empty response yields no edits (the task is honestly skipped) —
//! never retried into a fabrication. No reflection, retry-into-replan, memory, or
//! multi-agent behavior yet.

pub mod dto;
pub mod prompt;
pub mod provider;
pub mod selection;
pub mod session;
pub mod validation;

use crate::inference::{Endpoint, Route, UserPolicy};

use dto::{ModelEdit, ModelTask, PromptContext};
use prompt::{Prompt, PromptAssembler};
use provider::{ModelResponse, NullSink, ProviderManager, TokenSink};
use selection::ModelSelector;
use validation::{ResponseValidator, Validated};

/// A structured tool call a model may request (future agent capability). Defined
/// so [`ModelOutcome`] is total; no provider emits these yet.
#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize)]
pub struct ToolCall {
    pub name: String,
    pub arguments: serde_json::Value,
}

/// The neutral, high-level invocation request the runtime port accepts. Bundles
/// the unit of work and its assembled context; the *expectation* (what artifact to
/// return and validate) lives on [`ModelTask::expectation`], set by the capability.
pub struct ModelRequest<'a> {
    pub task: &'a ModelTask,
    pub context: Option<&'a PromptContext>,
}

impl<'a> ModelRequest<'a> {
    pub fn new(task: &'a ModelTask, context: Option<&'a PromptContext>) -> Self {
        Self { task, context }
    }
}

/// The terminal classification of a [`ModelResult`] — the gate before any
/// mutation, generalized over every output kind.
#[derive(Debug, Clone)]
pub enum ModelOutcome {
    /// No model is needed for this task (read/verify capability).
    NoModel,
    /// A model was selected but no provider serves it (or the circuit is open).
    ProviderUnavailable,
    /// The provider produced nothing usable (e.g. the default null provider).
    Empty,
    /// The response was present but failed validation; carries the reason.
    Rejected(String),
    /// Validated, structurally sound edits ready for the verifying apply path.
    Edits(Vec<ModelEdit>),
    /// Validated free-form text (explain / review / report / plan).
    Text(String),
    /// Validated tool calls (future agent capability; not produced yet).
    ToolCalls(Vec<ToolCall>),
}

/// The result of running the full Model Runtime pipeline for one request. Richer
/// than the outcome alone, so callers that want the prompt or the raw response
/// (telemetry, replay, the future Reflection engine) can observe them.
pub struct ModelResult {
    /// The route the selector resolved (model + endpoint).
    pub route: Route,
    /// The assembled prompt, present whenever a model was selected.
    pub prompt: Option<Prompt>,
    /// The raw model response, present whenever a provider was invoked.
    pub response: Option<ModelResponse>,
    /// The terminal classification.
    pub outcome: ModelOutcome,
}

/// The port the Execution Runtime drives. Implemented by [`ModelRuntime`]; the
/// runtime never imports an execution type, so the arrow points Execution →
/// Model Runtime, not the reverse.
pub trait ModelBackend {
    /// Run one invocation, streaming any output to `sink`.
    fn run(&self, req: &ModelRequest, sink: &mut dyn TokenSink) -> ModelResult;

    /// The route this task would use under `policy`. Defaulted to the single
    /// routing source so every backend (including test doubles) shares one
    /// decision and none can drift.
    fn route_for(&self, task: &ModelTask, policy: UserPolicy) -> Route {
        ModelSelector::select(task, policy)
    }

    /// Convenience for the mutating apply path: run the task (with `Edits`
    /// expectation set by the caller) and return validated edits, or `None` for
    /// every non-edit outcome (no model, unavailable, empty, rejected, or a
    /// non-edit artifact). Non-streaming.
    fn run_for_edits(
        &self,
        task: &ModelTask,
        context: Option<&PromptContext>,
    ) -> Option<Vec<ModelEdit>> {
        match self.run(&ModelRequest::new(task, context), &mut NullSink).outcome {
            ModelOutcome::Edits(edits) => Some(edits),
            _ => None,
        }
    }
}

/// The Model Runtime. Constructed per run with the active policy and a
/// [`ProviderManager`]; used as the executor's [`ModelBackend`].
pub struct ModelRuntime {
    policy: UserPolicy,
    providers: ProviderManager,
}

impl ModelRuntime {
    /// A runtime with the default ([`ProviderManager::with_defaults`]) providers:
    /// wired end-to-end but producing no edits until a real provider is registered.
    pub fn new(policy: UserPolicy) -> Self {
        Self { policy, providers: ProviderManager::with_defaults() }
    }

    /// A runtime over a caller-supplied provider registry (wrapped in a manager
    /// with default retry/breaker).
    pub fn with_providers(policy: UserPolicy, providers: provider::ProviderRegistry) -> Self {
        Self { policy, providers: ProviderManager::from_registry(providers) }
    }

    /// A runtime over a fully-configured [`ProviderManager`] (custom retry/breaker).
    pub fn with_manager(policy: UserPolicy, providers: ProviderManager) -> Self {
        Self { policy, providers }
    }

    /// The route this runtime would select for `task` — selection without invoking.
    pub fn select(&self, task: &ModelTask) -> Route {
        ModelSelector::select(task, self.policy)
    }

    /// Run the full pipeline for `req`, streaming any output to `sink`:
    /// select → assemble → invoke → validate. Pure except for the provider call.
    pub fn run(&self, req: &ModelRequest, sink: &mut dyn TokenSink) -> ModelResult {
        let task = req.task;
        let route = self.select(task);

        let Some(model) = route.model else {
            return ModelResult { route, prompt: None, response: None, outcome: ModelOutcome::NoModel };
        };

        let prompt = PromptAssembler::assemble(task, req.context, &route, self.policy);

        let response = match self.providers.invoke(model, route.endpoint, &prompt, sink) {
            Ok(r) => r,
            Err(_) => {
                return ModelResult {
                    route,
                    prompt: Some(prompt),
                    response: None,
                    outcome: ModelOutcome::ProviderUnavailable,
                };
            }
        };

        // The gate: nothing the model produced reaches the workspace unvalidated.
        let outcome = match ResponseValidator::validate(&response, task.expectation) {
            Validated::Edits(e) => ModelOutcome::Edits(e),
            Validated::Text(t) => ModelOutcome::Text(t),
            Validated::Empty => ModelOutcome::Empty,
            Validated::Rejected(reason) => ModelOutcome::Rejected(reason),
        };

        ModelResult { route, prompt: Some(prompt), response: Some(response), outcome }
    }
}

impl ModelBackend for ModelRuntime {
    fn run(&self, req: &ModelRequest, sink: &mut dyn TokenSink) -> ModelResult {
        ModelRuntime::run(self, req, sink)
    }
}

/// The honest default backend: needs no policy or providers and produces nothing.
/// Useful where a [`ModelBackend`] is required but no model should run (defaults,
/// tests). Routing still works via the trait's default [`ModelBackend::route_for`].
pub struct NullBackend;

impl ModelBackend for NullBackend {
    fn run(&self, _req: &ModelRequest, _sink: &mut dyn TokenSink) -> ModelResult {
        // No policy, so no route to resolve; Local is the neutral "nothing leaves
        // the machine" endpoint, and `model: None` honestly says nothing ran.
        ModelResult {
            route: Route { model: None, endpoint: Endpoint::Local },
            prompt: None,
            response: None,
            outcome: ModelOutcome::NoModel,
        }
    }
}

pub use dto::OutputExpectation as Expectation;
