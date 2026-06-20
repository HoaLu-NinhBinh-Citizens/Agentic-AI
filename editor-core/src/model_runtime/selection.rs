//! Model selection — the Model Runtime's owned use of the inference router.
//!
//! ADR-003's Policy Layer + Inference Router stay exactly as they are; this module
//! is the *only* caller of [`inference::plan`] inside the Model Runtime. Selection
//! used to be reached straight from the executor's edit path; concentrating it
//! here means "which model, on which endpoint" is decided in one place, alongside
//! invocation and validation, rather than scattered across the runtime.

use crate::capability::Capability;
use crate::inference::{self, resolve_endpoint, Route, Task as InfTask, UserPolicy};
use crate::planner::PlanTask;

/// Maps a requested capability to the model route for it, under a policy.
pub struct ModelSelector;

impl ModelSelector {
    /// Resolve the route for `task` under `policy`. Capabilities that need no model
    /// (read/verify) collapse to a `model: None` route on the policy endpoint, so
    /// the caller can uniformly skip invocation without a separate code path.
    pub fn select(task: &PlanTask, policy: UserPolicy) -> Route {
        match inference_task(task.capability) {
            Some(t) => inference::plan(policy, t),
            None => Route { model: None, endpoint: resolve_endpoint(policy) },
        }
    }
}

/// Which inference task (if any) a capability maps to. Mirrors the executor's
/// kind→task mapping, keyed on the capability the Capability Layer requested.
fn inference_task(capability: Capability) -> Option<InfTask> {
    match capability {
        Capability::ReadCode => None,
        Capability::AnalyzeCode => Some(InfTask::Chat),
        Capability::ModifyCode => Some(InfTask::Apply),
        Capability::VerifyCode => None,
        Capability::Report => Some(InfTask::Chat),
    }
}
