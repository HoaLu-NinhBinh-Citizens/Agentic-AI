//! Real embeddings via a local Ollama server.
//!
//! Calls Ollama's `/api/embeddings` over HTTP (sync `ureq`). This is the
//! production embedder; it implements the same `Embedder` trait as the offline
//! `HashEmbedder`, so swapping is a one-line change at the call site.
//!
//! Failures are graceful: a network/parse error yields a zero vector (and a
//! warning) rather than panicking the daemon — a missing embedding degrades
//! retrieval, it does not take the editor down.

use std::time::Duration;

use serde::{Deserialize, Serialize};
use tracing::warn;

use super::embed::Embedder;

const DEFAULT_HOST: &str = "http://localhost:11434";
const DEFAULT_MODEL: &str = "nomic-embed-text";
/// nomic-embed-text output dimension.
const DEFAULT_DIM: usize = 768;
const TIMEOUT_SECS: u64 = 30;

pub struct OllamaEmbedder {
    host: String,
    model: String,
    dim: usize,
    agent: ureq::Agent,
}

#[derive(Serialize)]
struct EmbedRequest<'a> {
    model: &'a str,
    prompt: &'a str,
}

#[derive(Deserialize)]
struct EmbedResponse {
    embedding: Vec<f32>,
}

impl OllamaEmbedder {
    /// `model`'s output dimension must be provided so the vector store schema is
    /// fixed up front (e.g. 768 for `nomic-embed-text`).
    pub fn new(host: impl Into<String>, model: impl Into<String>, dim: usize) -> Self {
        let agent = ureq::AgentBuilder::new()
            .timeout(Duration::from_secs(TIMEOUT_SECS))
            .build();
        Self { host: host.into(), model: model.into(), dim, agent }
    }

    /// Default: `nomic-embed-text` on `localhost:11434`, dim 768.
    pub fn default_local() -> Self {
        Self::new(DEFAULT_HOST, DEFAULT_MODEL, DEFAULT_DIM)
    }

    fn request(&self, text: &str) -> anyhow::Result<Vec<f32>> {
        let url = format!("{}/api/embeddings", self.host);
        let resp: EmbedResponse = self
            .agent
            .post(&url)
            .send_json(EmbedRequest { model: &self.model, prompt: text })?
            .into_json()?;
        Ok(resp.embedding)
    }
}

impl Embedder for OllamaEmbedder {
    fn dim(&self) -> usize {
        self.dim
    }

    fn embed(&self, text: &str) -> Vec<f32> {
        match self.request(text) {
            Ok(v) if v.len() == self.dim => v,
            Ok(v) => {
                warn!(got = v.len(), expected = self.dim, "ollama embedding dim mismatch");
                // Conform to the expected dim so the vector store stays valid.
                let mut v = v;
                v.resize(self.dim, 0.0);
                v
            }
            Err(e) => {
                warn!(error = %e, "ollama embed failed; returning zero vector");
                vec![0.0; self.dim]
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_embedding_response() {
        // Pure JSON-shape test — no network.
        let json = r#"{"embedding":[0.1,0.2,0.3]}"#;
        let parsed: EmbedResponse = serde_json::from_str(json).unwrap();
        assert_eq!(parsed.embedding, vec![0.1, 0.2, 0.3]);
    }

    #[test]
    #[ignore = "requires a running Ollama with nomic-embed-text"]
    fn live_embed_has_expected_dim() {
        let e = OllamaEmbedder::default_local();
        let v = e.embed("fn main() {}");
        assert_eq!(v.len(), e.dim());
    }
}
