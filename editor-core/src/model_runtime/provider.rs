//! The common provider interface, the streaming sink, and the Provider Manager.
//!
//! Every language model — local Qwen, cloud Haiku/Sonnet, a future provider —
//! reaches the runtime through one trait, [`ModelProvider`]. The runtime selects a
//! [`Model`](crate::inference::Model); the [`ProviderManager`] resolves that to a
//! concrete provider for the policy-chosen [`Endpoint`], honoring a
//! [`CircuitBreaker`] and a [`RetryPolicy`]. Adding a provider is registering one
//! more `Box<dyn ModelProvider>` — no runtime change.
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
/// target; providers that want the structured prompt read [`ProviderRequest::prompt`].
/// This is the *provider-facing* request — distinct from the high-level
/// [`ModelRequest`](super::ModelRequest) the runtime port accepts.
pub struct ProviderRequest<'a> {
    pub model: Model,
    pub endpoint: Endpoint,
    pub prompt: &'a Prompt,
}

impl ProviderRequest<'_> {
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
/// validated output", never a fabricated success.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ProviderError {
    /// No registered provider serves the selected model on the chosen endpoint.
    NoProvider(Model),
    /// The provider could not produce a response (network, backend, etc.).
    Backend(String),
    /// The circuit breaker is open for this model — the call was not attempted.
    CircuitOpen(Model),
}

impl ProviderError {
    /// Whether retrying could plausibly succeed. A missing provider or an open
    /// circuit will not change between immediate attempts; a backend blip might.
    fn is_retryable(&self) -> bool {
        matches!(self, ProviderError::Backend(_))
    }
}

impl std::fmt::Display for ProviderError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            ProviderError::NoProvider(m) => write!(f, "no provider registered for {m:?}"),
            ProviderError::Backend(e) => write!(f, "provider backend error: {e}"),
            ProviderError::CircuitOpen(m) => write!(f, "circuit open for {m:?}"),
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
    /// Whether this provider serves `model` on `endpoint`. Defaults to
    /// [`supports`](Self::supports) (endpoint-agnostic) — the seam a provider that
    /// is, say, cloud-only or local-only overrides without breaking others.
    fn serves(&self, model: Model, _endpoint: Endpoint) -> bool {
        self.supports(model)
    }
    /// Generate a response, streaming each chunk to `sink`. The returned
    /// [`ModelResponse::text`] MUST equal the concatenation of streamed chunks.
    fn generate(
        &self,
        req: &ProviderRequest,
        sink: &mut dyn TokenSink,
    ) -> Result<ModelResponse, ProviderError>;
}

/// Resolves a selected [`Model`] (on an [`Endpoint`]) to the registered provider
/// that serves it. The most recently registered match wins, so a later-registered
/// provider shadows an earlier one for the same model.
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
    /// produces no output, so a mutating task yields nothing rather than a
    /// fabricated edit. Real providers are registered over it.
    pub fn with_defaults() -> Self {
        let mut reg = Self::empty();
        reg.register(Box::new(NullProvider));
        reg
    }

    /// Add a provider. Registered providers are consulted most-recent-first, so a
    /// later registration shadows an earlier one for any model both serve.
    pub fn register(&mut self, provider: Box<dyn ModelProvider>) -> &mut Self {
        self.providers.push(provider);
        self
    }

    /// The provider serving `model` on `endpoint`, if any. Most recently
    /// registered match wins (iteration is reversed).
    pub fn for_model(&self, model: Model, endpoint: Endpoint) -> Option<&dyn ModelProvider> {
        self.providers.iter().rev().find(|p| p.serves(model, endpoint)).map(|p| p.as_ref())
    }
}

impl Default for ProviderRegistry {
    fn default() -> Self {
        Self::with_defaults()
    }
}

/// How many times the manager attempts a generation before giving up. `1` (the
/// default) means no retry. Retries are immediate — no wall-clock backoff — so the
/// runtime stays deterministic; only [retryable](ProviderError::is_retryable)
/// backend errors are retried.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct RetryPolicy {
    pub max_attempts: u8,
}

impl Default for RetryPolicy {
    fn default() -> Self {
        Self { max_attempts: 1 }
    }
}

/// Gate that can refuse a model before it is invoked — the seam for circuit
/// breaking (open after repeated failures, half-open probes, etc.). This milestone
/// ships only [`AlwaysClosed`]; the manager already honors the gate so a real
/// breaker is a drop-in.
pub trait CircuitBreaker: Send + Sync {
    /// `true` if a call to `model` is permitted right now.
    fn allow(&self, model: Model) -> bool;
}

/// A breaker that never trips — every call is allowed. The default.
pub struct AlwaysClosed;
impl CircuitBreaker for AlwaysClosed {
    fn allow(&self, _model: Model) -> bool {
        true
    }
}

/// The Provider Manager: policy-aware provider selection, endpoint resolution,
/// retry, and a circuit-breaking seam over a [`ProviderRegistry`]. The runtime
/// invokes through this rather than touching the registry directly.
pub struct ProviderManager {
    registry: ProviderRegistry,
    retry: RetryPolicy,
    breaker: Box<dyn CircuitBreaker>,
}

impl ProviderManager {
    /// The honest default: the [`ProviderRegistry::with_defaults`] null provider,
    /// no retry, and an [`AlwaysClosed`] breaker.
    pub fn with_defaults() -> Self {
        Self::from_registry(ProviderRegistry::with_defaults())
    }

    /// A manager over a caller-supplied registry, with default retry/breaker.
    pub fn from_registry(registry: ProviderRegistry) -> Self {
        Self { registry, retry: RetryPolicy::default(), breaker: Box::new(AlwaysClosed) }
    }

    /// Override the retry policy (builder style).
    pub fn with_retry(mut self, retry: RetryPolicy) -> Self {
        self.retry = retry;
        self
    }

    /// Override the circuit breaker (builder style).
    pub fn with_breaker(mut self, breaker: Box<dyn CircuitBreaker>) -> Self {
        self.breaker = breaker;
        self
    }

    /// Invoke `model` on `endpoint` with `prompt`, streaming output to `sink`.
    ///
    /// Resolves the provider for the (model, endpoint) pair, refuses if the breaker
    /// is open, and retries a retryable backend error up to `max_attempts`
    /// (a missing provider or open circuit is never retried). Retries are
    /// immediate — no backoff — keeping the call deterministic.
    pub fn invoke(
        &self,
        model: Model,
        endpoint: Endpoint,
        prompt: &Prompt,
        sink: &mut dyn TokenSink,
    ) -> Result<ModelResponse, ProviderError> {
        if !self.breaker.allow(model) {
            return Err(ProviderError::CircuitOpen(model));
        }
        let provider =
            self.registry.for_model(model, endpoint).ok_or(ProviderError::NoProvider(model))?;
        let req = ProviderRequest { model, endpoint, prompt };

        let attempts = self.retry.max_attempts.max(1);
        let mut last = ProviderError::Backend("no attempt made".to_string());
        for _ in 0..attempts {
            match provider.generate(&req, sink) {
                Ok(resp) => return Ok(resp),
                Err(e) if e.is_retryable() => last = e,
                Err(e) => return Err(e),
            }
        }
        Err(last)
    }
}

impl Default for ProviderManager {
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
        req: &ProviderRequest,
        _sink: &mut dyn TokenSink,
    ) -> Result<ModelResponse, ProviderError> {
        Ok(ModelResponse { model: req.model, text: String::new(), finish: FinishReason::Empty, chunks: 0 })
    }
}
