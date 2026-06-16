//! Vector store abstraction.
//!
//! `VectorStore` is a trait so **LanceDB** (the intended production store) slots
//! in here without touching the retriever or ContextBuilder. The current
//! `InMemoryVectorStore` is brute-force cosine — correct and fast enough for
//! moderate repos; it is the de-risked stand-in until the LanceDB impl lands.
//!
//! Vectors are assumed L2-normalized (see `Embedder`), so cosine similarity is
//! just the dot product.

/// A nearest-neighbor index over embedding vectors keyed by chunk id.
pub trait VectorStore {
    fn clear(&mut self);
    fn add(&mut self, id: u64, vector: Vec<f32>);
    /// Top-`k` `(id, score)` by descending cosine similarity.
    fn search(&self, query: &[f32], k: usize) -> Vec<(u64, f32)>;
    fn len(&self) -> usize;
    fn is_empty(&self) -> bool {
        self.len() == 0
    }
}

#[derive(Default)]
pub struct InMemoryVectorStore {
    items: Vec<(u64, Vec<f32>)>,
}

impl InMemoryVectorStore {
    pub fn new() -> Self {
        Self::default()
    }
}

fn dot(a: &[f32], b: &[f32]) -> f32 {
    a.iter().zip(b).map(|(x, y)| x * y).sum()
}

impl VectorStore for InMemoryVectorStore {
    fn clear(&mut self) {
        self.items.clear();
    }

    fn add(&mut self, id: u64, vector: Vec<f32>) {
        self.items.push((id, vector));
    }

    fn search(&self, query: &[f32], k: usize) -> Vec<(u64, f32)> {
        let mut scored: Vec<(u64, f32)> = self
            .items
            .iter()
            .map(|(id, v)| (*id, dot(query, v)))
            .collect();
        // Descending by score; partial_cmp is safe because vectors are finite.
        scored.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
        scored.truncate(k);
        scored
    }

    fn len(&self) -> usize {
        self.items.len()
    }
}
