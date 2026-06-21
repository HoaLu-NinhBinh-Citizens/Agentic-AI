//! Tests for the Execution Runtime: it consumes a planner `Plan` and runs it
//! deterministically — assembling per-task context, selecting a model per task
//! (inference router), dispatching to the existing engine APIs, and gating
//! mutating tasks on verification before declaring success. No retry, no
//! reflection, no LLM call: the edit seam is supplied explicitly.

use std::fs;

use aircore::execution::{
    ArtifactKind, Executor, ExecutionEvent, ExecutionStatus, TaskState,
};
use aircore::index::IndexEngine;
use aircore::inference::{Endpoint, Model, Route, UserPolicy};
use aircore::model_runtime::dto::EditSpan;
use aircore::model_runtime::dto::ModelEdit;
use aircore::model_runtime::provider::TokenSink;
use aircore::model_runtime::{ModelBackend, ModelOutcome, ModelRequest, ModelResult};
use aircore::planner::{PlanRequest, Planner, TaskKind};

fn synced_workspace(files: &[(&str, &str)]) -> (tempfile::TempDir, IndexEngine) {
    let dir = tempfile::tempdir().unwrap();
    for (path, src) in files {
        let abs = dir.path().join(path);
        fs::create_dir_all(abs.parent().unwrap()).unwrap();
        fs::write(abs, src).unwrap();
    }
    let mut engine = IndexEngine::open(dir.path()).unwrap();
    engine.sync().unwrap();
    (dir, engine)
}

const CARGO: &str = "[package]\nname = \"demo\"\nversion = \"0.1.0\"\n";
// One `.unwrap()` -> exactly one `rust/unwrap` finding.
const BUGGY: &str =
    "pub fn run() -> i32 {\n    let x: Option<i32> = Some(1);\n    x.unwrap()\n}\n";
const CLEAN: &str =
    "pub fn run() -> i32 {\n    let x: Option<i32> = Some(1);\n    x.unwrap_or(0)\n}\n";

/// A deterministic model backend standing in for a real model client. Returns a
/// fixed edit set regardless of input (the model output is the only nondeterminism
/// the runtime allows, so a test pins it). Routing uses the trait default.
struct StaticEdits {
    file: String,
    spans: Vec<EditSpan>,
}

impl ModelBackend for StaticEdits {
    fn run(&self, _req: &ModelRequest, _sink: &mut dyn TokenSink) -> ModelResult {
        ModelResult {
            // The executor records the route via the trait-default `route_for`;
            // this test double's own route is unused, so a neutral stub suffices.
            route: Route { model: None, endpoint: Endpoint::Local },
            prompt: None,
            response: None,
            outcome: ModelOutcome::Edits(vec![ModelEdit {
                file: self.file.clone(),
                spans: self.spans.clone(),
            }]),
        }
    }
}

fn bug_fix_plan(focus: &str) -> aircore::planner::Plan {
    Planner::plan(&PlanRequest {
        goal: "fix the crash in run".to_string(),
        focus_symbol: Some(focus.to_string()),
        ..Default::default()
    })
}

#[test]
fn default_runtime_runs_readonly_tasks_and_skips_mutating() {
    let (_dir, mut engine) =
        synced_workspace(&[("Cargo.toml", CARGO), ("src/lib.rs", BUGGY)]);
    let plan = bug_fix_plan("src/lib.rs::run");

    let result = engine.execute_plan(&plan, UserPolicy::Cloud);

    // Locate + Analyze run; Implement is skipped (no edits wired); Verify runs.
    let by_kind = |k: TaskKind| result.tasks.iter().find(|t| t.kind == k).unwrap();
    assert_eq!(by_kind(TaskKind::Locate).state, TaskState::Succeeded);
    assert_eq!(by_kind(TaskKind::Analyze).state, TaskState::Succeeded);
    assert_eq!(by_kind(TaskKind::Implement).state, TaskState::Skipped);

    // The skipped implement task still selected a model (router ran at exec time).
    assert_eq!(by_kind(TaskKind::Implement).route.unwrap().model, Some(Model::Haiku45));
    // ...and preserved the assembled context as the edit-request artifact.
    assert!(by_kind(TaskKind::Implement).artifacts.iter().any(|a| a.name == "edit_request"));

    // Analyze surfaced the unwrap finding.
    assert!(!by_kind(TaskKind::Analyze).diagnostics.is_empty());

    // A skipped (not failed) task => Partial overall. The downstream verify task
    // defers too (nothing to verify), so two tasks are skipped.
    assert_eq!(result.status, ExecutionStatus::Partial);
    assert_eq!(by_kind(TaskKind::Verify).state, TaskState::Skipped);
    assert_eq!(result.metadata.tasks_skipped, 2);
    assert_eq!(result.metadata.policy, UserPolicy::Cloud);
}

#[test]
fn mutating_task_applies_and_passes_verification() {
    let (_dir, mut engine) =
        synced_workspace(&[("Cargo.toml", CARGO), ("src/lib.rs", BUGGY)]);
    let plan = bug_fix_plan("src/lib.rs::run");

    // Edit that removes the unwrap (resolves the finding, introduces none).
    let off = BUGGY.find("x.unwrap()").unwrap();
    let provider = StaticEdits {
        file: "src/lib.rs".to_string(),
        spans: vec![EditSpan {
            start_byte: off,
            end_byte: off + "x.unwrap()".len(),
            new_text: "x.unwrap_or(0)".to_string(),
        }],
    };

    let result = {
        let mut exec = Executor::with_backend(&mut engine, UserPolicy::Cloud, &provider, false);
        exec.execute(&plan)
    };

    let implement = result.tasks.iter().find(|t| t.kind == TaskKind::Implement).unwrap();
    assert_eq!(implement.state, TaskState::Succeeded, "{:?}", implement);
    assert_eq!(implement.modified_files, vec!["src/lib.rs".to_string()]);
    // Verification ran on the mutating task (detector diff) and was clean.
    assert!(implement.verification.iter().all(|c| c.status != aircore::execution::CheckStatus::Failed));

    // The explicit verify task passed too, and the whole run succeeded.
    let verify = result.tasks.iter().find(|t| t.kind == TaskKind::Verify).unwrap();
    assert_eq!(verify.state, TaskState::Succeeded);
    assert_eq!(result.status, ExecutionStatus::Succeeded);

    // The verify task consumed the implement task's ModifiedFiles artifact and
    // re-checked it: a detector check passed over the now-clean file.
    assert!(verify.verification.iter().any(|c| c.kind == aircore::planner::VerificationKind::Detectors
        && c.status == aircore::execution::CheckStatus::Passed));

    // The implement task recorded a modified_files artifact downstream consumed.
    assert!(implement.artifacts.iter().any(|a| a.kind == ArtifactKind::ModifiedFiles));
}

#[test]
fn regressing_edit_fails_verification_and_blocks_downstream() {
    // Start clean; the edit *introduces* an unwrap -> verification must reject it.
    let (_dir, mut engine) =
        synced_workspace(&[("Cargo.toml", CARGO), ("src/lib.rs", CLEAN)]);
    let plan = bug_fix_plan("src/lib.rs::run");

    let off = CLEAN.find("x.unwrap_or(0)").unwrap();
    let provider = StaticEdits {
        file: "src/lib.rs".to_string(),
        spans: vec![EditSpan {
            start_byte: off,
            end_byte: off + "x.unwrap_or(0)".len(),
            new_text: "x.unwrap()".to_string(),
        }],
    };

    let result = {
        let mut exec = Executor::with_backend(&mut engine, UserPolicy::Cloud, &provider, false);
        exec.execute(&plan)
    };

    let implement = result.tasks.iter().find(|t| t.kind == TaskKind::Implement).unwrap();
    assert_eq!(implement.state, TaskState::Failed);

    // The downstream verify task depends on implement -> blocked, never run.
    let verify = result.tasks.iter().find(|t| t.kind == TaskKind::Verify).unwrap();
    assert_eq!(verify.state, TaskState::Blocked);

    assert_eq!(result.status, ExecutionStatus::Failed);
}

#[test]
fn read_only_intent_executes_without_edits_and_succeeds() {
    let (_dir, mut engine) =
        synced_workspace(&[("Cargo.toml", CARGO), ("src/lib.rs", CLEAN)]);
    let plan = Planner::plan(&PlanRequest {
        goal: "explain how run works".to_string(),
        focus_symbol: Some("src/lib.rs::run".to_string()),
        ..Default::default()
    });

    let result = engine.execute_plan(&plan, UserPolicy::Cloud);

    // No mutating task in an explain plan, so nothing is skipped -> full success.
    assert!(result.tasks.iter().all(|t| t.state == TaskState::Succeeded));
    assert_eq!(result.status, ExecutionStatus::Succeeded);
    // The report task produced a report artifact.
    let report = result.tasks.iter().find(|t| t.kind == TaskKind::Report).unwrap();
    assert!(report.artifacts.iter().any(|a| a.name == "report"));
}

#[test]
fn execution_is_deterministic() {
    let (_d1, mut e1) = synced_workspace(&[("Cargo.toml", CARGO), ("src/lib.rs", CLEAN)]);
    let (_d2, mut e2) = synced_workspace(&[("Cargo.toml", CARGO), ("src/lib.rs", CLEAN)]);
    let plan = bug_fix_plan("src/lib.rs::run");

    let r1 = e1.execute_plan(&plan, UserPolicy::Cloud);
    let r2 = e2.execute_plan(&plan, UserPolicy::Cloud);

    // Ignore timing metadata; compare the structural outcome.
    let strip = |r: &aircore::execution::ExecutionResult| {
        r.tasks
            .iter()
            .map(|t| (t.id.clone(), t.kind, t.state, t.route))
            .collect::<Vec<_>>()
    };
    assert_eq!(strip(&r1), strip(&r2));
    assert_eq!(r1.status, r2.status);
    // The event stream is deterministic too (ignoring per-task timing).
    let ev = |r: &aircore::execution::ExecutionResult| {
        r.events.iter().map(|e| serde_json::to_value(&e.event).unwrap()).collect::<Vec<_>>()
    };
    assert_eq!(ev(&r1), ev(&r2));
}

#[test]
fn emits_lifecycle_and_artifact_events() {
    let (_dir, mut engine) =
        synced_workspace(&[("Cargo.toml", CARGO), ("src/lib.rs", BUGGY)]);
    let plan = bug_fix_plan("src/lib.rs::run");
    let result = engine.execute_plan(&plan, UserPolicy::Cloud);

    // Event sequence numbers are monotonic from zero.
    for (i, e) in result.events.iter().enumerate() {
        assert_eq!(e.seq, i);
    }

    // The stream opens and closes with plan-level events.
    assert!(matches!(result.events.first().map(|e| &e.event), Some(ExecutionEvent::PlanStarted { .. })));
    assert!(matches!(result.events.last().map(|e| &e.event), Some(ExecutionEvent::PlanFinished { .. })));

    // Lifecycle + artifact events were emitted.
    let has = |pred: fn(&ExecutionEvent) -> bool| result.events.iter().any(|e| pred(&e.event));
    assert!(has(|e| matches!(e, ExecutionEvent::TaskStarted { .. })));
    assert!(has(|e| matches!(e, ExecutionEvent::TaskStateChanged { .. })));
    assert!(has(|e| matches!(e, ExecutionEvent::TaskFinished { .. })));
    assert!(has(|e| matches!(e, ExecutionEvent::ArtifactProduced { .. })));

    // Every task that ran passed through Running at some point.
    assert!(result.events.iter().any(|e| matches!(
        &e.event,
        ExecutionEvent::TaskStateChanged { to: TaskState::Running, .. }
    )));
}

#[test]
fn verifying_state_is_entered_for_mutating_tasks() {
    let (_dir, mut engine) =
        synced_workspace(&[("Cargo.toml", CARGO), ("src/lib.rs", BUGGY)]);
    let plan = bug_fix_plan("src/lib.rs::run");
    let off = BUGGY.find("x.unwrap()").unwrap();
    let provider = StaticEdits {
        file: "src/lib.rs".to_string(),
        spans: vec![EditSpan {
            start_byte: off,
            end_byte: off + "x.unwrap()".len(),
            new_text: "x.unwrap_or(0)".to_string(),
        }],
    };

    let result = {
        let mut exec = Executor::with_backend(&mut engine, UserPolicy::Cloud, &provider, false);
        exec.execute(&plan)
    };

    // The implement task transitioned into Verifying and emitted verification
    // start/finish events.
    assert!(result.events.iter().any(|e| matches!(
        &e.event,
        ExecutionEvent::TaskStateChanged { to: TaskState::Verifying, .. }
    )));
    assert!(result.events.iter().any(|e| matches!(&e.event, ExecutionEvent::VerificationStarted { .. })));
    assert!(result.events.iter().any(|e| matches!(&e.event, ExecutionEvent::VerificationFinished { .. })));
}

#[test]
fn pluggable_tool_overrides_default() {
    use aircore::execution::{Tool, ToolCx, ToolOutcome, ToolRegistry};

    // A custom Analyze tool that records a sentinel state instead of the default.
    struct NoopAnalyze;
    impl Tool for NoopAnalyze {
        fn name(&self) -> &'static str {
            "noop-analyze"
        }
        fn run(&self, _task: &aircore::planner::PlanTask, _cx: &mut ToolCx) -> ToolOutcome {
            ToolOutcome::succeeded("custom analyze ran")
        }
    }

    let (_dir, mut engine) =
        synced_workspace(&[("Cargo.toml", CARGO), ("src/lib.rs", BUGGY)]);
    let plan = bug_fix_plan("src/lib.rs::run");

    let result = {
        let mut reg = ToolRegistry::with_defaults();
        reg.register(TaskKind::Analyze, Box::new(NoopAnalyze));
        let backend = aircore::model_runtime::NullBackend;
        let mut exec = Executor::with_backend(&mut engine, UserPolicy::Cloud, &backend, false);
        exec.set_registry(reg);
        exec.execute(&plan)
    };

    let analyze = result.tasks.iter().find(|t| t.kind == TaskKind::Analyze).unwrap();
    assert_eq!(analyze.summary, "custom analyze ran");
    // The custom tool produced no diagnostics (unlike the default analyzer).
    assert!(analyze.diagnostics.is_empty());
}
