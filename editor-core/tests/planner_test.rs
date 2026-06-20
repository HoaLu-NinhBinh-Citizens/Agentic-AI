//! Tests for the rule-based Planner: intent classification, intent-specific
//! task decomposition into a DAG, dependency-aware scheduling, per-task context
//! planning, and verification planning. The Planner is deterministic and never
//! calls the semantic engine or an LLM — same request in, same plan out.

use aircore::capability::Capability;
use aircore::planner::{
    classify_intent, Intent, Plan, PlanRequest, Planner, VerificationKind,
};

fn plan_for(goal: &str, focus: Option<&str>) -> Plan {
    Planner::plan(&PlanRequest {
        goal: goal.to_string(),
        focus_symbol: focus.map(str::to_string),
        files: vec![],
        max_tokens: None,
    })
}

#[test]
fn classifies_intent_by_keywords() {
    assert_eq!(classify_intent("fix the failing parse_header test"), Intent::BugFix);
    assert_eq!(classify_intent("implement a new export feature"), Intent::Feature);
    assert_eq!(classify_intent("refactor and simplify the retry loop"), Intent::Refactor);
    assert_eq!(classify_intent("audit this for security issues"), Intent::Review);
    assert_eq!(classify_intent("explain how indexing works"), Intent::Explain);
    // No keyword -> safe read-only default.
    assert_eq!(classify_intent("the cache layer"), Intent::Explain);
}

#[test]
fn bug_fix_decomposes_into_locate_diagnose_fix_verify() {
    let plan = plan_for("fix the crash in run", Some("src/main.rs::run"));
    assert_eq!(plan.intent, Intent::BugFix);

    // The Planner requests capabilities, not concrete tools.
    let caps: Vec<Capability> = plan.tasks.iter().map(|t| t.capability).collect();
    assert_eq!(
        caps,
        vec![
            Capability::ReadCode,
            Capability::AnalyzeCode,
            Capability::ModifyCode,
            Capability::VerifyCode
        ]
    );

    // Exactly one task mutates source.
    assert_eq!(plan.tasks.iter().filter(|t| t.produces_edits).count(), 1);

    // The final verify task gates on the full battery of checks.
    let verify = plan.tasks.last().unwrap();
    let checks: Vec<VerificationKind> = verify.verification.iter().map(|v| v.kind).collect();
    assert!(checks.contains(&VerificationKind::Compile));
    assert!(checks.contains(&VerificationKind::Detectors));
    assert!(checks.contains(&VerificationKind::Tests));
    assert!(checks.contains(&VerificationKind::Regression));
}

#[test]
fn tasks_form_a_dependency_chain_and_schedule_in_waves() {
    let plan = plan_for("fix the crash in run", Some("src/main.rs::run"));

    // Every non-root task depends on the immediately preceding one.
    assert!(plan.tasks[0].depends_on.is_empty());
    for win in plan.tasks.windows(2) {
        assert_eq!(win[1].depends_on, vec![win[0].id.clone()]);
    }

    // A linear chain schedules as one task per wave, in order.
    assert_eq!(plan.schedule.len(), plan.tasks.len());
    for (wave, task) in plan.schedule.iter().zip(&plan.tasks) {
        assert_eq!(wave, &vec![task.id.clone()]);
    }
}

#[test]
fn schedule_respects_dependencies() {
    // For every task, all of its dependencies appear in an earlier wave.
    let plan = plan_for("add a new flag to the parser", Some("src/p.rs::parse"));
    let wave_of = |id: &str| {
        plan.schedule
            .iter()
            .position(|w| w.iter().any(|x| x == id))
            .expect("task is scheduled")
    };
    for t in &plan.tasks {
        let tw = wave_of(&t.id);
        for dep in &t.depends_on {
            assert!(wave_of(dep) < tw, "dep {dep} must precede {}", t.id);
        }
    }
}

#[test]
fn read_only_intents_produce_no_edits_and_no_compile_checks() {
    for goal in ["review the auth module", "explain how the scheduler works"] {
        let plan = plan_for(goal, Some("src/x.rs::y"));
        assert!(!plan.intent.mutates());
        assert!(
            plan.tasks.iter().all(|t| !t.produces_edits),
            "read-only intent {:?} must not produce edits",
            plan.intent
        );
        // No compile/test/regression gates on a read-only plan.
        let all_checks: Vec<VerificationKind> =
            plan.tasks.iter().flat_map(|t| t.verification.iter().map(|v| v.kind)).collect();
        assert!(!all_checks.contains(&VerificationKind::Compile));
        assert!(!all_checks.contains(&VerificationKind::Tests));
    }
}

#[test]
fn each_task_plans_context_independently() {
    let plan = plan_for("explain how run works", Some("src/main.rs::run"));
    for t in &plan.tasks {
        // Every task carries its own context request grounded on the goal.
        assert!(t.context.query.as_deref() == Some("explain how run works"));
        assert!(t.context.max_tokens > 0);
    }
    // Focused tasks center on the provided symbol; the workspace-wide report task
    // drops focus.
    let locate = &plan.tasks[0];
    assert!(locate.context.focus.is_some());
    let report = plan.tasks.last().unwrap();
    assert_eq!(report.capability, Capability::Report);
    assert!(report.context.focus.is_none());
}

#[test]
fn planning_is_deterministic() {
    let a = plan_for("refactor the retry loop", Some("src/r.rs::retry"));
    let b = plan_for("refactor the retry loop", Some("src/r.rs::retry"));
    assert_eq!(
        serde_json::to_value(&a).unwrap(),
        serde_json::to_value(&b).unwrap()
    );
}
