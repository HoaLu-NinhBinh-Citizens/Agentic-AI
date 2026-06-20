//! Model invocation — the bridge from a [`Prompt`] to a [`ModelResponse`].
//!
//! Invocation is deliberately thin: it resolves the selected model to a provider
//! and drives the streaming generation. It holds no policy and makes no model
//! choice — selection already happened. This is the one place that actually talks
//! to a provider, and thus the one place nondeterminism (the model's own output)
//! enters the otherwise deterministic runtime.

use crate::inference::Model;

use super::prompt::Prompt;
use super::provider::{ModelRequest, ModelResponse, ProviderError, ProviderRegistry, TokenSink};

/// Drives a single model interaction against the provider registry.
pub struct Invoker<'a> {
    providers: &'a ProviderRegistry,
}

impl<'a> Invoker<'a> {
    pub fn new(providers: &'a ProviderRegistry) -> Self {
        Self { providers }
    }

    /// Invoke `model` with `prompt`, streaming output to `sink`. Errors with
    /// [`ProviderError::NoProvider`] when no registered provider serves the model.
    pub fn invoke(
        &self,
        model: Model,
        prompt: &Prompt,
        sink: &mut dyn TokenSink,
    ) -> Result<ModelResponse, ProviderError> {
        let provider = self.providers.for_model(model).ok_or(ProviderError::NoProvider(model))?;
        let req = ModelRequest { model, endpoint: prompt.metadata.endpoint, prompt };
        provider.generate(&req, sink)
    }
}
