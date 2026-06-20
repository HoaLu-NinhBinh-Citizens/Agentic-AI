//! Planner: turns a natural-language request into a deterministic execution plan.
//!
//! The Planner sits *above* the semantic engine. It does not resolve symbols,
//! retrieve snippets, or call an LLM — it produces a **contract** that the future
//! Execution Engine consumes. That contract is:
//!
//! 1. **Intent** — what class of work this is (bug fix, feature, refactor,
//!    review, explain), classified by keyword rules over the request text.
//! 2. **A task DAG** — the work decomposed into typed tasks with explicit
//!    `depends_on` edges, not a flat list. Decomposition is intent-specific.
//! 3. **A schedule** — the DAG flattened into dependency-ordered *waves* (tasks
//!    in the same wave have no unmet dependencies and may run concurrently).
//! 4. **Per-task context plans** — each task independently declares the semantic
//!    context it will need ([`ContextPlan`]: a focus, a retrieval query, a token
//!    budget). The Execution Engine feeds these to the [`SemanticEngine`].
//! 5. **Per-task verification plans** — which checks (compile, detectors, tests,
//!    regression) must pass after the task's edits.
//!
//! Everything here is pure and rule-based: same request in, same plan out. The
//! LLM (and the semantic engine itself) only enter at execution time.
//!
//! [`SemanticEngine`]: crate::semantic::SemanticEngine

use serde::{Deserialize, Serialize};

use crate::semantic::FocusSpec;

/// Default per-task context budget (tokens) when the request doesn't set one.
const DEFAULT_TASK_TOKENS: usize = 4000;

/// The class of work a request describes. Drives task decomposition.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Intent {
    /// Fix incorrect behavior: a crash, wrong output, failing test, regression.
    BugFix,
    /// Add new capability: a function, endpoint, option, module.
    Feature,
    /// Improve structure without changing behavior: rename, extract, simplify.
    Refactor,
    /// Read-only assessment: review, audit, security pass — no edits.
    Review,
    /// Read-only understanding: explain, document, trace — no edits.
    Explain,
}

impl Intent {
    pub fn as_str(self) -> &'static str {
        match self {
            Intent::BugFix => "bug_fix",
            Intent::Feature => "feature",
            Intent::Refactor => "refactor",
            Intent::Review => "review",
            Intent::Explain => "explain",
        }
    }

    /// Whether tasks for this intent are expected to modify source. Read-only
    /// intents (review, explain) never produce edits, so they carry no
    /// compile/test verification.
    pub fn mutates(self) -> bool {
        matches!(self, Intent::BugFix | Intent::Feature | Intent::Refactor)
    }
}

/// What kind of step a task is. The Execution Engine dispatches on this.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum TaskKind {
    /// Gather the relevant symbols/files for the work (semantic context).
    Locate,
    /// Understand or diagnose: run detectors, read the resolved context.
    Analyze,
    /// Produce a change set (edits). The only kind that mutates source.
    Implement,
    /// Run verification checks over the workspace after edits.
    Verify,
    /// Produce a human-facing answer (review notes / explanation). No edits.
    Report,
}

/// A check the Execution Engine must run (and pass) after a task's edits.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum VerificationKind {
    /// The workspace still compiles / type-checks.
    Compile,
    /// The bug detectors report no new findings (and resolve the targeted ones).
    Detectors,
    /// The test suite passes.
    Tests,
    /// Behavior outside the change is unchanged (no test that passed now fails).
    Regression,
}

/// One verification check with a human-readable rationale.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VerificationCheck {
    pub kind: VerificationKind,
    pub description: String,
}

impl VerificationCheck {
    fn new(kind: VerificationKind, description: &str) -> Self {
        Self { kind, description: description.to_string() }
    }
}

/// A task's independent request for semantic context. The Execution Engine maps
/// this onto a [`SemanticRequest`](crate::semantic::SemanticRequest) (when
/// `focus` is set) and/or a hybrid-retrieval query — the Planner never resolves
/// it itself.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ContextPlan {
    /// What to center context on. `None` for tasks that operate on the whole
    /// workspace (e.g. running tests) rather than a specific symbol.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub focus: Option<FocusSpec>,
    /// Free-text query to seed hybrid retrieval (and to ground a `None` focus).
    #[serde(skip_serializing_if = "Option::is_none")]
    pub query: Option<String>,
    /// Token budget the Execution Engine should pack this context into.
    pub max_tokens: usize,
    /// Whether resolved callee *bodies* are needed (editing/explaining) or just
    /// their signatures (locating/scoping).
    pub include_bodies: bool,
    /// Files the task is expected to read or touch, if known up front.
    pub files: Vec<String>,
}

/// One node in the execution DAG.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PlanTask {
    /// Stable id within this plan (`"t1"`, `"t2"`, …). Referenced by `depends_on`.
    pub id: String,
    pub kind: TaskKind,
    pub title: String,
    pub description: String,
    /// The context this task requests, independently of every other task.
    pub context: ContextPlan,
    /// Ids of tasks that must complete before this one. Empty = a root.
    pub depends_on: Vec<String>,
    /// Checks that must pass after this task. Empty for read-only tasks.
    pub verification: Vec<VerificationCheck>,
    /// True if the task emits a change set the Execution Engine applies.
    pub produces_edits: bool,
}

/// The Planner's output: the contract the Execution Engine consumes.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Plan {
    pub intent: Intent,
    /// The original request, verbatim.
    pub goal: String,
    /// Tasks in declaration order. Edges live in `PlanTask::depends_on`.
    pub tasks: Vec<PlanTask>,
    /// Dependency-ordered waves of task ids: every task in `schedule[i]` has all
    /// its dependencies satisfied by waves `0..i`, so a wave may run concurrently.
    pub schedule: Vec<Vec<String>>,
}

/// A planning request. Deliberately small: a goal plus optional grounding the
/// caller already knows (a focus symbol, candidate files, a budget).
#[derive(Debug, Clone, Default, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PlanRequest {
    /// The natural-language ask, e.g. "fix the panic in parse_header".
    pub goal: String,
    /// A focus symbol's qualified name, if the caller already pinned one.
    #[serde(default)]
    pub focus_symbol: Option<String>,
    /// Files the caller flagged as relevant (e.g. the open editor tab).
    #[serde(default)]
    pub files: Vec<String>,
    /// Per-task context budget. Falls back to [`DEFAULT_TASK_TOKENS`].
    #[serde(default)]
    pub max_tokens: Option<usize>,
}

/// Lowercased keyword sets per intent. Order of the outer array is the tie-break
/// priority when two intents score equally (earlier wins).
const INTENT_KEYWORDS: &[(Intent, &[&str])] = &[
    (
        Intent::BugFix,
        &[
            "fix", "bug", "broken", "crash", "panic", "error", "fails", "failing",
            "incorrect", "wrong", "regression", "exception", "defect", "npe",
            "segfault", "hang", "deadlock",
        ],
    ),
    (
        Intent::Refactor,
        &[
            "refactor", "rename", "restructure", "cleanup", "clean up", "extract",
            "simplify", "deduplicate", "dedupe", "reorganize", "decouple", "inline",
            "tidy",
        ],
    ),
    (
        Intent::Feature,
        &[
            "add", "implement", "create", "build", "new", "feature", "support",
            "introduce", "enable", "integrate",
        ],
    ),
    (
        Intent::Review,
        &[
            "review", "audit", "inspect", "vet", "assess", "evaluate", "critique",
            "security review", "code review",
        ],
    ),
    (
        Intent::Explain,
        &[
            "explain", "describe", "document", "understand", "how does", "what does",
            "why does", "walk through", "summarize", "trace", "clarify",
        ],
    ),
];

/// Classify a request's intent by keyword scoring. Each matched keyword scores 1
/// for its intent; the highest total wins, ties broken by [`INTENT_KEYWORDS`]
/// order. With no keyword match, default to [`Intent::Explain`] — the safest
/// (read-only) interpretation of an ambiguous ask.
pub fn classify_intent(goal: &str) -> Intent {
    let hay = goal.to_lowercase();
    let mut best = Intent::Explain;
    let mut best_score = 0usize;
    for (intent, words) in INTENT_KEYWORDS {
        let score = words.iter().filter(|w| hay.contains(*w)).count();
        if score > best_score {
            best_score = score;
            best = *intent;
        }
    }
    best
}

/// The deterministic, rule-based planner. Holds no state; `plan` is pure.
pub struct Planner;

impl Planner {
    /// Build the execution plan for a request. Pure: identical requests yield
    /// identical plans (including task ids and schedule).
    pub fn plan(req: &PlanRequest) -> Plan {
        let intent = classify_intent(&req.goal);
        let b = TaskListBuilder::new(req);

        let tasks = match intent {
            Intent::BugFix => b.bug_fix(),
            Intent::Feature => b.feature(),
            Intent::Refactor => b.refactor(),
            Intent::Review => b.review(),
            Intent::Explain => b.explain(),
        };

        let schedule = compute_schedule(&tasks);
        Plan { intent, goal: req.goal.clone(), tasks, schedule }
    }
}

/// Accumulates tasks, assigning sequential ids and a per-request context budget.
struct TaskListBuilder<'a> {
    req: &'a PlanRequest,
    budget: usize,
    next: usize,
    tasks: Vec<PlanTask>,
}

impl<'a> TaskListBuilder<'a> {
    fn new(req: &'a PlanRequest) -> Self {
        Self {
            req,
            budget: req.max_tokens.unwrap_or(DEFAULT_TASK_TOKENS),
            next: 0,
            tasks: Vec::new(),
        }
    }

    /// A context plan grounded on the request's focus symbol (if any) and goal.
    /// `bodies` distinguishes locating (signatures suffice) from editing
    /// (full callee bodies needed).
    fn ctx(&self, bodies: bool) -> ContextPlan {
        ContextPlan {
            focus: self.req.focus_symbol.clone().map(FocusSpec::Symbol),
            query: Some(self.req.goal.clone()),
            max_tokens: self.budget,
            include_bodies: bodies,
            files: self.req.files.clone(),
        }
    }

    /// A context plan for a workspace-wide step (no focus, no callee bodies).
    fn ctx_workspace(&self) -> ContextPlan {
        ContextPlan {
            focus: None,
            query: Some(self.req.goal.clone()),
            max_tokens: self.budget,
            include_bodies: false,
            files: self.req.files.clone(),
        }
    }

    /// Append a task, returning its id so callers can wire dependencies.
    fn push(
        &mut self,
        kind: TaskKind,
        title: &str,
        description: &str,
        context: ContextPlan,
        depends_on: &[&str],
        verification: Vec<VerificationCheck>,
        produces_edits: bool,
    ) -> String {
        self.next += 1;
        let id = format!("t{}", self.next);
        self.tasks.push(PlanTask {
            id: id.clone(),
            kind,
            title: title.to_string(),
            description: description.to_string(),
            context,
            depends_on: depends_on.iter().map(|s| s.to_string()).collect(),
            verification,
            produces_edits,
        });
        id
    }

    fn bug_fix(mut self) -> Vec<PlanTask> {
        let locate = self.push(
            TaskKind::Locate,
            "Locate the defect",
            "Resolve the focus symbol and its callees to pin where the wrong \
             behavior originates.",
            self.ctx(false),
            &[],
            vec![],
            false,
        );
        let diagnose = self.push(
            TaskKind::Analyze,
            "Diagnose the root cause",
            "Run detectors over the located code and read the resolved context \
             to identify the faulty logic.",
            self.ctx(true),
            &[&locate],
            vec![VerificationCheck::new(
                VerificationKind::Detectors,
                "Detector findings name the suspect lines",
            )],
            false,
        );
        let fix = self.push(
            TaskKind::Implement,
            "Apply the fix",
            "Produce a minimal edit that corrects the root cause without changing \
             unrelated behavior.",
            self.ctx(true),
            &[&diagnose],
            vec![],
            true,
        );
        self.push(
            TaskKind::Verify,
            "Verify the fix",
            "Confirm the fix compiles, clears the targeted findings, passes tests, \
             and introduces no regression.",
            self.ctx_workspace(),
            &[&fix],
            full_verification(),
            false,
        );
        self.tasks
    }

    fn feature(mut self) -> Vec<PlanTask> {
        let locate = self.push(
            TaskKind::Locate,
            "Locate insertion points",
            "Find the modules and symbols the new capability hooks into.",
            self.ctx(false),
            &[],
            vec![],
            false,
        );
        let design = self.push(
            TaskKind::Analyze,
            "Design the change",
            "Read the resolved context and decide the shape of the new code \
             (signatures, call sites, data flow).",
            self.ctx(true),
            &[&locate],
            vec![],
            false,
        );
        let implement = self.push(
            TaskKind::Implement,
            "Implement the feature",
            "Produce the edits that add the capability, following existing \
             patterns in the located code.",
            self.ctx(true),
            &[&design],
            vec![],
            true,
        );
        self.push(
            TaskKind::Verify,
            "Verify the feature",
            "Confirm the new code compiles and the test suite passes.",
            self.ctx_workspace(),
            &[&implement],
            vec![
                VerificationCheck::new(VerificationKind::Compile, "Workspace compiles"),
                VerificationCheck::new(VerificationKind::Tests, "Test suite passes"),
            ],
            false,
        );
        self.tasks
    }

    fn refactor(mut self) -> Vec<PlanTask> {
        let locate = self.push(
            TaskKind::Locate,
            "Locate the refactor target",
            "Resolve the target symbol and everything that depends on it so the \
             change set is complete.",
            self.ctx(false),
            &[],
            vec![],
            false,
        );
        let plan_transform = self.push(
            TaskKind::Analyze,
            "Plan the transformation",
            "Decide the structural change and enumerate every call site that must \
             move with it.",
            self.ctx(true),
            &[&locate],
            vec![],
            false,
        );
        let apply = self.push(
            TaskKind::Implement,
            "Apply the refactor",
            "Produce the edits that restructure the code while preserving behavior.",
            self.ctx(true),
            &[&plan_transform],
            vec![],
            true,
        );
        self.push(
            TaskKind::Verify,
            "Verify behavior is preserved",
            "Confirm the refactor compiles, clears detectors, passes tests, and \
             changes no observable behavior.",
            self.ctx_workspace(),
            &[&apply],
            full_verification(),
            false,
        );
        self.tasks
    }

    fn review(mut self) -> Vec<PlanTask> {
        let locate = self.push(
            TaskKind::Locate,
            "Locate the code under review",
            "Resolve the focus symbol and its dependencies into review scope.",
            self.ctx(false),
            &[],
            vec![],
            false,
        );
        let analyze = self.push(
            TaskKind::Analyze,
            "Analyze for issues",
            "Run detectors and inspect the resolved context for bugs, risks, and \
             smells.",
            self.ctx(true),
            &[&locate],
            vec![VerificationCheck::new(
                VerificationKind::Detectors,
                "Detector pass completed over the reviewed code",
            )],
            false,
        );
        self.push(
            TaskKind::Report,
            "Report findings",
            "Summarize the review: findings, severity, and suggested fixes. No \
             edits are applied.",
            self.ctx_workspace(),
            &[&analyze],
            vec![],
            false,
        );
        self.tasks
    }

    fn explain(mut self) -> Vec<PlanTask> {
        let locate = self.push(
            TaskKind::Locate,
            "Locate the subject",
            "Resolve the focus symbol and the callees it depends on.",
            self.ctx(false),
            &[],
            vec![],
            false,
        );
        let gather = self.push(
            TaskKind::Analyze,
            "Gather supporting context",
            "Pull the resolved callee bodies and imports needed to explain the \
             behavior end to end.",
            self.ctx(true),
            &[&locate],
            vec![],
            false,
        );
        self.push(
            TaskKind::Report,
            "Explain",
            "Produce the explanation from the gathered context. No edits are \
             applied.",
            self.ctx_workspace(),
            &[&gather],
            vec![],
            false,
        );
        self.tasks
    }
}

/// The full post-edit verification gate used by behavior-changing intents.
fn full_verification() -> Vec<VerificationCheck> {
    vec![
        VerificationCheck::new(VerificationKind::Compile, "Workspace compiles"),
        VerificationCheck::new(
            VerificationKind::Detectors,
            "No new detector findings introduced",
        ),
        VerificationCheck::new(VerificationKind::Tests, "Test suite passes"),
        VerificationCheck::new(
            VerificationKind::Regression,
            "No previously-passing behavior regressed",
        ),
    ]
}

/// Flatten the task DAG into dependency-ordered waves (Kahn's algorithm). Tasks
/// within a wave have all dependencies satisfied by earlier waves and may run
/// concurrently. Ordering inside a wave follows task declaration order, so the
/// schedule is deterministic. A dependency cycle (which the rule-based builders
/// never produce) would leave tasks unscheduled; we append any such remainder as
/// a final wave rather than loop forever.
fn compute_schedule(tasks: &[PlanTask]) -> Vec<Vec<String>> {
    let mut done: Vec<bool> = vec![false; tasks.len()];
    let mut waves: Vec<Vec<String>> = Vec::new();
    let mut remaining = tasks.len();

    while remaining > 0 {
        let mut wave: Vec<String> = Vec::new();
        let mut wave_idx: Vec<usize> = Vec::new();
        for (i, t) in tasks.iter().enumerate() {
            if done[i] {
                continue;
            }
            let ready = t.depends_on.iter().all(|dep| {
                tasks
                    .iter()
                    .position(|x| &x.id == dep)
                    .map(|j| done[j])
                    .unwrap_or(true) // unknown dep id => treat as satisfied
            });
            if ready {
                wave.push(t.id.clone());
                wave_idx.push(i);
            }
        }

        if wave.is_empty() {
            // Cycle / unsatisfiable deps: schedule whatever is left, once.
            let leftover: Vec<String> = tasks
                .iter()
                .enumerate()
                .filter(|(i, _)| !done[*i])
                .map(|(_, t)| t.id.clone())
                .collect();
            if !leftover.is_empty() {
                waves.push(leftover);
            }
            break;
        }

        for i in &wave_idx {
            done[*i] = true;
        }
        remaining -= wave.len();
        waves.push(wave);
    }

    waves
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn classifies_each_intent() {
        assert_eq!(classify_intent("fix the panic in parse_header"), Intent::BugFix);
        assert_eq!(classify_intent("add a retry option to the client"), Intent::Feature);
        assert_eq!(classify_intent("rename Foo to Bar and extract the helper"), Intent::Refactor);
        assert_eq!(classify_intent("review this module for security issues"), Intent::Review);
        assert_eq!(classify_intent("explain how the scheduler works"), Intent::Explain);
    }

    #[test]
    fn ambiguous_request_defaults_to_explain() {
        assert_eq!(classify_intent("the scheduler"), Intent::Explain);
    }

    #[test]
    fn schedule_is_linear_chain_for_default_decomposition() {
        let plan = Planner::plan(&PlanRequest {
            goal: "fix the crash".to_string(),
            focus_symbol: Some("src/a.rs::run".to_string()),
            ..Default::default()
        });
        // Each rule-based decomposition is a 4-stage chain -> 4 single-task waves.
        assert_eq!(plan.schedule.len(), plan.tasks.len());
        assert!(plan.schedule.iter().all(|w| w.len() == 1));
    }
}
