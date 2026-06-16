//! Embedding abstraction.
//!
//! `Embedder` is a trait so the real model (e.g. nomic-embed-code served by
//! Ollama over HTTP) drops in behind the same interface the retriever uses. The
//! default `HashEmbedder` is deterministic and offline — good for tests and a
//! reasonable lexical-ish signal — so the whole pipeline runs without a model.

/// Produces a fixed-dimension, L2-normalized embedding for a text.
pub trait Embedder: Send + Sync {
    fn dim(&self) -> usize;
    fn embed(&self, text: &str) -> Vec<f32>;
}

/// A deterministic bag-of-words embedder: tokens are hashed into `dim` buckets
/// and the vector is L2-normalized. Cosine similarity then approximates token
/// overlap. Not semantic, but real, offline, and reproducible — the model-based
/// embedder replaces it behind the `Embedder` trait without touching callers.
pub struct HashEmbedder {
    dim: usize,
}

impl HashEmbedder {
    pub fn new(dim: usize) -> Self {
        assert!(dim > 0);
        Self { dim }
    }
}

impl Default for HashEmbedder {
    fn default() -> Self {
        Self::new(256)
    }
}

/// FNV-1a — small, fast, stable across runs (unlike DefaultHasher).
fn fnv1a(bytes: &[u8]) -> u64 {
    let mut h: u64 = 0xcbf29ce484222325;
    for &b in bytes {
        h ^= b as u64;
        h = h.wrapping_mul(0x100000001b3);
    }
    h
}

fn tokenize(text: &str) -> impl Iterator<Item = String> + '_ {
    text.split(|c: char| !c.is_alphanumeric() && c != '_')
        .filter(|t| !t.is_empty())
        .map(|t| t.to_ascii_lowercase())
}

impl Embedder for HashEmbedder {
    fn dim(&self) -> usize {
        self.dim
    }

    fn embed(&self, text: &str) -> Vec<f32> {
        let mut v = vec![0f32; self.dim];
        for tok in tokenize(text) {
            let bucket = (fnv1a(tok.as_bytes()) as usize) % self.dim;
            v[bucket] += 1.0;
        }
        let norm: f32 = v.iter().map(|x| x * x).sum::<f32>().sqrt();
        if norm > 0.0 {
            for x in &mut v {
                *x /= norm;
            }
        }
        v
    }
}
