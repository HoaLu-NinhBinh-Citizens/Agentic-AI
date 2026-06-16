//! Policy Layer + Inference Router (ADR-003).
//!
//! Two pure stages, deliberately separate so a policy change never touches
//! routing logic and the router can never violate policy:
//!
//! 1. **Policy Layer** — `UserPolicy -> Endpoint` (the trust tier: where is it
//!    legally allowed to run?).
//! 2. **Inference Router** — `(Task, Endpoint) -> Route` (which model for this
//!    task, within the allowed endpoint?).
//!
//! Completion is ALWAYS local for latency, regardless of tier. The router only
//! ever sees the already-collapsed `Endpoint`, so it structurally cannot route
//! a chat to the cloud under `air_gap`.

use serde::{Deserialize, Serialize};

/// The user's trust tier. See ADR-003.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum UserPolicy {
    /// Code never leaves the machine.
    AirGap,
    /// Frontier model under a BAA + zero data retention.
    Compliance,
    /// Default: best quality/cost on standard cloud.
    Cloud,
}

/// The trust tier an inference call is allowed to use.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Endpoint {
    Local,
    CloudZdr,
    CloudStandard,
}

/// What we're running.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Task {
    Completion,
    /// A pure rename — no model needed (the classifier already produced edits).
    NextEditMechanical,
    /// A signature change — needs the model at each site.
    NextEditSemantic,
    Apply,
    Chat,
    Agent,
    Embedding,
}

/// The model to invoke. `None` in a `Route` means "no model call needed".
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Model {
    QwenLocal3B,
    QwenLocal7B,
    Haiku45,
    Sonnet46,
    LocalEmbed,
}

/// The resolved plan for one request.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct Route {
    /// `None` => no inference required (mechanical edit).
    pub model: Option<Model>,
    pub endpoint: Endpoint,
}

/// Policy Layer: collapse the user's tier to an endpoint.
pub fn resolve_endpoint(policy: UserPolicy) -> Endpoint {
    match policy {
        UserPolicy::AirGap => Endpoint::Local,
        UserPolicy::Compliance => Endpoint::CloudZdr,
        UserPolicy::Cloud => Endpoint::CloudStandard,
    }
}

/// Inference Router: pick the model for a task within an endpoint.
pub fn route(task: Task, endpoint: Endpoint) -> Route {
    let local = endpoint == Endpoint::Local;
    match task {
        // Latency wins: completion is always local, whatever the tier.
        Task::Completion => Route { model: Some(Model::QwenLocal3B), endpoint: Endpoint::Local },

        // Mechanical edits never call a model.
        Task::NextEditMechanical => Route { model: None, endpoint },

        // Heavier tasks honor the policy endpoint.
        Task::NextEditSemantic | Task::Apply => Route {
            model: Some(if local { Model::QwenLocal7B } else { Model::Haiku45 }),
            endpoint,
        },
        Task::Chat | Task::Agent => Route {
            model: Some(if local { Model::QwenLocal7B } else { Model::Sonnet46 }),
            endpoint,
        },
        Task::Embedding => Route { model: Some(Model::LocalEmbed), endpoint: Endpoint::Local },
    }
}

/// Full plan: policy + task in one call. This is what callers use.
pub fn plan(policy: UserPolicy, task: Task) -> Route {
    route(task, resolve_endpoint(policy))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn completion_is_always_local_regardless_of_policy() {
        for policy in [UserPolicy::AirGap, UserPolicy::Compliance, UserPolicy::Cloud] {
            let r = plan(policy, Task::Completion);
            assert_eq!(r.model, Some(Model::QwenLocal3B));
            assert_eq!(r.endpoint, Endpoint::Local);
        }
    }

    #[test]
    fn air_gap_keeps_chat_local() {
        let r = plan(UserPolicy::AirGap, Task::Chat);
        assert_eq!(r.endpoint, Endpoint::Local);
        assert_eq!(r.model, Some(Model::QwenLocal7B));
    }

    #[test]
    fn compliance_chat_uses_frontier_over_zdr() {
        let r = plan(UserPolicy::Compliance, Task::Chat);
        assert_eq!(r.endpoint, Endpoint::CloudZdr);
        assert_eq!(r.model, Some(Model::Sonnet46));
    }

    #[test]
    fn cloud_chat_uses_frontier_over_standard() {
        let r = plan(UserPolicy::Cloud, Task::Chat);
        assert_eq!(r.endpoint, Endpoint::CloudStandard);
        assert_eq!(r.model, Some(Model::Sonnet46));
    }

    #[test]
    fn apply_uses_fast_model_in_cloud_local_in_air_gap() {
        assert_eq!(plan(UserPolicy::Cloud, Task::Apply).model, Some(Model::Haiku45));
        assert_eq!(plan(UserPolicy::Compliance, Task::Apply).model, Some(Model::Haiku45));
        assert_eq!(plan(UserPolicy::AirGap, Task::Apply).model, Some(Model::QwenLocal7B));
    }

    #[test]
    fn mechanical_next_edit_needs_no_model() {
        let r = plan(UserPolicy::Cloud, Task::NextEditMechanical);
        assert_eq!(r.model, None);
    }

    #[test]
    fn router_cannot_send_air_gap_to_cloud() {
        // Whatever the task, an air_gap policy must never yield a cloud endpoint.
        for task in [
            Task::Completion,
            Task::NextEditSemantic,
            Task::Apply,
            Task::Chat,
            Task::Agent,
            Task::Embedding,
        ] {
            let r = plan(UserPolicy::AirGap, task);
            assert_eq!(r.endpoint, Endpoint::Local, "task {task:?} leaked off-device");
        }
    }
}
