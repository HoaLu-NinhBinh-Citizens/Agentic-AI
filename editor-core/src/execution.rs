//! Execution Runtime: consumes a [`Plan`] and runs it.
//!
//! The division of labor (mirrors the milestone's design goals):
//!
//! * **Planner** decides *what* to do — a deterministic [`Plan`] (intent + task
//!   DAG + schedule + per-task context/verification). It never executes.
//! * **Execution Engine** (this module) decides *how* — it walks the planner
//!   schedule wave by wave, and for each [`PlanTask`] selects a model (inference
//!   router), assembles that task's own context (semantic context builder),
//!   dispatches to the right engine API ([`ToolDispatcher`]), and, for mutating
//!   tasks, runs verification before declaring success.
//! * **Semantic Engine** supplies the minimal relevant context per task.
//! * **Verification** validates mutating results (detector diff today; compile /
//!   tests / regression are seams reported as `Skipped` until a runner exists).
//!
//! This milestone is deterministic: no retry, no reflection, no replanning, no
//! multi-agent. The one variation point that a future milestone fills — turning
//! assembled context into actual edits via the LLM — is the [`EditProvider`]
//! seam. Its default ([`NoEdits`]) produces nothing, so a mutating task without
//! a wired model is reported `Skipped` (honestly, never fabricated).

use std::time::Instant;

use serde::Serialize;

use crate::context::{BuildRequest, BuiltPrompt, Task as CtxTask};
use crate::detector::Finding;
use crate::index::{Edit, IndexEngine};
use crate::inference::{self, Route, Task as InfTask, UserPolicy};
use crate::planner::{
    ContextPlan, Intent, Plan, PlanTask, TaskKind, VerificationCheck, VerificationKind,
};
use crate::semantic::FocusSpec;

/// Edits a mutating task wants applied, grouped per file. The Execution Engine
/// applies these through the verifying [`IndexEngine::apply_fix`] path.
#[derive(Debug, Clone)]
pub struct FileEdits {
    pub file: String,
    pub edits: Vec<Edit>,
}

/// The seam between "assembled context" and "concrete edits". In this milestone
/// the default is [`NoEdits`] (deterministic, no LLM). A future milestone plugs
/// a model client in here without touching the runtime.
pub trait EditProvider {
    /// Given a mutating task and the context assembled for it, return the edits
    /// to apply, or `None` when no edits are available.
    fn edits_for(&self, task: &PlanTask, context: Option<&BuiltPrompt>) -> Option<Vec<FileEdits>>;
}

/// Default provider: produces no edits. Mutating tasks become `Skipped` with the
/// assembled context preserved as an artifact (the request a model would fill).
pub struct NoEdits;

impl EditProvider for NoEdits {
    fn edits_for(&self, _task: &PlanTask, _context: Option<&BuiltPrompt>) -> Option<Vec<FileEdits>> {
        None
    }
}

/// Outcome of one task.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum TaskStatus {
    /// Ran and met its success criteria (including verification, if mutating).
    Succeeded,
    /// Ran but failed its criteria (e.g. verification regressed).
    Failed,
    /// Intentionally not run to completion — a mutating task with no edits
    /// available (model seam not wired), or a context-only task with nothing to
    /// focus on.
    Skipped,
    /// Not attempted because a dependency did not succeed.
    Blocked,
}

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

/// A produced output the editor/agent can consume (assembled prompt, report, …).
#[derive(Debug, Clone, Serialize)]
pub struct Artifact {
    pub name: String,
    pub content: String,
}

/// The record of executing one [`PlanTask`].
#[derive(Debug, Clone, Serialize)]
pub struct TaskExecution {
    pub id: String,
    pub kind: TaskKind,
    pub status: TaskStatus,
    pub summary: String,
    /// Model selection for this task (None = no model needed). Resolved here, at
    /// execution time — never during planning.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub route: Option<Route>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub context: Option<ContextSummary>,
    /// Detector findings gathered (analyze / verify tasks).
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub diagnostics: Vec<Finding>,
    /// Verification check outcomes (mutating tasks, and the explicit verify task).
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub verification: Vec<CheckResult>,
    /// Files this task modified on disk (mutating tasks).
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
    pub metadata: ExecutionMetadata,
}

/// Maps a [`TaskKind`] to the existing engine APIs and runs it. This is the
/// "how": context assembly, model selection, tool calls, verification — all
/// reusing modules that already exist (`build_context`, `diagnose`, `apply_fix`,
/// the inference router).
pub struct ToolDispatcher<'a> {
    engine: &'a mut IndexEngine,
    policy: UserPolicy,
    edits: &'a dyn EditProvider,
    /// Apply edits to disk (`false`) or only compute + verify them (`true`).
    dry_run: bool,
}

impl<'a> ToolDispatcher<'a> {
    /// Which inference task (if any) a kind corresponds to. Context-only and
    /// verification steps need no model.
    fn inference_task(kind: TaskKind) -> Option<InfTask> {
        match kind {
            TaskKind::Locate => None,
            TaskKind::Analyze => Some(InfTask::Chat),
            TaskKind::Implement => Some(InfTask::Apply),
            TaskKind::Verify => None,
            TaskKind::Report => Some(InfTask::Chat),
        }
    }

    /// Turn a task's [`ContextPlan`] into a [`BuildRequest`] and assemble its
    /// context via the existing semantic context builder. Returns `None` when the
    /// plan has nothing to center on (a workspace-wide step).
    fn assemble_context(&mut self, ctx: &ContextPlan) -> Option<anyhow::Result<BuiltPrompt>> {
        let (file, cursor_byte, focus_symbol) = match &ctx.focus {
            Some(FocusSpec::Symbol(s)) => (String::new(), 0usize, Some(s.clone())),
            Some(FocusSpec::Location { file, byte }) => (file.clone(), *byte, None),
            None => {
                // No focus: fall back to the first candidate file, if any. With
                // neither, there's nothing to assemble.
                match ctx.files.first() {
                    Some(f) => (f.clone(), 0usize, None),
                    None => return None,
                }
            }
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
    fn run_detectors(&self, ctx: &ContextPlan) -> Vec<Finding> {
        let mut files: Vec<String> = ctx.files.clone();
        if let Some(f) = focus_file(&ctx.focus) {
            files.push(f);
        }
        files.sort();
        files.dedup();
        let mut findings = Vec::new();
        for f in files {
            if let Ok(mut fs) = self.engine.diagnose(&f) {
                findings.append(&mut fs);
            }
        }
        findings
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
}

/// The Execution Engine. Walks a [`Plan`]'s schedule and executes each task,
/// gating on dependencies. Holds no mutable run state itself beyond the engine
/// handle — every task's record is returned in the [`ExecutionResult`].
pub struct Executor<'a> {
    dispatcher: ToolDispatcher<'a>,
}

impl<'a> Executor<'a> {
    /// Executor with the deterministic default ([`NoEdits`]): mutating tasks are
    /// skipped (no model wired), everything else runs for real.
    pub fn new(engine: &'a mut IndexEngine, policy: UserPolicy) -> Self {
        Self::with_options(engine, policy, &NoEdits, false)
    }

    /// Full control: supply an [`EditProvider`] (the future model seam) and choose
    /// whether mutating edits are written (`dry_run = false`) or only verified.
    pub fn with_options(
        engine: &'a mut IndexEngine,
        policy: UserPolicy,
        edits: &'a dyn EditProvider,
        dry_run: bool,
    ) -> Self {
        Self { dispatcher: ToolDispatcher { engine, policy, edits, dry_run } }
    }

    /// Execute the whole plan. Waves run in schedule order; tasks within a wave
    /// run sequentially (deterministic). A task whose dependency did not succeed
    /// is `Blocked` and never dispatched.
    pub fn execute(&mut self, plan: &Plan) -> ExecutionResult {
        let started = Instant::now();
        let mut done: Vec<TaskExecution> = Vec::with_capacity(plan.tasks.len());

        for wave in &plan.schedule {
            for id in wave {
                let Some(task) = plan.tasks.iter().find(|t| &t.id == id) else { continue };

                // Dependency gate. A failed/blocked dependency *blocks* this task
                // (it can't run). A *skipped* dependency (e.g. a mutating task with
                // no model wired) leaves nothing to build on, so this task is
                // deferred (skipped) rather than blocked — that's a clean partial
                // run, not a failure.
                let dep_status = |dep: &str| done.iter().find(|d| &d.id == dep).map(|d| d.status);
                if task.depends_on.iter().any(|dep| {
                    matches!(dep_status(dep), Some(TaskStatus::Failed) | Some(TaskStatus::Blocked) | None)
                }) {
                    done.push(stub_task(task, TaskStatus::Blocked, "dependency did not succeed"));
                    continue;
                }
                if task.depends_on.iter().any(|dep| dep_status(dep) == Some(TaskStatus::Skipped)) {
                    done.push(stub_task(task, TaskStatus::Skipped, "upstream task was skipped"));
                    continue;
                }

                let exec = self.run_task(task, &done);
                done.push(exec);
            }
        }

        let metadata = summarize(
            plan,
            &done,
            self.dispatcher.policy,
            plan.schedule.len(),
            started.elapsed().as_millis(),
        );
        let status = overall_status(&done);
        ExecutionResult {
            goal: plan.goal.clone(),
            intent: plan.intent,
            status,
            tasks: done,
            metadata,
        }
    }

    /// Dispatch a single ready task by kind.
    fn run_task(&mut self, task: &PlanTask, prior: &[TaskExecution]) -> TaskExecution {
        let started = Instant::now();
        let route = ToolDispatcher::inference_task(task.kind)
            .map(|t| inference::plan(self.dispatcher.policy, t));

        let mut exec = TaskExecution {
            id: task.id.clone(),
            kind: task.kind,
            status: TaskStatus::Succeeded,
            summary: String::new(),
            route,
            context: None,
            diagnostics: Vec::new(),
            verification: Vec::new(),
            modified_files: Vec::new(),
            artifacts: Vec::new(),
            elapsed_ms: 0,
        };

        match task.kind {
            TaskKind::Locate => self.do_locate(task, &mut exec),
            TaskKind::Analyze => self.do_analyze(task, &mut exec),
            TaskKind::Implement => self.do_implement(task, &mut exec),
            TaskKind::Verify => self.do_verify(task, prior, &mut exec),
            TaskKind::Report => self.do_report(task, prior, &mut exec),
        }

        exec.elapsed_ms = started.elapsed().as_millis();
        exec
    }

    fn do_locate(&mut self, task: &PlanTask, exec: &mut TaskExecution) {
        match self.dispatcher.assemble_context(&task.context) {
            Some(Ok(prompt)) => {
                exec.context = Some(ToolDispatcher::context_summary(&task.context, &prompt));
                exec.summary = format!("located context ({} snippets, mode={})", prompt.included.len(), prompt.mode);
            }
            Some(Err(e)) => {
                exec.status = TaskStatus::Failed;
                exec.summary = format!("context assembly failed: {e}");
            }
            None => {
                exec.status = TaskStatus::Skipped;
                exec.summary = "no focus or files to locate".to_string();
            }
        }
    }

    fn do_analyze(&mut self, task: &PlanTask, exec: &mut TaskExecution) {
        // Analyze assembles context AND runs detectors over the relevant files.
        if let Some(Ok(prompt)) = self.dispatcher.assemble_context(&task.context) {
            exec.context = Some(ToolDispatcher::context_summary(&task.context, &prompt));
        }
        exec.diagnostics = self.dispatcher.run_detectors(&task.context);
        // Record the planned detector check, if any.
        for vc in &task.verification {
            if vc.kind == VerificationKind::Detectors {
                exec.verification.push(CheckResult {
                    kind: VerificationKind::Detectors,
                    status: CheckStatus::Passed,
                    detail: format!("{} finding(s) surfaced for review", exec.diagnostics.len()),
                });
            }
        }
        exec.summary = format!("analyzed: {} finding(s)", exec.diagnostics.len());
    }

    fn do_implement(&mut self, task: &PlanTask, exec: &mut TaskExecution) {
        // Assemble the context a model would edit against (kept as an artifact).
        let prompt = match self.dispatcher.assemble_context(&task.context) {
            Some(Ok(p)) => Some(p),
            Some(Err(e)) => {
                exec.status = TaskStatus::Failed;
                exec.summary = format!("context assembly failed: {e}");
                return;
            }
            None => None,
        };
        if let Some(p) = &prompt {
            exec.context = Some(ToolDispatcher::context_summary(&task.context, p));
            exec.artifacts.push(Artifact { name: "edit_request".to_string(), content: p.text.clone() });
        }

        // The model seam: turn context into edits. Default => none.
        let Some(file_edits) = self.dispatcher.edits.edits_for(task, prompt.as_ref()) else {
            exec.status = TaskStatus::Skipped;
            exec.summary = "no edits produced (model seam not wired)".to_string();
            return;
        };

        // Apply each file's edits through the verifying apply_fix path. The
        // detector diff IS the verification: a clean apply introduces no findings.
        let mut all_clean = true;
        let mut applied_any = false;
        for fe in &file_edits {
            match self.dispatcher.engine.apply_fix(&fe.file, &fe.edits, self.dispatcher.dry_run) {
                Ok(outcome) => {
                    if outcome.applied {
                        applied_any = true;
                        exec.modified_files.push(fe.file.clone());
                    }
                    let clean = outcome.introduced.is_empty();
                    all_clean &= clean;
                    exec.verification.push(CheckResult {
                        kind: VerificationKind::Detectors,
                        status: if clean { CheckStatus::Passed } else { CheckStatus::Failed },
                        detail: format!(
                            "{}: resolved {}, introduced {}",
                            fe.file,
                            outcome.resolved.len(),
                            outcome.introduced.len()
                        ),
                    });
                    if !clean {
                        exec.diagnostics.extend(outcome.introduced);
                    }
                }
                Err(e) => {
                    all_clean = false;
                    exec.verification.push(CheckResult {
                        kind: VerificationKind::Detectors,
                        status: CheckStatus::Failed,
                        detail: format!("{}: apply failed: {e}", fe.file),
                    });
                }
            }
        }

        if all_clean {
            exec.status = TaskStatus::Succeeded;
            exec.summary = format!(
                "applied edits to {} file(s); verification clean",
                exec.modified_files.len().max(if self.dispatcher.dry_run { file_edits.len() } else { 0 })
            );
        } else {
            exec.status = TaskStatus::Failed;
            exec.summary = "edits introduced new detector findings; rejected".to_string();
        }
        let _ = applied_any;
    }

    fn do_verify(&mut self, task: &PlanTask, prior: &[TaskExecution], exec: &mut TaskExecution) {
        // Files to re-check: everything mutated by upstream tasks, plus any the
        // task's context names.
        let mut files: Vec<String> = prior.iter().flat_map(|t| t.modified_files.clone()).collect();
        files.extend(task.context.files.clone());
        files.sort();
        files.dedup();

        for vc in &task.verification {
            exec.verification.push(self.run_check(vc, &files));
        }
        // Surface remaining detector findings on the checked files.
        for f in &files {
            if let Ok(mut fs) = self.dispatcher.engine.diagnose(f) {
                exec.diagnostics.append(&mut fs);
            }
        }

        let failed = exec.verification.iter().any(|c| c.status == CheckStatus::Failed);
        exec.status = if failed { TaskStatus::Failed } else { TaskStatus::Succeeded };
        exec.summary = format!(
            "verification: {} passed, {} skipped, {} failed",
            count(&exec.verification, CheckStatus::Passed),
            count(&exec.verification, CheckStatus::Skipped),
            count(&exec.verification, CheckStatus::Failed),
        );
    }

    /// Run one verification check. Detectors is backed by the real detector
    /// engine; compile / tests / regression are seams reported as `Skipped` until
    /// a runner is integrated (a later milestone), so we never claim an unchecked
    /// pass.
    fn run_check(&self, vc: &VerificationCheck, files: &[String]) -> CheckResult {
        match vc.kind {
            VerificationKind::Detectors => {
                let mut total = 0usize;
                for f in files {
                    if let Ok(fs) = self.dispatcher.engine.diagnose(f) {
                        total += fs.len();
                    }
                }
                CheckResult {
                    kind: vc.kind,
                    status: if total == 0 { CheckStatus::Passed } else { CheckStatus::Failed },
                    detail: format!("{total} finding(s) on {} file(s)", files.len()),
                }
            }
            VerificationKind::Compile | VerificationKind::Tests | VerificationKind::Regression => {
                CheckResult {
                    kind: vc.kind,
                    status: CheckStatus::Skipped,
                    detail: "no runner integrated yet".to_string(),
                }
            }
        }
    }

    fn do_report(&mut self, task: &PlanTask, prior: &[TaskExecution], exec: &mut TaskExecution) {
        let findings: usize = prior.iter().map(|t| t.diagnostics.len()).sum();
        let mut lines = vec![format!("Report for: {}", task.description)];
        for t in prior {
            lines.push(format!("- {} [{:?}] {}", t.id, t.status, t.summary));
        }
        lines.push(format!("Total findings surfaced: {findings}"));
        exec.artifacts.push(Artifact { name: "report".to_string(), content: lines.join("\n") });
        exec.summary = format!("report compiled from {} upstream task(s)", prior.len());
    }
}

/// A non-dispatched task record (blocked or deferred) due to a dependency.
fn stub_task(task: &PlanTask, status: TaskStatus, summary: &str) -> TaskExecution {
    TaskExecution {
        id: task.id.clone(),
        kind: task.kind,
        status,
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

/// The workspace file a focus names: the location's file, or the qualified
/// name's `file::…` prefix for a symbol focus.
fn focus_file(focus: &Option<FocusSpec>) -> Option<String> {
    match focus {
        Some(FocusSpec::Location { file, .. }) => Some(file.clone()),
        Some(FocusSpec::Symbol(q)) => q.split_once("::").map(|(file, _)| file.to_string()),
        None => None,
    }
}

fn count(checks: &[CheckResult], status: CheckStatus) -> usize {
    checks.iter().filter(|c| c.status == status).count()
}

fn overall_status(tasks: &[TaskExecution]) -> ExecutionStatus {
    if tasks.iter().any(|t| matches!(t.status, TaskStatus::Failed | TaskStatus::Blocked)) {
        ExecutionStatus::Failed
    } else if tasks.iter().any(|t| t.status == TaskStatus::Skipped) {
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
    let by = |s: TaskStatus| tasks.iter().filter(|t| t.status == s).count();
    ExecutionMetadata {
        policy,
        waves,
        tasks_total: plan.tasks.len(),
        tasks_succeeded: by(TaskStatus::Succeeded),
        tasks_failed: by(TaskStatus::Failed),
        tasks_skipped: by(TaskStatus::Skipped),
        tasks_blocked: by(TaskStatus::Blocked),
        elapsed_ms,
    }
}
