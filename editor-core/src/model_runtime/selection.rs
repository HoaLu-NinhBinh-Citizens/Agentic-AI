//! Model selection — the single place the route is decided.
//!
//! ADR-003's Policy Layer + Inference Router stay exactly as they are; this is the
//! one and only caller of [`inference::plan`] in the whole system. The Execution
//! Runtime no longer routes; it asks the backend (which delegates here), so the
//! "which model, which endpoint" decision exists in exactly one function.
//!
//! Selection reads only [`ModelTask::inference_task`] — the capability→task
//! mapping happened once, upstream, on `Capability::inference_task`. This module
//! knows nothing of planners or capabilities.

use crate::inference::{self, resolve_endpoint, Route, UserPolicy};

use super::dto::ModelTask;

/// Resolves the model route for a task under a policy.
pub struct ModelSelector;

impl ModelSelector {
    /// Resolve the route for `task` under `policy`. A task that needs no model
    /// collapses to a `model: None` route on the policy endpoint, so callers take
    /// one uniform path.
    pub fn select(task: &ModelTask, policy: UserPolicy) -> Route {
        match task.inference_task {
            Some(t) => inference::plan(policy, t),
            None => Route { model: None, endpoint: resolve_endpoint(policy) },
        }
    }
}
