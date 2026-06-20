//! The [`Prompt`] object and its assembly.
//!
//! A prompt is **not a string**. It is a structured object whose sections are
//! assembled deterministically from five sources, each owned by a different layer
//! of the system:
//!
//! 1. **system** — who the model is (fixed per task class).
//! 2. **capability** — what kind of work the Capability Layer requested.
//! 3. **semantic context** — the budgeted code context the Semantic Engine built.
//! 4. **user request** — the task's natural-language goal.
//! 5. **metadata** — the execution facts (task id, route, policy) that travelled
//!    with the request.
//!
//! Keeping these as fields (not a pre-flattened string) means a provider can
//! render them however its API expects (system/user roles, a single FIM string,
//! a chat array) without the runtime guessing. [`Prompt::render`] is the one
//! canonical flattening, used by string-only providers and for inspection.

use serde::Serialize;

use crate::capability::Capability;
use crate::context::BuiltPrompt;
use crate::inference::{Endpoint, Model, Route, UserPolicy};
use crate::planner::PlanTask;

/// The system instruction for every model interaction. Deliberately a single
/// named constant so the runtime never scatters ad-hoc instruction strings.
const SYSTEM_PROMPT: &str = "\
You are the inference core of a deterministic code editor. \
You receive assembled code context and a request. \
Respond ONLY with the artifact the request asks for — no prose, no apology. \
For a code change, respond with a JSON object: \
{\"edits\":[{\"file\":\"<path>\",\"edits\":[{\"startByte\":N,\"endByte\":N,\"newText\":\"...\"}]}]}.";

/// The execution facts that travelled with the request. These are recorded on the
/// prompt so an interaction is fully self-describing for telemetry and replay.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct PromptMetadata {
    pub task_id: String,
    pub capability: &'static str,
    pub policy: UserPolicy,
    /// The model the selector chose. `None` means no model is needed for the task
    /// (a context-only or mechanical step) — such a prompt is never invoked.
    pub model: Option<Model>,
    pub endpoint: Endpoint,
}

/// A structured prompt: the five inputs the milestone calls for, kept apart so
/// each provider renders them in its own dialect.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Prompt {
    pub system: String,
    pub capability: String,
    pub semantic_context: String,
    pub user_request: String,
    pub metadata: PromptMetadata,
}

impl Prompt {
    /// The canonical flattening: a single string with labelled sections, stable
    /// across runs (no timestamps, no map iteration). String-only providers and
    /// inspection tooling use this; structured providers read the fields instead.
    pub fn render(&self) -> String {
        format!(
            "<|system|>\n{}\n<|capability|>\n{}\n<|context|>\n{}\n<|request|>\n{}\n<|respond|>\n",
            self.system, self.capability, self.semantic_context, self.user_request,
        )
    }
}

/// Assembles a [`Prompt`] from the pieces the Execution Runtime already holds for
/// a task. Pure: same task + same context + same route => same prompt.
pub struct PromptAssembler;

impl PromptAssembler {
    /// Build the prompt for `task`, folding in the context the Semantic Engine
    /// assembled (when any) and the route the selector resolved.
    pub fn assemble(
        task: &PlanTask,
        context: Option<&BuiltPrompt>,
        route: &Route,
        policy: UserPolicy,
    ) -> Prompt {
        let semantic_context = context
            .map(|p| p.text.clone())
            .unwrap_or_else(|| "// (no code context assembled)".to_string());

        Prompt {
            system: SYSTEM_PROMPT.to_string(),
            capability: capability_instruction(task.capability).to_string(),
            semantic_context,
            user_request: task.description.clone(),
            metadata: PromptMetadata {
                task_id: task.id.clone(),
                capability: task.capability.as_str(),
                policy,
                model: route.model,
                endpoint: route.endpoint,
            },
        }
    }
}

/// The capability-specific instruction block. Each is a fixed, auditable string;
/// the Capability Layer chose the capability, this only renders its intent.
fn capability_instruction(capability: Capability) -> &'static str {
    match capability {
        Capability::ReadCode => "Summarize the relevant code for the request.",
        Capability::AnalyzeCode => "Analyze the code and explain the issue the request describes.",
        Capability::ModifyCode => "Produce the minimal edit set that satisfies the request. \
            Return only the JSON edit object described in the system prompt.",
        Capability::VerifyCode => "Assess whether the change satisfies the request.",
        Capability::Report => "Write a concise human-facing report answering the request.",
    }
}
