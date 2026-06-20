//! The common provider interface and streaming.
//!
//! Every language model — local Qwen, cloud Haiku/Sonnet, a future provider —
//! reaches the runtime through one trait, [`ModelProvider`]. The runtime selects a
//! [`Model`](crate::inference::Model); the [`ProviderRegistry`] resolves that to a
//! concrete provider. Adding a provider is registering one more `Box<dyn
//! ModelProvider>` — no runtime change.
//!
//! Output is streamed token-by-token through a [`TokenSink`] so the editor can
//! render as the model produces. The full text is also returned in the
//! [`ModelResponse`], so a non-streaming caller passes [`NullSink`] and ignores
//! the stream entirely.

use crate::inference::{Endpoint, Model};

use super::prompt::Prompt;

/// Why a generation stopped. Carried on the response so validation and telemetry
/// can distinguish a complete answer from a truncated one.
#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Serialize)]
#[serde(rename_all = "snake_case")]
pub enum FinishReason {
    /// The model emitted a natural end.
    Stop,
    /// The provider hit its output length cap.
    Length,
    /// The provider produced nothing (e.g. the default null provider).
    Empty,
}

/// One model interaction's request. Holds the rendered prompt and the resolved
/// target; providers that want the structured prompt read [`ModelRequest::prompt`].
pub struct ModelRequest<'a> {
    pub model: Model,
    pub endpoint: Endpoint,
    pub prompt: &'a Prompt,
}

impl ModelRequest<'_> {
    /// The canonical flattened prompt text (see [`Prompt::render`]).
    pub fn rendered(&self) -> String {
        self.prompt.render()
    }
}

/// A model interaction's result. The streamed text is also accumulated here so the
/// caller has the whole response without reassembling the stream.
#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize)]
pub struct ModelResponse {
    pub model: Model,
    pub text: String,
    pub finish: FinishReason,
    /// How many chunks the provider streamed — lets a caller assert streaming
    /// happened without inspecting wall-clock timing (which would be nondeterministic).
    pub chunks: usize,
}

/// A provider failure. Kept coarse: the Model Runtime turns any error into "no
/// validated edits", never a fabricated success.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ProviderError {
    /// No registered provider serves the selected model.
    NoProvider(Model),
    /// The provider could not produce a response (network, backend, etc.).
    Backend(String),
}

impl std::fmt::Display for ProviderError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            ProviderError::NoProvider(m) => write!(f, "no provider registered for {m:?}"),
            ProviderError::Backend(e) => write!(f, "provider backend error: {e}"),
        }
    }
}

impl std::error::Error for ProviderError {}

/// Receives output as the provider streams it. The runtime drives this; an editor
/// implements it to render incrementally.
pub trait TokenSink: Send {
    fn on_token(&mut self, token: &str);
}

/// A sink that discards everything — for callers that only want the final text.
pub struct NullSink;
impl TokenSink for NullSink {
    fn on_token(&mut self, _token: &str) {}
}

/// A sink that accumulates the stream into a string (handy for tests and for
/// proving the streamed text equals the returned text).
#[derive(Default)]
pub struct CollectingSink {
    pub tokens: Vec<String>,
}
impl TokenSink for CollectingSink {
    fn on_token(&mut self, token: &str) {
        self.tokens.push(token.to_string());
    }
}

/// A language-model provider behind the common interface.
pub trait ModelProvider: Send + Sync {
    /// Stable identifier, e.g. `"local"`, `"anthropic"`.
    fn id(&self) -> &'static str;
    /// Whether this provider serves `model`.
    fn supports(&self, model: Model) -> bool;
    /// Generate a response, streaming each chunk to `sink`. The returned
    /// [`ModelResponse::text`] MUST equal the concatenation of streamed chunks.
    fn generate(
        &self,
        req: &ModelRequest,
        sink: &mut dyn TokenSink,
    ) -> Result<ModelResponse, ProviderError>;
}

/// Resolves a selected [`Model`] to the registered provider that serves it. First
/// match wins, so a later-registered provider can shadow an earlier one for a model.
pub struct ProviderRegistry {
    providers: Vec<Box<dyn ModelProvider>>,
}

impl ProviderRegistry {
    /// An empty registry — every model resolves to "no provider" until one is
    /// registered. Use [`with_defaults`](Self::with_defaults) for the honest stub.
    pub fn empty() -> Self {
        Self { providers: Vec::new() }
    }

    /// The default registry: a single [`NullProvider`] covering every model. It
    /// produces no output, so — exactly like the executor's `NoEdits` seam — a
    /// mutating task yields nothing rather than a fabricated edit. Real providers
    /// are registered over it.
    pub fn with_defaults() -> Self {
        let mut reg = Self::empty();
        reg.register(Box::new(NullProvider));
        reg
    }

    /// Add a provider. Registered providers are consulted in insertion order.
    pub fn register(&mut self, provider: Box<dyn ModelProvider>) -> &mut Self {
        self.providers.push(provider);
        self
    }

    /// The provider serving `model`, if any.
    pub fn for_model(&self, model: Model) -> Option<&dyn ModelProvider> {
        self.providers.iter().rev().find(|p| p.supports(model)).map(|p| p.as_ref())
    }
}

impl Default for ProviderRegistry {
    fn default() -> Self {
        Self::with_defaults()
    }
}

/// The honest default: serves every model but generates nothing. Keeps the
/// Model Runtime wired end-to-end without a real backend — mutating tasks become
/// `Skipped` (no edits), never fabricated.
pub struct NullProvider;

impl ModelProvider for NullProvider {
    fn id(&self) -> &'static str {
        "null"
    }
    fn supports(&self, _model: Model) -> bool {
        true
    }
    fn generate(
        &self,
        req: &ModelRequest,
        _sink: &mut dyn TokenSink,
    ) -> Result<ModelResponse, ProviderError> {
        Ok(ModelResponse { model: req.model, text: String::new(), finish: FinishReason::Empty, chunks: 0 })
    }
}
