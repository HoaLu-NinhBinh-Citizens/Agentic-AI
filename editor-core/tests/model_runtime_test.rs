//! Tests for the Model Runtime: the layer that treats LLMs as first-class runtime
//! components. It owns model selection (inference router), structured prompt
//! assembly, provider invocation, streaming, and response validation — and plugs
//! into the *unchanged* Execution Runtime through the existing `EditProvider` seam.
//!
//! No real model is called: a deterministic scripted provider stands in for one,
//! so the whole pipeline (select → assemble → invoke → stream → validate → apply)
//! is exercised without network or nondeterminism.

use std::fs;

use aircore::execution::{CheckStatus, Executor, TaskState};
use aircore::index::IndexEngine;
use aircore::inference::{Endpoint, Model, UserPolicy};
use aircore::model_runtime::prompt::{Prompt, PromptAssembler};
use aircore::model_runtime::provider::{
    CollectingSink, FinishReason, ModelProvider, ModelRequest, ModelResponse, ProviderError,
    ProviderRegistry, TokenSink,
};
use aircore::model_runtime::validation::{ResponseValidator, Validated};
use aircore::model_runtime::{ModelRuntime, RunOutcome};
use aircore::planner::{PlanRequest, PlanTask, Planner, TaskKind};

const CARGO: &str = "[package]\nname = \"demo\"\nversion = \"0.1.0\"\n";
const BUGGY: &str =
    "pub fn run() -> i32 {\n    let x: Option<i32> = Some(1);\n    x.unwrap()\n}\n";

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

fn bug_fix_plan(focus: &str) -> aircore::planner::Plan {
    Planner::plan(&PlanRequest {
        goal: "fix the crash in run".to_string(),
        focus_symbol: Some(focus.to_string()),
        ..Default::default()
    })
}

/// The first mutating task in a plan — what the Model Runtime acts on.
fn modify_task(plan: &aircore::planner::Plan) -> &PlanTask {
    plan.tasks
        .iter()
        .find(|t| t.capability.primary_kind() == TaskKind::Implement)
        .expect("plan has a mutating task")
}

/// A deterministic provider that streams a fixed response in small chunks. Stands
/// in for a real model so the pipeline can be tested without nondeterminism.
struct ScriptedProvider {
    response: String,
    finish: FinishReason,
}

impl ScriptedProvider {
    fn edit_json(file: &str, start: usize, end: usize, new_text: &str) -> Self {
        let response = format!(
            r#"{{"edits":[{{"file":"{file}","edits":[{{"startByte":{start},"endByte":{end},"newText":"{new_text}"}}]}}]}}"#
        );
        Self { response, finish: FinishReason::Stop }
    }
}

impl ModelProvider for ScriptedProvider {
    fn id(&self) -> &'static str {
        "scripted"
    }
    fn supports(&self, _model: Model) -> bool {
        true
    }
    fn generate(
        &self,
        req: &ModelRequest,
        sink: &mut dyn TokenSink,
    ) -> Result<ModelResponse, ProviderError> {
        // Stream in fixed-size chunks so we can prove streaming happened and that
        // the streamed text equals the returned text.
        let mut chunks = 0;
        for chunk in self.response.as_bytes().chunks(8) {
            let s = String::from_utf8_lossy(chunk);
            sink.on_token(&s);
            chunks += 1;
        }
        Ok(ModelResponse {
            model: req.model,
            text: self.response.clone(),
            finish: self.finish,
            chunks,
        })
    }
}

fn scripted_runtime(provider: ScriptedProvider, policy: UserPolicy) -> ModelRuntime {
    let mut providers = ProviderRegistry::empty();
    providers.register(Box::new(provider));
    ModelRuntime::with_providers(policy, providers)
}

// ───────────────────────────── Selection ───────────────────────────────────

#[test]
fn selection_uses_the_inference_router() {
    let plan = bug_fix_plan("src/lib.rs::run");
    let task = modify_task(&plan);

    // ModifyCode → Apply task. Cloud policy → Haiku on standard endpoint.
    let route = ModelRuntime::new(UserPolicy::Cloud).select(task);
    assert_eq!(route.model, Some(Model::Haiku45));
    assert_eq!(route.endpoint, Endpoint::CloudStandard);

    // Air-gap keeps it local — the router, not the runtime, enforces this.
    let route = ModelRuntime::new(UserPolicy::AirGap).select(task);
    assert_eq!(route.model, Some(Model::QwenLocal7B));
    assert_eq!(route.endpoint, Endpoint::Local);
}

// ───────────────────────────── Prompt assembly ──────────────────────────────

#[test]
fn prompt_combines_all_five_sources() {
    let plan = bug_fix_plan("src/lib.rs::run");
    let task = modify_task(&plan);
    let route = ModelRuntime::new(UserPolicy::Cloud).select(task);

    let prompt: Prompt = PromptAssembler::assemble(task, None, &route, UserPolicy::Cloud);

    // Every section is present and the metadata carries the execution facts.
    assert!(!prompt.system.is_empty());
    assert!(!prompt.capability.is_empty());
    assert_eq!(prompt.user_request, task.description);
    assert_eq!(prompt.metadata.task_id, task.id);
    assert_eq!(prompt.metadata.model, Some(Model::Haiku45));
    assert_eq!(prompt.metadata.policy, UserPolicy::Cloud);

    // The canonical render carries every section in a stable order.
    let rendered = prompt.render();
    for marker in ["<|system|>", "<|capability|>", "<|context|>", "<|request|>"] {
        assert!(rendered.contains(marker), "missing {marker}");
    }
}

// ───────────────────────────── Validation ───────────────────────────────────

fn response(text: &str, finish: FinishReason) -> ModelResponse {
    ModelResponse { model: Model::Haiku45, text: text.to_string(), finish, chunks: 1 }
}

#[test]
fn validation_accepts_well_formed_edits() {
    let r = response(
        r#"{"edits":[{"file":"a.rs","edits":[{"startByte":0,"endByte":3,"newText":"foo"}]}]}"#,
        FinishReason::Stop,
    );
    match ResponseValidator::validate_edits(&r) {
        Validated::Edits(e) => {
            assert_eq!(e.len(), 1);
            assert_eq!(e[0].file, "a.rs");
        }
        other => panic!("expected edits, got {other:?}"),
    }
}

#[test]
fn validation_rejects_malformed_json() {
    let r = response("not json at all", FinishReason::Stop);
    assert!(matches!(ResponseValidator::validate_edits(&r), Validated::Rejected(_)));
}

#[test]
fn validation_rejects_inverted_byte_range() {
    let r = response(
        r#"{"edits":[{"file":"a.rs","edits":[{"startByte":9,"endByte":2,"newText":"x"}]}]}"#,
        FinishReason::Stop,
    );
    assert!(matches!(ResponseValidator::validate_edits(&r), Validated::Rejected(_)));
}

#[test]
fn validation_rejects_truncated_response() {
    // Even valid-looking JSON must not be applied if the model was cut off.
    let r = response(
        r#"{"edits":[{"file":"a.rs","edits":[{"startByte":0,"endByte":3,"newText":"foo"}]}]}"#,
        FinishReason::Length,
    );
    assert!(matches!(ResponseValidator::validate_edits(&r), Validated::Rejected(_)));
}

#[test]
fn validation_treats_empty_response_as_empty_not_error() {
    let r = response("", FinishReason::Empty);
    assert!(matches!(ResponseValidator::validate_edits(&r), Validated::Empty));
}

// ───────────────────────────── Streaming ────────────────────────────────────

#[test]
fn streaming_text_equals_returned_text() {
    let plan = bug_fix_plan("src/lib.rs::run");
    let task = modify_task(&plan);
    let provider = ScriptedProvider::edit_json("src/lib.rs", 0, 3, "x");
    let runtime = scripted_runtime(provider, UserPolicy::Cloud);

    let mut sink = CollectingSink::default();
    let run = runtime.run(task, None, &mut sink);

    let response = run.response.expect("a provider was invoked");
    assert!(response.chunks > 1, "expected multiple streamed chunks");
    assert_eq!(sink.tokens.concat(), response.text);
}

// ───────────────────────────── Default provider ─────────────────────────────

#[test]
fn default_runtime_produces_no_edits() {
    let plan = bug_fix_plan("src/lib.rs::run");
    let task = modify_task(&plan);

    // The null provider serves every model but emits nothing → honest empty.
    let run = ModelRuntime::new(UserPolicy::Cloud).run(task, None, &mut aircore::model_runtime::provider::NullSink);
    assert!(matches!(run.outcome, RunOutcome::Empty));
}

#[test]
fn no_model_capability_short_circuits() {
    // A read-only plan's first task needs no model.
    let plan = Planner::plan(&PlanRequest {
        goal: "explain how run works".to_string(),
        focus_symbol: Some("src/lib.rs::run".to_string()),
        ..Default::default()
    });
    let locate = plan
        .tasks
        .iter()
        .find(|t| t.capability.primary_kind() == TaskKind::Locate)
        .unwrap();

    let run = ModelRuntime::new(UserPolicy::Cloud).run(locate, None, &mut aircore::model_runtime::provider::NullSink);
    assert!(matches!(run.outcome, RunOutcome::NoModel));
    assert_eq!(run.route.model, None);
}

// ───────────────────── Integration with the unchanged Executor ──────────────

#[test]
fn model_runtime_drives_a_real_mutation_through_the_executor() {
    let (_dir, mut engine) = synced_workspace(&[("Cargo.toml", CARGO), ("src/lib.rs", BUGGY)]);
    let plan = bug_fix_plan("src/lib.rs::run");

    // Scripted model returns the edit that removes the unwrap (clean verify).
    let off = BUGGY.find("x.unwrap()").unwrap();
    let provider = ScriptedProvider::edit_json(
        "src/lib.rs",
        off,
        off + "x.unwrap()".len(),
        "x.unwrap_or(0)",
    );
    let runtime = scripted_runtime(provider, UserPolicy::Cloud);

    // The executor is constructed exactly as before — the Model Runtime is just
    // the EditProvider. No executor/capability/planner change.
    let result = {
        let mut exec = Executor::with_options(&mut engine, UserPolicy::Cloud, &runtime, false);
        exec.execute(&plan)
    };

    let implement = result.tasks.iter().find(|t| t.kind == TaskKind::Implement).unwrap();
    assert_eq!(implement.state, TaskState::Succeeded, "{implement:?}");
    assert_eq!(implement.modified_files, vec!["src/lib.rs".to_string()]);
    assert!(implement.verification.iter().all(|c| c.status != CheckStatus::Failed));

    // The fix is actually on disk.
    let patched = fs::read_to_string(_dir.path().join("src/lib.rs")).unwrap();
    assert!(patched.contains("unwrap_or(0)"));
}

#[test]
fn invalid_model_output_is_not_applied() {
    let (_dir, mut engine) = synced_workspace(&[("Cargo.toml", CARGO), ("src/lib.rs", BUGGY)]);
    let plan = bug_fix_plan("src/lib.rs::run");

    // Model returns garbage — validation must reject it, so nothing is applied and
    // the mutating task is skipped (never a fabricated success).
    let runtime = scripted_runtime(
        ScriptedProvider { response: "I cannot help with that".to_string(), finish: FinishReason::Stop },
        UserPolicy::Cloud,
    );

    let result = {
        let mut exec = Executor::with_options(&mut engine, UserPolicy::Cloud, &runtime, false);
        exec.execute(&plan)
    };

    let implement = result.tasks.iter().find(|t| t.kind == TaskKind::Implement).unwrap();
    assert_eq!(implement.state, TaskState::Skipped);
    // The buggy code is untouched.
    let untouched = fs::read_to_string(_dir.path().join("src/lib.rs")).unwrap();
    assert!(untouched.contains("x.unwrap()"));
}
