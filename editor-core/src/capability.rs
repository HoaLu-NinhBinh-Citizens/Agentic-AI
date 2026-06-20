//! Capability Layer: the deterministic bridge between the Planner and the Tool
//! Registry.
//!
//! The Planner no longer names concrete tools. It requests a [`Capability`] — an
//! *intent-level* unit of work (read code, analyze it, modify it, verify it,
//! report on it). This module is what turns a requested capability into concrete
//! [`Tool`](crate::execution::Tool) invocations against the **unchanged**
//! [`ToolRegistry`](crate::execution::ToolRegistry):
//!
//! ```text
//! Planner → Capability Layer → Tool Registry → Execution Runtime
//! ```
//!
//! A capability may orchestrate *one or more* registered tools (see
//! [`Capability::tool_kinds`]); [`CapabilityLayer::execute`] runs them in order
//! and merges their outputs into a single outcome the runtime consumes. Today
//! each capability maps to a single tool, but the seam is the point: new tools
//! (Git, Cargo, MCP, Docker, …) can be registered and folded into a capability
//! without the Planner ever changing.
//!
//! The layer is pure orchestration — no LLM reasoning, no retry, no reflection,
//! no memory, no state. Same capability + same task => same dispatch.

use serde::{Deserialize, Serialize};

use crate::execution::{TaskState, ToolCx, ToolOutcome, ToolRegistry};
use crate::planner::{PlanTask, TaskKind};

/// An intent-level unit of work the Planner requests. The Capability Layer
/// resolves it to concrete tool(s); the Planner stays ignorant of tool identity.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Capability {
    /// Gather the relevant code/context for the work.
    ReadCode,
    /// Understand or diagnose the located code (detectors + context).
    AnalyzeCode,
    /// Produce and apply a change set. The only mutating capability.
    ModifyCode,
    /// Run verification checks over the affected workspace.
    VerifyCode,
    /// Produce a human-facing answer (review notes / explanation).
    Report,
}

impl Capability {
    pub fn as_str(self) -> &'static str {
        match self {
            Capability::ReadCode => "read_code",
            Capability::AnalyzeCode => "analyze_code",
            Capability::ModifyCode => "modify_code",
            Capability::VerifyCode => "verify_code",
            Capability::Report => "report",
        }
    }

    /// Whether this capability changes source. Only [`ModifyCode`] mutates.
    ///
    /// [`ModifyCode`]: Capability::ModifyCode
    pub fn mutates(self) -> bool {
        matches!(self, Capability::ModifyCode)
    }

    /// The ordered tool kinds this capability orchestrates from the registry.
    /// Each capability maps to one tool today; the slice return type is the
    /// extension seam for capabilities that will compose several tools.
    pub fn tool_kinds(self) -> &'static [TaskKind] {
        match self {
            Capability::ReadCode => &[TaskKind::Locate],
            Capability::AnalyzeCode => &[TaskKind::Analyze],
            Capability::ModifyCode => &[TaskKind::Implement],
            Capability::VerifyCode => &[TaskKind::Verify],
            Capability::Report => &[TaskKind::Report],
        }
    }

    /// The representative tool kind for this capability — used by the runtime to
    /// resolve a model route and to label the recorded execution. It is the first
    /// tool the capability orchestrates.
    pub fn primary_kind(self) -> TaskKind {
        self.tool_kinds()[0]
    }

    /// Whether the runtime should gate this capability's outcome through the
    /// verification lifecycle (the `Verifying` state). Mutating and explicit
    /// verify capabilities do; read-only ones don't.
    pub fn runs_verification(self) -> bool {
        matches!(self, Capability::ModifyCode | Capability::VerifyCode)
    }
}

/// The deterministic orchestrator between the Planner's requested capabilities
/// and the concrete tools in the registry. Stateless: holds no per-run data, so
/// dispatch is pure.
pub struct CapabilityLayer;

impl CapabilityLayer {
    pub fn new() -> Self {
        CapabilityLayer
    }

    /// Resolve `capability` to its tool(s), run each against `registry`, and merge
    /// their outcomes into one. A capability whose tool is not registered yields a
    /// `Skipped` step (honest: nothing ran), never a fabricated success.
    pub fn execute(
        &self,
        capability: Capability,
        task: &PlanTask,
        cx: &mut ToolCx,
        registry: &ToolRegistry,
    ) -> ToolOutcome {
        let mut merged: Option<ToolOutcome> = None;
        for &kind in capability.tool_kinds() {
            let step = match registry.tool_for(kind) {
                Some(tool) => tool.run(task, cx),
                None => ToolOutcome::new(
                    TaskState::Skipped,
                    format!("no tool registered for {}", capability.as_str()),
                ),
            };
            merged = Some(match merged {
                None => step,
                Some(acc) => merge_outcomes(acc, step),
            });
        }
        // A capability always maps to at least one tool, so `merged` is always
        // `Some`; guard defensively rather than panic.
        merged.unwrap_or_else(|| ToolOutcome::new(TaskState::Skipped, "capability orchestrates no tools"))
    }
}

impl Default for CapabilityLayer {
    fn default() -> Self {
        Self::new()
    }
}

/// Fold one tool's outcome into the running orchestration outcome. For a
/// single-tool capability this returns the step verbatim; for multi-tool
/// capabilities it concatenates outputs and takes the most severe state.
fn merge_outcomes(mut acc: ToolOutcome, next: ToolOutcome) -> ToolOutcome {
    acc.state = if state_rank(next.state) >= state_rank(acc.state) { next.state } else { acc.state };
    acc.summary = match (acc.summary.is_empty(), next.summary.is_empty()) {
        (true, _) => next.summary,
        (false, true) => acc.summary,
        (false, false) => format!("{}; {}", acc.summary, next.summary),
    };
    acc.route = next.route.or(acc.route);
    acc.context = next.context.or(acc.context);
    acc.diagnostics.extend(next.diagnostics);
    acc.verification.extend(next.verification);
    acc.modified_files.extend(next.modified_files);
    acc.artifacts.extend(next.artifacts);
    acc
}

/// Severity ordering for merging multi-tool states: a failure dominates a skip,
/// which dominates a success. Higher rank wins.
fn state_rank(state: TaskState) -> u8 {
    match state {
        TaskState::Failed => 4,
        TaskState::Blocked => 3,
        TaskState::Skipped => 2,
        TaskState::Succeeded => 1,
        _ => 0,
    }
}
