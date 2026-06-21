//! Execution Runtime: consumes a [`Plan`] and runs it.
//!
//! The division of labor (mirrors the milestone's design goals):
//!
//! * **Planner** decides *what* to do — a deterministic [`Plan`] (intent + task
//!   DAG + schedule + per-task context/verification). It never executes.
//! * **Execution Engine** (this module) decides *how* — it walks the planner
//!   schedule wave by wave, drives each task through an explicit
//!   [state machine](TaskState), selects a model (inference router), assembles
//!   that task's own context (semantic context builder), dispatches the task's
//!   requested *capability* through the
//!   [`CapabilityLayer`](crate::capability::CapabilityLayer) — which resolves it
//!   to one or more pluggable [`Tool`]s in the [`ToolRegistry`] — records every output as a
//!   structured [`Artifact`] downstream tasks consume, and — for mutating tasks —
//!   runs verification before declaring success. Every transition is reported on
//!   an [`ExecutionEvent`] stream for observability.
//! * **Semantic Engine** supplies the minimal relevant context per task.
//! * **Verification** validates mutating results (detector diff today; compile /
//!   tests / regression are seams reported as `Skipped` until a runner exists).
//!
//! This milestone is deterministic: no retry, no reflection, no replanning, no
//! memory, no multi-agent. The one variation point — turning assembled context
//! into actual edits via the LLM — lives below this layer in the
//! [`Model Runtime`](crate::model_runtime), reached through its
//! [`ModelBackend`] port. Its default ([`NullBackend`], or a [`ModelRuntime`] with
//! no real provider) produces nothing, so a mutating task without a wired model is
//! reported `Skipped` (honestly, never fabricated).
//!
//! [`ModelRuntime`]: crate::model_runtime::ModelRuntime

use std::time::Instant;

use serde::Serialize;
use serde_json::{json, Value};

use crate::capability::CapabilityLayer;
use crate::context::{BuildRequest, BuiltPrompt, Task as CtxTask};
use crate::detector::Finding;
use crate::index::{Edit, IndexEngine};
use crate::inference::{Route, UserPolicy};
use crate::model_runtime::dto::{ModelEdit, ModelTask, OutputExpectation, PromptContext};
use crate::model_runtime::ModelBackend;
use crate::planner::{
    ContextPlan, Intent, Plan, PlanTask, TaskKind, VerificationCheck, VerificationKind,
};
use crate::semantic::FocusSpec;

// ───────────────────────────── Task state machine ──────────────────────────

/// Explicit lifecycle of a task. The runtime moves a task through these states
/// and reports every transition on the [event stream](ExecutionEvent). Only the
/// terminal four ever appear in a finished [`TaskExecution::state`].
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum TaskState {
    /// Created, not yet considered by the scheduler.
    Pending,
    /// Waiting on dependencies that have not all completed.
    Waiting,
    /// Dependencies satisfied; eligible to run.
    Ready,
    /// A tool is executing the task.
    Running,
    /// Mutating result is being checked by the verification pipeline.
    Verifying,
    /// Terminal: ran and met its criteria (including verification, if mutating).
    Succeeded,
    /// Terminal: ran but failed its criteria (e.g. verification regressed).
    Failed,
    /// Terminal: intentionally not completed — a mutating task with no edits
    /// (model seam not wired), or nothing to act on.
    Skipped,
    /// Terminal: not attempted because a dependency did not succeed.
    Blocked,
}

impl TaskState {
    pub fn is_terminal(self) -> bool {
        matches!(self, TaskState::Succeeded | TaskState::Failed | TaskState::Skipped | TaskState::Blocked)
    }

    /// Whether `self -> next` is a legal lifecycle transition. The runtime only
    /// ever performs legal transitions; this guards that invariant (a violation
    /// is a runtime bug, not recoverable state).
    pub fn can_transition_to(self, next: TaskState) -> bool {
        use TaskState::*;
        matches!(
            (self, next),
            (Pending, Waiting | Ready | Blocked | Skipped)
                | (Waiting, Ready | Blocked | Skipped)
                | (Ready, Running | Skipped)
                | (Running, Verifying | Succeeded | Failed | Skipped)
                | (Verifying, Succeeded | Failed)
        )
    }
}

// ──────────────────────── Model Runtime boundary adapters ───────────────────

/// Adapt a [`PlanTask`] into the Model Runtime's neutral [`ModelTask`]. This is
/// the one place planner/capability detail is translated into the runtime's
/// vocabulary; the runtime never sees a `PlanTask`. The capability owns both the
/// routing input ([`Capability::inference_task`]) and the model directive
/// ([`Capability::model_directive`]), so routing has a single source.
///
/// [`Capability::inference_task`]: crate::capability::Capability::inference_task
/// [`Capability::model_directive`]: crate::capability::Capability::model_directive
pub fn model_task(task: &PlanTask) -> ModelTask {
    let cap = task.capability;
    ModelTask {
        id: task.id.clone(),
        capability: cap.as_str().to_string(),
        directive: cap.model_directive().to_string(),
        request: task.description.clone(),
        inference_task: cap.inference_task(),
        // Only the mutating capability returns a structured edit set; every other
        // capability (analyze / report) produces free-form text.
        expectation: if cap.mutates() { OutputExpectation::Edits } else { OutputExpectation::Text },
    }
}

/// Adapt the Semantic Engine's [`BuiltPrompt`] into the runtime's neutral
/// [`PromptContext`].
pub fn prompt_context(prompt: &BuiltPrompt) -> PromptContext {
    PromptContext { text: prompt.text.clone(), mode: prompt.mode.to_string() }
}

/// Adapt a model-produced [`ModelEdit`] back into the index engine's [`Edit`]s for
/// the verifying [`IndexEngine::apply_fix`] path. The runtime produces edits; the
/// Execution Runtime applies them.
fn to_engine_edits(edit: &ModelEdit) -> Vec<Edit> {
    edit.spans
        .iter()
        .map(|s| Edit { start_byte: s.start_byte, end_byte: s.end_byte, new_text: s.new_text.clone() })
        .collect()
}

// ───────────────────────────── Verification types ──────────────────────────

/// Result of one verification check.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum CheckStatus {
    Passed,
    Failed,
    /// No runner integrated for this check yet (compile / tests / regression).
    Skipped,
}

/// One verification check's outcome.
#[derive(Debug, Clone, Serialize)]
pub struct CheckResult {
    pub kind: VerificationKind,
    pub status: CheckStatus,
    pub detail: String,
}

// ───────────────────────────── Artifact system ─────────────────────────────

/// The class of a structured output. Lets a downstream task find the upstream
/// artifacts it cares about (e.g. the verify task reads [`ModifiedFiles`]).
///
/// [`ModifiedFiles`]: ArtifactKind::ModifiedFiles
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ArtifactKind {
    /// A summary of the context assembled for a task.
    Context,
    /// The prompt + route a model would turn into edits.
    EditRequest,
    /// Detector findings.
    Diagnostics,
    /// Files a mutating task touched.
    ModifiedFiles,
    /// Verification check results.
    Verification,
    /// A human-facing report.
    Report,
}

/// A structured output produced by a task and consumed by downstream tasks. The
/// `data` is a JSON value so artifacts are uniform, serializable, and inspectable
/// without the runtime knowing every producer's shape.
#[derive(Debug, Clone, Serialize)]
pub struct Artifact {
    /// Id of the task that produced it.
    pub producer: String,
    pub kind: ArtifactKind,
    /// Stable, human-readable name (e.g. `"edit_request"`, `"report"`).
    pub name: String,
    pub data: Value,
}

impl Artifact {
    fn new(producer: &str, kind: ArtifactKind, name: &str, data: Value) -> Self {
        Self { producer: producer.to_string(), kind, name: name.to_string(), data }
    }
}

/// All artifacts produced so far in a run. Tasks read upstream artifacts from it;
/// the runtime appends each task's outputs after the task finishes, so a task
/// only ever sees artifacts from tasks that completed before it (deterministic).
#[derive(Debug, Clone, Default, Serialize)]
pub struct ArtifactStore {
    items: Vec<Artifact>,
}

impl ArtifactStore {
    fn add(&mut self, a: Artifact) {
        self.items.push(a);
    }

    /// Every artifact, in production order.
    pub fn all(&self) -> &[Artifact] {
        &self.items
    }

    /// Artifacts of a given kind, in production order.
    pub fn by_kind(&self, kind: ArtifactKind) -> impl Iterator<Item = &Artifact> {
        self.items.iter().filter(move |a| a.kind == kind)
    }
}

// ───────────────────────────── Event stream ────────────────────────────────

/// An observability event. Deterministic: ordered by an integer `seq` (see
/// [`EmittedEvent`]) rather than wall-clock time.
#[derive(Debug, Clone, Serialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum ExecutionEvent {
    PlanStarted { goal: String, intent: Intent, tasks: usize, waves: usize },
    TaskStateChanged { task: String, from: TaskState, to: TaskState },
    TaskStarted { task: String, kind: TaskKind },
    VerificationStarted { task: String, checks: usize },
    VerificationFinished { task: String, passed: usize, failed: usize, skipped: usize },
    ArtifactProduced { task: String, name: String, kind: ArtifactKind },
    TaskFinished { task: String, state: TaskState },
    PlanFinished { status: ExecutionStatus },
}

/// An event with its monotonic sequence number.
#[derive(Debug, Clone, Serialize)]
pub struct EmittedEvent {
    pub seq: usize,
    #[serde(flatten)]
    pub event: ExecutionEvent,
}

/// A live observer of the event stream (e.g. the editor streaming progress).
/// Pluggable; the runtime always records events into the [`ExecutionResult`]
/// regardless, so a sink is purely additive.
pub trait EventSink: Send {
    fn emit(&mut self, event: &EmittedEvent);
}

/// Records the event stream into a Vec and (optionally) forwards each event to a
/// live sink. Owns the sequence counter so ordering is total and deterministic.
struct EventLog {
    seq: usize,
    events: Vec<EmittedEvent>,
    live: Option<Box<dyn EventSink>>,
}

impl EventLog {
    fn new(live: Option<Box<dyn EventSink>>) -> Self {
        Self { seq: 0, events: Vec::new(), live }
    }

    fn emit(&mut self, event: ExecutionEvent) {
        let env = EmittedEvent { seq: self.seq, event };
        self.seq += 1;
        if let Some(sink) = self.live.as_mut() {
            sink.emit(&env);
        }
        self.events.push(env);
    }
}

// ───────────────────────────── Result types ────────────────────────────────

/// A lean summary of the context assembled for a task (the full prompt text, when
/// useful, is kept as an [`Artifact`] instead).
#[derive(Debug, Clone, Serialize)]
pub struct ContextSummary {
    pub mode: String,
    pub token_estimate: usize,
    /// Number of snippets included.
    pub included: usize,
    pub dropped: usize,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub focus: Option<FocusSpec>,
}

/// The record of executing one [`PlanTask`].
#[derive(Debug, Clone, Serialize)]
pub struct TaskExecution {
    pub id: String,
    pub kind: TaskKind,
    /// Terminal state reached.
    pub state: TaskState,
    pub summary: String,
    /// Model selection for this task (None = no model needed). Resolved here, at
    /// execution time — never during planning.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub route: Option<Route>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub context: Option<ContextSummary>,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub diagnostics: Vec<Finding>,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub verification: Vec<CheckResult>,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub modified_files: Vec<String>,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub artifacts: Vec<Artifact>,
    pub elapsed_ms: u128,
}

/// Overall execution verdict.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ExecutionStatus {
    /// Every task succeeded.
    Succeeded,
    /// No task failed, but at least one was skipped (e.g. edits not wired).
    Partial,
    /// At least one task failed or was blocked.
    Failed,
}

/// Run-level metadata.
#[derive(Debug, Clone, Serialize)]
pub struct ExecutionMetadata {
    pub policy: UserPolicy,
    pub waves: usize,
    pub tasks_total: usize,
    pub tasks_succeeded: usize,
    pub tasks_failed: usize,
    pub tasks_skipped: usize,
    pub tasks_blocked: usize,
    pub elapsed_ms: u128,
}

/// The structured result of executing a whole plan — the contract returned to
/// the editor (and, later, to the Reflection milestone).
#[derive(Debug, Clone, Serialize)]
pub struct ExecutionResult {
    pub goal: String,
    pub intent: Intent,
    pub status: ExecutionStatus,
    pub tasks: Vec<TaskExecution>,
    /// Every structured output produced, for downstream/inspection.
    pub artifacts: Vec<Artifact>,
    /// The full observability event stream, in order.
    pub events: Vec<EmittedEvent>,
    pub metadata: ExecutionMetadata,
}

// ───────────────────────────── Tool abstraction ────────────────────────────

/// Everything a [`Tool`] needs to do its work, reusing existing engine modules.
pub struct ToolCx<'a> {
    pub engine: &'a mut IndexEngine,
    pub policy: UserPolicy,
    pub model: &'a dyn ModelBackend,
    /// Apply edits to disk (`false`) or only compute + verify them (`true`).
    pub dry_run: bool,
    /// Artifacts produced by upstream tasks (read-only).
    pub upstream: &'a ArtifactStore,
}

impl<'a> ToolCx<'a> {
    /// Turn a task's [`ContextPlan`] into a [`BuildRequest`] and assemble its
    /// context via the existing semantic context builder. `None` when the plan
    /// has nothing to center on (a workspace-wide step with no files).
    fn assemble_context(&mut self, ctx: &ContextPlan) -> Option<anyhow::Result<BuiltPrompt>> {
        let (file, cursor_byte, focus_symbol) = match &ctx.focus {
            Some(FocusSpec::Symbol(s)) => (String::new(), 0usize, Some(s.clone())),
            Some(FocusSpec::Location { file, byte }) => (file.clone(), *byte, None),
            None => match ctx.files.first() {
                Some(f) => (f.clone(), 0usize, None),
                None => return None,
            },
        };
        let req = BuildRequest {
            task: CtxTask::Chat,
            file,
            cursor_byte,
            query: ctx.query.clone(),
            max_tokens: ctx.max_tokens,
            focus_symbol,
        };
        Some(self.engine.build_context(&req))
    }

    /// Detector findings over a task's relevant files (focus file + listed files).
    fn detectors(&self, ctx: &ContextPlan) -> Vec<Finding> {
        diagnose_files(self.engine, &relevant_files(ctx))
    }
}

/// A pluggable unit of work. The registry maps a [`TaskKind`] to a `Tool`; a
/// custom runtime can register its own without changing the executor.
pub trait Tool: Send + Sync {
    fn name(&self) -> &'static str;
    /// Run the task and return its outcome. The tool does not emit events or
    /// mutate the artifact store directly — the runtime does both from the
    /// returned [`ToolOutcome`], keeping lifecycle/observability in one place.
    fn run(&self, task: &PlanTask, cx: &mut ToolCx) -> ToolOutcome;
}

/// What a [`Tool`] produces. The runtime turns this into a [`TaskExecution`],
/// stores the artifacts, and emits the matching events.
pub struct ToolOutcome {
    pub state: TaskState,
    pub summary: String,
    pub route: Option<Route>,
    pub context: Option<ContextSummary>,
    pub diagnostics: Vec<Finding>,
    pub verification: Vec<CheckResult>,
    pub modified_files: Vec<String>,
    pub artifacts: Vec<Artifact>,
}

impl ToolOutcome {
    /// An outcome in `state` with a summary and no other fields set. Custom tools
    /// build on this and push artifacts / diagnostics / verification as needed.
    pub fn new(state: TaskState, summary: impl Into<String>) -> Self {
        Self {
            state,
            summary: summary.into(),
            route: None,
            context: None,
            diagnostics: Vec::new(),
            verification: Vec::new(),
            modified_files: Vec::new(),
            artifacts: Vec::new(),
        }
    }

    /// Convenience constructors for the common terminal states.
    pub fn succeeded(summary: impl Into<String>) -> Self {
        Self::new(TaskState::Succeeded, summary)
    }
    pub fn failed(summary: impl Into<String>) -> Self {
        Self::new(TaskState::Failed, summary)
    }
    pub fn skipped(summary: impl Into<String>) -> Self {
        Self::new(TaskState::Skipped, summary)
    }
}

/// Holds the active tools keyed by the task kind they handle. A later-registered
/// tool for the same kind overrides an earlier one, so defaults are replaceable.
pub struct ToolRegistry {
    tools: Vec<(TaskKind, Box<dyn Tool>)>,
}

impl ToolRegistry {
    /// The built-in tools, one per [`TaskKind`].
    pub fn with_defaults() -> Self {
        let mut reg = Self { tools: Vec::new() };
        reg.register(TaskKind::Locate, Box::new(LocateTool));
        reg.register(TaskKind::Analyze, Box::new(AnalyzeTool));
        reg.register(TaskKind::Implement, Box::new(ImplementTool));
        reg.register(TaskKind::Verify, Box::new(VerifyTool));
        reg.register(TaskKind::Report, Box::new(ReportTool));
        reg
    }

    pub fn empty() -> Self {
        Self { tools: Vec::new() }
    }

    /// Register (or override) the tool for `kind`.
    pub fn register(&mut self, kind: TaskKind, tool: Box<dyn Tool>) {
        self.tools.push((kind, tool));
    }

    /// The tool for `kind` (the most recently registered wins). Used by the
    /// [`CapabilityLayer`](crate::capability::CapabilityLayer) to resolve a
    /// capability's tool(s); the registry's keying and contents are unchanged.
    pub(crate) fn tool_for(&self, kind: TaskKind) -> Option<&dyn Tool> {
        self.tools.iter().rev().find(|(k, _)| *k == kind).map(|(_, t)| t.as_ref())
    }
}

impl Default for ToolRegistry {
    fn default() -> Self {
        Self::with_defaults()
    }
}

// ───────────────────────────── Built-in tools ──────────────────────────────

/// Locate: assemble the task's semantic context.
struct LocateTool;
impl Tool for LocateTool {
    fn name(&self) -> &'static str {
        "locate"
    }
    fn run(&self, task: &PlanTask, cx: &mut ToolCx) -> ToolOutcome {
        match cx.assemble_context(&task.context) {
            Some(Ok(p)) => {
                let mut o = ToolOutcome::new(
                    TaskState::Succeeded,
                    format!("located context ({} snippets, mode={})", p.included.len(), p.mode),
                );
                o.context = Some(context_summary(&task.context, &p));
                o.artifacts.push(context_artifact(&task.id, &p));
                o
            }
            Some(Err(e)) => ToolOutcome::new(TaskState::Failed, format!("context assembly failed: {e}")),
            None => ToolOutcome::new(TaskState::Skipped, "no focus or files to locate"),
        }
    }
}

/// Analyze: assemble context AND run detectors over the relevant files.
struct AnalyzeTool;
impl Tool for AnalyzeTool {
    fn name(&self) -> &'static str {
        "analyze"
    }
    fn run(&self, task: &PlanTask, cx: &mut ToolCx) -> ToolOutcome {
        let context = match cx.assemble_context(&task.context) {
            Some(Ok(p)) => Some((context_summary(&task.context, &p), context_artifact(&task.id, &p))),
            _ => None,
        };
        let diagnostics = cx.detectors(&task.context);
        let mut o = ToolOutcome::new(
            TaskState::Succeeded,
            format!("analyzed: {} finding(s)", diagnostics.len()),
        );
        if let Some((summary, artifact)) = context {
            o.context = Some(summary);
            o.artifacts.push(artifact);
        }
        // A planned Detectors check on this task records that detectors ran.
        if task.verification.iter().any(|v| v.kind == VerificationKind::Detectors) {
            o.verification.push(CheckResult {
                kind: VerificationKind::Detectors,
                status: CheckStatus::Passed,
                detail: format!("{} finding(s) surfaced for review", diagnostics.len()),
            });
        }
        o.artifacts.push(Artifact::new(
            &task.id,
            ArtifactKind::Diagnostics,
            "diagnostics",
            serde_json::to_value(&diagnostics).unwrap_or(Value::Null),
        ));
        o.diagnostics = diagnostics;
        o
    }
}

/// Implement: assemble context, ask the edit provider for edits, and apply them
/// through the verifying `apply_fix` path. The detector diff IS the verification.
struct ImplementTool;
impl Tool for ImplementTool {
    fn name(&self) -> &'static str {
        "implement"
    }
    fn run(&self, task: &PlanTask, cx: &mut ToolCx) -> ToolOutcome {
        let prompt = match cx.assemble_context(&task.context) {
            Some(Ok(p)) => Some(p),
            Some(Err(e)) => return ToolOutcome::new(TaskState::Failed, format!("context assembly failed: {e}")),
            None => None,
        };

        let mut o = ToolOutcome::new(TaskState::Succeeded, String::new());
        if let Some(p) = &prompt {
            o.context = Some(context_summary(&task.context, p));
            o.artifacts.push(Artifact::new(
                &task.id,
                ArtifactKind::EditRequest,
                "edit_request",
                json!({ "prompt": p.text, "mode": p.mode }),
            ));
        }

        // The Model Runtime: turn context into validated edits. Default => none.
        let mtask = model_task(task);
        let pctx = prompt.as_ref().map(prompt_context);
        let Some(model_edits) = cx.model.run_for_edits(&mtask, pctx.as_ref()) else {
            o.state = TaskState::Skipped;
            o.summary = "no edits produced (no model wired or response rejected)".to_string();
            return o;
        };

        let mut all_clean = true;
        let mut touched: Vec<String> = Vec::new();
        for me in &model_edits {
            touched.push(me.file.clone());
            let engine_edits = to_engine_edits(me);
            match cx.engine.apply_fix(&me.file, &engine_edits, cx.dry_run) {
                Ok(outcome) => {
                    if outcome.applied {
                        o.modified_files.push(me.file.clone());
                    }
                    let clean = outcome.introduced.is_empty();
                    all_clean &= clean;
                    o.verification.push(CheckResult {
                        kind: VerificationKind::Detectors,
                        status: if clean { CheckStatus::Passed } else { CheckStatus::Failed },
                        detail: format!(
                            "{}: resolved {}, introduced {}",
                            me.file,
                            outcome.resolved.len(),
                            outcome.introduced.len()
                        ),
                    });
                    if !clean {
                        o.diagnostics.extend(outcome.introduced);
                    }
                }
                Err(e) => {
                    all_clean = false;
                    o.verification.push(CheckResult {
                        kind: VerificationKind::Detectors,
                        status: CheckStatus::Failed,
                        detail: format!("{}: apply failed: {e}", me.file),
                    });
                }
            }
        }

        // Record the files touched so the downstream verify task can re-check them.
        o.artifacts.push(Artifact::new(
            &task.id,
            ArtifactKind::ModifiedFiles,
            "modified_files",
            json!(touched),
        ));

        if all_clean {
            o.state = TaskState::Succeeded;
            o.summary = format!("applied edits to {} file(s); verification clean", touched.len());
        } else {
            o.state = TaskState::Failed;
            o.summary = "edits introduced new detector findings; rejected".to_string();
        }
        o
    }
}

/// Verify: run each planned check over the files upstream tasks modified.
struct VerifyTool;
impl Tool for VerifyTool {
    fn name(&self) -> &'static str {
        "verify"
    }
    fn run(&self, task: &PlanTask, cx: &mut ToolCx) -> ToolOutcome {
        // Files to re-check: everything upstream ModifiedFiles artifacts name,
        // plus any the task's context lists.
        let mut files: Vec<String> = cx
            .upstream
            .by_kind(ArtifactKind::ModifiedFiles)
            .filter_map(|a| a.data.as_array())
            .flatten()
            .filter_map(|v| v.as_str().map(str::to_string))
            .collect();
        files.extend(task.context.files.clone());
        files.sort();
        files.dedup();

        let mut o = ToolOutcome::new(TaskState::Succeeded, String::new());
        for vc in &task.verification {
            o.verification.push(run_check(cx.engine, vc, &files));
        }
        o.diagnostics = diagnose_files(cx.engine, &files);

        let failed = o.verification.iter().any(|c| c.status == CheckStatus::Failed);
        o.state = if failed { TaskState::Failed } else { TaskState::Succeeded };
        o.summary = format!(
            "verification: {} passed, {} skipped, {} failed",
            count(&o.verification, CheckStatus::Passed),
            count(&o.verification, CheckStatus::Skipped),
            count(&o.verification, CheckStatus::Failed),
        );
        o.artifacts.push(Artifact::new(
            &task.id,
            ArtifactKind::Verification,
            "verification",
            serde_json::to_value(&o.verification).unwrap_or(Value::Null),
        ));
        o
    }
}

/// Report: compile a human-facing summary from upstream artifacts.
struct ReportTool;
impl Tool for ReportTool {
    fn name(&self) -> &'static str {
        "report"
    }
    fn run(&self, task: &PlanTask, cx: &mut ToolCx) -> ToolOutcome {
        let mut lines = vec![format!("Report for: {}", task.description)];
        for a in cx.upstream.all() {
            lines.push(format!("- [{}] {} ({:?}) by {}", a.kind_label(), a.name, a.kind, a.producer));
        }
        let findings: usize = cx
            .upstream
            .by_kind(ArtifactKind::Diagnostics)
            .filter_map(|a| a.data.as_array().map(|arr| arr.len()))
            .sum();
        lines.push(format!("Total findings surfaced upstream: {findings}"));

        let mut o = ToolOutcome::new(
            TaskState::Succeeded,
            format!("report compiled from {} upstream artifact(s)", cx.upstream.all().len()),
        );
        o.artifacts.push(Artifact::new(
            &task.id,
            ArtifactKind::Report,
            "report",
            json!({ "text": lines.join("\n") }),
        ));
        o
    }
}

impl Artifact {
    fn kind_label(&self) -> &'static str {
        match self.kind {
            ArtifactKind::Context => "context",
            ArtifactKind::EditRequest => "edit",
            ArtifactKind::Diagnostics => "diagnostics",
            ArtifactKind::ModifiedFiles => "modified",
            ArtifactKind::Verification => "verification",
            ArtifactKind::Report => "report",
        }
    }
}

// ───────────────────────────── Executor ────────────────────────────────────

/// The Execution Engine. Walks a [`Plan`]'s schedule and drives each task through
/// the state machine via the [`ToolRegistry`], recording artifacts and events.
pub struct Executor<'a> {
    engine: &'a mut IndexEngine,
    policy: UserPolicy,
    model: &'a dyn ModelBackend,
    dry_run: bool,
    registry: ToolRegistry,
    capabilities: CapabilityLayer,
    artifacts: ArtifactStore,
    log: EventLog,
}

impl<'a> Executor<'a> {
    /// Executor over an explicit [`ModelBackend`]. Supply
    /// [`NullBackend`](crate::model_runtime::NullBackend) (or a
    /// [`ModelRuntime`] with no real provider) for the deterministic default where
    /// mutating tasks are skipped; choose whether edits are written
    /// (`dry_run = false`) or only computed + verified.
    ///
    /// [`ModelRuntime`]: crate::model_runtime::ModelRuntime
    pub fn with_backend(
        engine: &'a mut IndexEngine,
        policy: UserPolicy,
        model: &'a dyn ModelBackend,
        dry_run: bool,
    ) -> Self {
        Self {
            engine,
            policy,
            model,
            dry_run,
            registry: ToolRegistry::with_defaults(),
            capabilities: CapabilityLayer::new(),
            artifacts: ArtifactStore::default(),
            log: EventLog::new(None),
        }
    }

    /// Replace the tool registry (register custom/override tools before running).
    pub fn set_registry(&mut self, registry: ToolRegistry) -> &mut Self {
        self.registry = registry;
        self
    }

    /// Attach a live event sink (e.g. stream progress to the editor). Events are
    /// still recorded into the [`ExecutionResult`] regardless.
    pub fn set_event_sink(&mut self, sink: Box<dyn EventSink>) -> &mut Self {
        self.log = EventLog::new(Some(sink));
        self
    }

    /// Execute the whole plan. Waves run in schedule order; tasks within a wave
    /// run sequentially (deterministic). A task whose dependency did not succeed
    /// is `Blocked`; one whose dependency was skipped is itself `Skipped`.
    pub fn execute(&mut self, plan: &Plan) -> ExecutionResult {
        let started = Instant::now();
        self.log.emit(ExecutionEvent::PlanStarted {
            goal: plan.goal.clone(),
            intent: plan.intent,
            tasks: plan.tasks.len(),
            waves: plan.schedule.len(),
        });

        let mut done: Vec<TaskExecution> = Vec::with_capacity(plan.tasks.len());

        for wave in &plan.schedule {
            for id in wave {
                let Some(task) = plan.tasks.iter().find(|t| &t.id == id) else { continue };

                // Drive the dependency gate through the state machine.
                if let Some(stub) = self.gate(task, &done) {
                    done.push(stub);
                    continue;
                }
                let exec = self.run_task(task);
                done.push(exec);
            }
        }

        let status = overall_status(&done);
        self.log.emit(ExecutionEvent::PlanFinished { status });

        let metadata = summarize(plan, &done, self.policy, plan.schedule.len(), started.elapsed().as_millis());
        ExecutionResult {
            goal: plan.goal.clone(),
            intent: plan.intent,
            status,
            tasks: done,
            artifacts: self.artifacts.all().to_vec(),
            events: std::mem::take(&mut self.log.events),
            metadata,
        }
    }

    /// Evaluate dependencies. Returns `Some(stub)` (Blocked/Skipped) when the task
    /// must not run, emitting the lifecycle transitions; `None` when it's `Ready`.
    fn gate(&mut self, task: &PlanTask, done: &[TaskExecution]) -> Option<TaskExecution> {
        let dep_state = |dep: &str| done.iter().find(|d| &d.id == dep).map(|d| d.state);

        if task.depends_on.is_empty() {
            self.transition(&task.id, TaskState::Pending, TaskState::Ready);
            return None;
        }

        // It has dependencies, so it passed through Waiting.
        self.transition(&task.id, TaskState::Pending, TaskState::Waiting);

        // A failed/blocked/missing dependency blocks this task.
        if task.depends_on.iter().any(|dep| {
            matches!(dep_state(dep), Some(TaskState::Failed) | Some(TaskState::Blocked) | None)
        }) {
            self.transition(&task.id, TaskState::Waiting, TaskState::Blocked);
            self.log.emit(ExecutionEvent::TaskFinished { task: task.id.clone(), state: TaskState::Blocked });
            return Some(stub_task(task, TaskState::Blocked, "dependency did not succeed"));
        }
        // A skipped dependency leaves nothing to build on -> defer (skip), don't
        // fail: that's a clean partial run.
        if task.depends_on.iter().any(|dep| dep_state(dep) == Some(TaskState::Skipped)) {
            self.transition(&task.id, TaskState::Waiting, TaskState::Skipped);
            self.log.emit(ExecutionEvent::TaskFinished { task: task.id.clone(), state: TaskState::Skipped });
            return Some(stub_task(task, TaskState::Skipped, "upstream task was skipped"));
        }

        self.transition(&task.id, TaskState::Waiting, TaskState::Ready);
        None
    }

    /// Dispatch a ready task to its tool and record the result + events.
    fn run_task(&mut self, task: &PlanTask) -> TaskExecution {
        let started = Instant::now();
        // The capability names the work; its primary tool kind drives model
        // routing and labels the recorded execution.
        let kind = task.capability.primary_kind();
        // Routing is the Model Runtime's single decision; the executor only asks.
        // Keep the prior contract: a no-model task records no route (None).
        let resolved = self.model.route_for(&model_task(task), self.policy);
        let route = resolved.model.map(|_| resolved);

        self.transition(&task.id, TaskState::Ready, TaskState::Running);
        self.log.emit(ExecutionEvent::TaskStarted { task: task.id.clone(), kind });

        // Dispatch through the Capability Layer: it resolves the capability to
        // registered tool(s) and merges their outcome. The runtime stays unaware
        // of which concrete tools a capability orchestrates.
        let mut outcome = {
            let mut cx = ToolCx {
                engine: &mut *self.engine,
                policy: self.policy,
                model: self.model,
                dry_run: self.dry_run,
                upstream: &self.artifacts,
            };
            self.capabilities.execute(task.capability, task, &mut cx, &self.registry)
        };
        outcome.route = route;

        // Verifying state + events for the capabilities that actually verify.
        let verifies = task.capability.runs_verification() && !outcome.verification.is_empty();
        if verifies {
            self.transition(&task.id, TaskState::Running, TaskState::Verifying);
            self.log.emit(ExecutionEvent::VerificationStarted {
                task: task.id.clone(),
                checks: outcome.verification.len(),
            });
            self.log.emit(ExecutionEvent::VerificationFinished {
                task: task.id.clone(),
                passed: count(&outcome.verification, CheckStatus::Passed),
                failed: count(&outcome.verification, CheckStatus::Failed),
                skipped: count(&outcome.verification, CheckStatus::Skipped),
            });
            self.transition(&task.id, TaskState::Verifying, outcome.state);
        } else {
            self.transition(&task.id, TaskState::Running, outcome.state);
        }

        // Publish artifacts to the store + stream.
        for a in &outcome.artifacts {
            self.artifacts.add(a.clone());
            self.log.emit(ExecutionEvent::ArtifactProduced {
                task: task.id.clone(),
                name: a.name.clone(),
                kind: a.kind,
            });
        }
        self.log.emit(ExecutionEvent::TaskFinished { task: task.id.clone(), state: outcome.state });

        TaskExecution {
            id: task.id.clone(),
            kind,
            state: outcome.state,
            summary: outcome.summary,
            route: outcome.route,
            context: outcome.context,
            diagnostics: outcome.diagnostics,
            verification: outcome.verification,
            modified_files: outcome.modified_files,
            artifacts: outcome.artifacts,
            elapsed_ms: started.elapsed().as_millis(),
        }
    }

    /// Emit a (guarded) lifecycle transition.
    fn transition(&mut self, task: &str, from: TaskState, to: TaskState) {
        debug_assert!(from.can_transition_to(to), "illegal task transition {from:?} -> {to:?}");
        self.log.emit(ExecutionEvent::TaskStateChanged { task: task.to_string(), from, to });
    }
}

// ───────────────────────────── Free helpers ────────────────────────────────

/// The workspace file a focus names: the location's file, or the qualified
/// name's `file::…` prefix for a symbol focus.
fn focus_file(focus: &Option<FocusSpec>) -> Option<String> {
    match focus {
        Some(FocusSpec::Location { file, .. }) => Some(file.clone()),
        Some(FocusSpec::Symbol(q)) => q.split_once("::").map(|(file, _)| file.to_string()),
        None => None,
    }
}

/// The files a context plan is relevant to: listed files plus the focus file.
fn relevant_files(ctx: &ContextPlan) -> Vec<String> {
    let mut files = ctx.files.clone();
    if let Some(f) = focus_file(&ctx.focus) {
        files.push(f);
    }
    files.sort();
    files.dedup();
    files
}

/// Run the detectors over each file and collect the findings.
fn diagnose_files(engine: &IndexEngine, files: &[String]) -> Vec<Finding> {
    let mut findings = Vec::new();
    for f in files {
        if let Ok(mut fs) = engine.diagnose(f) {
            findings.append(&mut fs);
        }
    }
    findings
}

/// Run one verification check. Detectors is backed by the real detector engine;
/// compile / tests / regression are seams reported as `Skipped` until a runner is
/// integrated (a later milestone), so we never claim an unchecked pass.
fn run_check(engine: &IndexEngine, vc: &VerificationCheck, files: &[String]) -> CheckResult {
    match vc.kind {
        VerificationKind::Detectors => {
            let total = diagnose_files(engine, files).len();
            CheckResult {
                kind: vc.kind,
                status: if total == 0 { CheckStatus::Passed } else { CheckStatus::Failed },
                detail: format!("{total} finding(s) on {} file(s)", files.len()),
            }
        }
        VerificationKind::Compile | VerificationKind::Tests | VerificationKind::Regression => CheckResult {
            kind: vc.kind,
            status: CheckStatus::Skipped,
            detail: "no runner integrated yet".to_string(),
        },
    }
}

fn context_summary(ctx: &ContextPlan, prompt: &BuiltPrompt) -> ContextSummary {
    ContextSummary {
        mode: prompt.mode.to_string(),
        token_estimate: prompt.token_estimate,
        included: prompt.included.len(),
        dropped: prompt.dropped,
        focus: ctx.focus.clone(),
    }
}

fn context_artifact(producer: &str, prompt: &BuiltPrompt) -> Artifact {
    Artifact::new(
        producer,
        ArtifactKind::Context,
        "context",
        json!({
            "mode": prompt.mode,
            "token_estimate": prompt.token_estimate,
            "included": prompt.included.len(),
            "dropped": prompt.dropped,
        }),
    )
}

/// A non-dispatched task record (blocked or deferred) due to a dependency.
fn stub_task(task: &PlanTask, state: TaskState, summary: &str) -> TaskExecution {
    TaskExecution {
        id: task.id.clone(),
        kind: task.capability.primary_kind(),
        state,
        summary: summary.to_string(),
        route: None,
        context: None,
        diagnostics: Vec::new(),
        verification: Vec::new(),
        modified_files: Vec::new(),
        artifacts: Vec::new(),
        elapsed_ms: 0,
    }
}

fn count(checks: &[CheckResult], status: CheckStatus) -> usize {
    checks.iter().filter(|c| c.status == status).count()
}

fn overall_status(tasks: &[TaskExecution]) -> ExecutionStatus {
    if tasks.iter().any(|t| matches!(t.state, TaskState::Failed | TaskState::Blocked)) {
        ExecutionStatus::Failed
    } else if tasks.iter().any(|t| t.state == TaskState::Skipped) {
        ExecutionStatus::Partial
    } else {
        ExecutionStatus::Succeeded
    }
}

fn summarize(
    plan: &Plan,
    tasks: &[TaskExecution],
    policy: UserPolicy,
    waves: usize,
    elapsed_ms: u128,
) -> ExecutionMetadata {
    let by = |s: TaskState| tasks.iter().filter(|t| t.state == s).count();
    ExecutionMetadata {
        policy,
        waves,
        tasks_total: plan.tasks.len(),
        tasks_succeeded: by(TaskState::Succeeded),
        tasks_failed: by(TaskState::Failed),
        tasks_skipped: by(TaskState::Skipped),
        tasks_blocked: by(TaskState::Blocked),
        elapsed_ms,
    }
}
