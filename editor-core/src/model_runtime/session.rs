//! Model sessions — a lightweight [`ModelSession`] → [`Conversation`] →
//! invocation hierarchy.
//!
//! This is the *shape* the interactive editor and the future agent runtime drive,
//! introduced now so it stabilizes before those features land. It deliberately
//! implements **no** memory or multi-agent behavior:
//!
//! * A [`ModelSession`] owns the long-lived runtime (policy + providers). One
//!   session ≈ one editor window / one user trust context.
//! * A [`Conversation`] is a turn sequence under a session. It records each
//!   [`Invocation`] in an in-memory history.
//! * History is recorded but **not yet fed back** into prompt assembly — that is
//!   the Memory seam (the [`History`]/[`Memory`] prompt sections). Wiring it is a
//!   later milestone, not this one.
//!
//! The Execution Runtime does not use this; it drives the stateless
//! [`ModelBackend`](super::ModelBackend) port directly. Sessions are for
//! conversational / agentic callers.
//!
//! [`History`]: super::prompt::SectionKind::History
//! [`Memory`]: super::prompt::SectionKind::Memory

use crate::inference::UserPolicy;

use super::provider::{ProviderManager, TokenSink};
use super::{ModelRequest, ModelResult, ModelRuntime};

/// One recorded turn: the request's task id and the result it produced.
pub struct Invocation {
    /// The task id the request carried (stable handle for telemetry).
    pub task_id: String,
    /// The full pipeline result for this turn.
    pub result: ModelResult,
}

/// A long-lived model context: policy + providers, shared across conversations.
pub struct ModelSession {
    runtime: ModelRuntime,
}

impl ModelSession {
    /// A session with the default provider manager.
    pub fn new(policy: UserPolicy) -> Self {
        Self { runtime: ModelRuntime::new(policy) }
    }

    /// A session over a fully-configured [`ProviderManager`].
    pub fn with_manager(policy: UserPolicy, providers: ProviderManager) -> Self {
        Self { runtime: ModelRuntime::with_manager(policy, providers) }
    }

    /// The underlying runtime (for callers that want one-off, stateless runs).
    pub fn runtime(&self) -> &ModelRuntime {
        &self.runtime
    }

    /// Open a fresh conversation under this session.
    pub fn conversation(&self) -> Conversation<'_> {
        Conversation { session: self, history: Vec::new() }
    }
}

/// A turn sequence under a [`ModelSession`]. Accumulates invocation history; that
/// history is the seam future memory integration will read and replay into the
/// prompt — today it is recorded only.
pub struct Conversation<'a> {
    session: &'a ModelSession,
    history: Vec<Invocation>,
}

impl Conversation<'_> {
    /// Run one turn, streaming output to `sink`, and record it. Returns the just-
    /// recorded invocation. (History is not yet injected back into the prompt.)
    pub fn invoke(&mut self, req: &ModelRequest, sink: &mut dyn TokenSink) -> &Invocation {
        let result = self.session.runtime.run(req, sink);
        self.history.push(Invocation { task_id: req.task.id.clone(), result });
        self.history.last().expect("just pushed")
    }

    /// Every turn so far, in order.
    pub fn history(&self) -> &[Invocation] {
        &self.history
    }

    /// Number of turns recorded.
    pub fn len(&self) -> usize {
        self.history.len()
    }

    pub fn is_empty(&self) -> bool {
        self.history.is_empty()
    }
}
