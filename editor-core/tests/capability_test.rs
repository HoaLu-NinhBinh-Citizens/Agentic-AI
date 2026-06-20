//! Tests for the Capability Layer: the deterministic bridge between the Planner
//! (which requests capabilities) and the Tool Registry (which holds concrete
//! tools). The layer never calls an LLM — it maps a capability to registered
//! tool(s), runs them, and merges the outcome.

use aircore::capability::{Capability, CapabilityLayer};
use aircore::execution::{TaskState, ToolRegistry};
use aircore::planner::{PlanRequest, Planner, TaskKind};

#[test]
fn capability_maps_to_its_registry_tool_kind() {
    // The Planner requests capabilities; each resolves to a concrete tool kind
    // the unchanged registry is keyed by.
    assert_eq!(Capability::ReadCode.primary_kind(), TaskKind::Locate);
    assert_eq!(Capability::AnalyzeCode.primary_kind(), TaskKind::Analyze);
    assert_eq!(Capability::ModifyCode.primary_kind(), TaskKind::Implement);
    assert_eq!(Capability::VerifyCode.primary_kind(), TaskKind::Verify);
    assert_eq!(Capability::Report.primary_kind(), TaskKind::Report);

    // Only ModifyCode mutates source.
    assert!(Capability::ModifyCode.mutates());
    assert!(!Capability::ReadCode.mutates());
    assert!(!Capability::Report.mutates());

    // Mutating + explicit-verify capabilities gate on verification.
    assert!(Capability::ModifyCode.runs_verification());
    assert!(Capability::VerifyCode.runs_verification());
    assert!(!Capability::AnalyzeCode.runs_verification());
}

#[test]
fn planner_requests_capabilities_for_every_task() {
    // Every decomposition the Planner produces is expressed in capabilities, so
    // the Planner is fully decoupled from tool implementations.
    for goal in [
        "fix the crash in run",
        "add a new export flag",
        "refactor the retry loop",
        "review the auth module",
        "explain how indexing works",
    ] {
        let plan = Planner::plan(&PlanRequest {
            goal: goal.to_string(),
            focus_symbol: Some("src/lib.rs::run".to_string()),
            ..Default::default()
        });
        assert!(!plan.tasks.is_empty());
        // Each capability resolves to at least one registered tool kind.
        for t in &plan.tasks {
            assert!(!t.capability.tool_kinds().is_empty());
        }
    }
}

#[test]
fn layer_reports_skipped_when_no_tool_registered() {
    // With an empty registry, the capability has nothing to run -> Skipped, never
    // a fabricated success.
    let plan = Planner::plan(&PlanRequest {
        goal: "explain how run works".to_string(),
        focus_symbol: Some("src/lib.rs::run".to_string()),
        ..Default::default()
    });
    let task = &plan.tasks[0];

    let registry = ToolRegistry::empty();
    let layer = CapabilityLayer::new();

    // ToolCx needs an engine; build one over an empty temp workspace.
    let dir = tempfile::tempdir().unwrap();
    let mut engine = aircore::index::IndexEngine::open(dir.path()).unwrap();
    engine.sync().unwrap();
    let store = aircore::execution::ArtifactStore::default();

    let mut cx = aircore::execution::ToolCx {
        engine: &mut engine,
        policy: aircore::inference::UserPolicy::Cloud,
        edits: &aircore::execution::NoEdits,
        dry_run: false,
        upstream: &store,
    };
    let outcome = layer.execute(task.capability, task, &mut cx, &registry);
    assert_eq!(outcome.state, TaskState::Skipped);
}
