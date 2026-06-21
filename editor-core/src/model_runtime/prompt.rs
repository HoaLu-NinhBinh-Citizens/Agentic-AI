//! The [`Prompt`] object and its assembly.
//!
//! A prompt is **not a string**, and no longer a fixed set of fields. It is a
//! *composable tree* of [`PromptSection`]s. Each section has a stable
//! [`SectionKind`] and a render tag; sections may nest. Assembly today emits four
//! sections — system, capability, semantic context, user request — but the kind
//! set already names the seams the agent/memory milestones will fill
//! (`WorkspaceSummary`, `ExecutionState`, `ToolSpec`, `History`, `Scratchpad`,
//! `Memory`). Adding one of those later is pushing a section, not widening a
//! struct, so neither providers nor the runtime change shape.
//!
//! Keeping sections as a tree (not a pre-flattened string) means a provider can
//! render them however its API expects (system/user roles, a single FIM string,
//! a chat array) without the runtime guessing. [`Prompt::render`] is the one
//! canonical flattening, used by string-only providers and for inspection, and is
//! stable across runs (ordered `Vec`, no maps, no timestamps).
//!
//! Assembly takes only Model-Runtime DTOs ([`ModelTask`], [`PromptContext`]) — it
//! has no knowledge of planners, capabilities, or the context builder.

use serde::Serialize;

use crate::inference::{Endpoint, Model, Route, UserPolicy};

use super::dto::{ModelTask, PromptContext};

/// The system instruction for every model interaction. A single named constant so
/// the runtime never scatters ad-hoc instruction strings; `&'static` so it is not
/// re-allocated per prompt.
const SYSTEM_PROMPT: &str = "\
You are the inference core of a deterministic code editor. \
You receive assembled code context and a request. \
Respond ONLY with the artifact the request asks for — no prose, no apology. \
For a code change, respond with a JSON object: \
{\"edits\":[{\"file\":\"<path>\",\"edits\":[{\"startByte\":N,\"endByte\":N,\"newText\":\"...\"}]}]}.";

const NO_CONTEXT: &str = "// (no code context assembled)";

/// The kind of a [`PromptSection`]. A closed, ordered vocabulary: the four kinds
/// assembled today plus the documented seams later milestones populate. The kind
/// (not the tag) is the stable handle [`Prompt::section`] looks up.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum SectionKind {
    /// Who the model is (fixed per task class).
    System,
    /// The directive for the kind of work requested.
    Capability,
    /// A summary of the workspace as a whole (future seam).
    WorkspaceSummary,
    /// The budgeted code context the Semantic Engine built.
    SemanticContext,
    /// The execution state / plan progress so far (future seam).
    ExecutionState,
    /// Tool specifications available to the model (future agent seam).
    ToolSpec,
    /// Prior conversation turns (future memory/session seam).
    History,
    /// The model's own working notes (future agent seam).
    Scratchpad,
    /// Retrieved long-term memory (future memory seam).
    Memory,
    /// The user's natural-language goal for this task.
    UserRequest,
}

impl SectionKind {
    /// The render tag for this kind — the marker [`Prompt::render`] wraps the
    /// body in. Stable: the four shipping kinds keep the historical markers.
    pub fn tag(self) -> &'static str {
        match self {
            SectionKind::System => "system",
            SectionKind::Capability => "capability",
            SectionKind::WorkspaceSummary => "workspace",
            SectionKind::SemanticContext => "context",
            SectionKind::ExecutionState => "execution",
            SectionKind::ToolSpec => "tools",
            SectionKind::History => "history",
            SectionKind::Scratchpad => "scratchpad",
            SectionKind::Memory => "memory",
            SectionKind::UserRequest => "request",
        }
    }
}

/// The execution facts that travelled with the request. Recorded on the prompt so
/// an interaction is fully self-describing for telemetry and replay.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct PromptMetadata {
    pub task_id: String,
    pub capability: String,
    pub policy: UserPolicy,
    /// The model the selector chose. `None` means no model is needed for the task
    /// (a context-only or mechanical step) — such a prompt is never invoked.
    pub model: Option<Model>,
    pub endpoint: Endpoint,
}

/// One node of the prompt tree: a tagged body plus any nested sections. Children
/// render after the parent's body, depth-first.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct PromptSection {
    pub kind: SectionKind,
    pub body: String,
    pub children: Vec<PromptSection>,
}

impl PromptSection {
    /// A leaf section (no children).
    pub fn leaf(kind: SectionKind, body: impl Into<String>) -> Self {
        Self { kind, body: body.into(), children: Vec::new() }
    }

    /// This section's render tag.
    pub fn tag(&self) -> &'static str {
        self.kind.tag()
    }

    fn render_into(&self, out: &mut String) {
        out.push_str(&format!("<|{}|>\n{}\n", self.tag(), self.body));
        for child in &self.children {
            child.render_into(out);
        }
    }
}

/// A structured prompt: an ordered tree of [`PromptSection`]s plus the execution
/// metadata that produced it. Each provider renders the sections in its own
/// dialect; string-only providers use [`render`](Prompt::render).
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Prompt {
    pub sections: Vec<PromptSection>,
    pub metadata: PromptMetadata,
}

impl Prompt {
    /// The first top-level section of `kind`, if assembled. Callers read a section
    /// by its stable kind rather than a positional field.
    pub fn section(&self, kind: SectionKind) -> Option<&PromptSection> {
        self.sections.iter().find(|s| s.kind == kind)
    }

    /// The body of the first top-level section of `kind`, or `""` when absent.
    pub fn body(&self, kind: SectionKind) -> &str {
        self.section(kind).map(|s| s.body.as_str()).unwrap_or("")
    }

    /// The canonical flattening: a single string with labelled sections, stable
    /// across runs (no timestamps, no map iteration). String-only providers and
    /// inspection tooling use this; structured providers walk the sections instead.
    pub fn render(&self) -> String {
        let mut out = String::new();
        for section in &self.sections {
            section.render_into(&mut out);
        }
        out.push_str("<|respond|>\n");
        out
    }
}

/// Builds a [`Prompt`] by pushing sections in order. The order of `push` calls is
/// the render order, so assembly stays deterministic by construction.
pub struct PromptBuilder {
    sections: Vec<PromptSection>,
    metadata: PromptMetadata,
}

impl PromptBuilder {
    pub fn new(metadata: PromptMetadata) -> Self {
        Self { sections: Vec::new(), metadata }
    }

    /// Append a leaf section. Empty bodies are still recorded so a section's
    /// presence (e.g. "context was considered, none found") is observable.
    pub fn section(mut self, kind: SectionKind, body: impl Into<String>) -> Self {
        self.sections.push(PromptSection::leaf(kind, body));
        self
    }

    /// Append a fully-formed section (allowing nested children).
    pub fn push(mut self, section: PromptSection) -> Self {
        self.sections.push(section);
        self
    }

    pub fn build(self) -> Prompt {
        Prompt { sections: self.sections, metadata: self.metadata }
    }
}

/// Assembles a [`Prompt`] from the runtime's DTOs. Pure: same task + same context
/// + same route => same prompt.
pub struct PromptAssembler;

impl PromptAssembler {
    /// Build the prompt for `task`, folding in the context the Semantic Engine
    /// assembled (when any) and the route the selector resolved. The future seams
    /// (workspace summary, execution state, tools, history, scratchpad, memory)
    /// are simply additional [`PromptBuilder::section`] calls when those engines
    /// exist.
    pub fn assemble(
        task: &ModelTask,
        context: Option<&PromptContext>,
        route: &Route,
        policy: UserPolicy,
    ) -> Prompt {
        let semantic_context = match context {
            Some(c) => c.text.clone(),
            None => NO_CONTEXT.to_string(),
        };

        let metadata = PromptMetadata {
            task_id: task.id.clone(),
            capability: task.capability.clone(),
            policy,
            model: route.model,
            endpoint: route.endpoint,
        };

        PromptBuilder::new(metadata)
            .section(SectionKind::System, SYSTEM_PROMPT)
            .section(SectionKind::Capability, task.directive.clone())
            .section(SectionKind::SemanticContext, semantic_context)
            .section(SectionKind::UserRequest, task.request.clone())
            .build()
    }
}
