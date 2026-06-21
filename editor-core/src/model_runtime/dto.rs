//! Neutral data-transfer objects owned by the Model Runtime.
//!
//! These types are the runtime's *inbound and outbound vocabulary*. They are
//! defined here, in the lowest layer, so the dependency arrow points the right
//! way: upper layers (the Execution Runtime) adapt their richer types
//! (`PlanTask`, `BuiltPrompt`, `FileEdits`) *into* and *out of* these DTOs. The
//! Model Runtime therefore depends on nothing above it — only on [`inference`],
//! the foundational router it integrates.
//!
//! [`inference`]: crate::inference

use serde::Deserialize;

use crate::inference::Task as InfTask;

/// What kind of artifact the caller expects back from an invocation. This is the
/// neutral vocabulary that lets one generic `run` serve many capabilities: it
/// selects which validation pipeline gates the response and which
/// [`ModelOutcome`](super::ModelOutcome) variant carries the result. The
/// capability owns the mapping (e.g. `ModifyCode → Edits`, `Report → Text`).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum OutputExpectation {
    /// A structured edit set, validated against the edit schema before any apply.
    Edits,
    /// Free-form text (explain / review / report / plan). Validated only for
    /// completeness — never applied to the workspace.
    Text,
    /// Structured tool calls (future agent capability). No provider emits these
    /// yet; the variant exists so the surface is total.
    ToolCalls,
}

/// The minimal, layer-neutral description of one unit of work the Model Runtime
/// acts on. The Execution Runtime builds this from its `PlanTask`; the runtime
/// never sees a planner or capability type.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ModelTask {
    /// Stable id, carried through to telemetry / metadata.
    pub id: String,
    /// A label for the capability that produced this task (e.g. `"modify_code"`),
    /// used only for metadata — the runtime makes no decision from it.
    pub capability: String,
    /// The capability-specific instruction for the model (intent wording).
    pub directive: String,
    /// The user's natural-language goal for this task.
    pub request: String,
    /// The routing input: which inference task this is, or `None` when no model is
    /// needed. This is the *only* field selection reads.
    pub inference_task: Option<InfTask>,
    /// The artifact the caller expects, which selects the validation pipeline. The
    /// capability sets this at the Execution Runtime boundary.
    pub expectation: OutputExpectation,
}

/// Budgeted code context for prompt assembly, neutral over how it was built
/// (semantic, retrieval, hybrid). Adapted from the Semantic Engine's `BuiltPrompt`
/// at the Execution Runtime boundary.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PromptContext {
    pub text: String,
    /// How the context was sourced (`"semantic"` / `"retrieval"` / `"hybrid"`).
    pub mode: String,
}

/// One file's worth of edits the model proposes. The Execution Runtime adapts this
/// to its own apply type before touching disk — the runtime produces edits, it
/// never applies them.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ModelEdit {
    pub file: String,
    pub spans: Vec<EditSpan>,
}

/// Replace the byte range `[start_byte, end_byte)` with `new_text`. Mirrors the
/// editor's on-the-wire edit shape (`camelCase`) so a model response deserializes
/// directly, but is a Model-Runtime-owned type — not the index engine's `Edit`.
#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct EditSpan {
    pub start_byte: usize,
    pub end_byte: usize,
    pub new_text: String,
}
