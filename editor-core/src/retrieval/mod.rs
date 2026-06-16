//! Hybrid retrieval: vector (semantic) ⊕ lexical (BM25), fused by Reciprocal
//! Rank Fusion. Selection uses the fused score; the caller (ContextBuilder)
//! decides ORDER and placement by proximity, not score.

pub mod chunks;
pub mod embed;
pub mod lance_store;
pub mod lexical;
pub mod ollama;
pub mod vector;

use std::collections::HashMap;

use anyhow::Result;

use chunks::Chunk;
use embed::Embedder;
use lexical::LexicalIndex;
use vector::{InMemoryVectorStore, VectorStore};

/// RRF constant. 60 is the value from the original paper; it damps the
/// influence of any single ranker's top results.
const RRF_K: f32 = 60.0;

/// A chunk with its fused retrieval score.
#[derive(Debug, Clone)]
pub struct ScoredChunk {
    pub chunk: Chunk,
    pub rrf_score: f32,
}

pub struct HybridRetriever {
    embedder: Box<dyn Embedder>,
    vector: Box<dyn VectorStore>,
    lexical: LexicalIndex,
    chunks: HashMap<u64, Chunk>,
}

/// Fuse several ranked id lists into one fused score per id (Reciprocal Rank
/// Fusion): score(id) = Σ 1 / (RRF_K + rank), rank 0-based per list.
fn reciprocal_rank_fusion(lists: &[Vec<u64>]) -> HashMap<u64, f32> {
    let mut fused: HashMap<u64, f32> = HashMap::new();
    for list in lists {
        for (rank, id) in list.iter().enumerate() {
            *fused.entry(*id).or_insert(0.0) += 1.0 / (RRF_K + rank as f32);
        }
    }
    fused
}

impl HybridRetriever {
    /// Build with the default in-memory vector store.
    pub fn build(embedder: impl Embedder + 'static, chunks: Vec<Chunk>) -> Result<Self> {
        Self::build_with(Box::new(embedder), Box::new(InMemoryVectorStore::new()), chunks)
    }

    /// Build with a caller-provided embedder + vector store (e.g.
    /// `OllamaEmbedder` + `LanceVectorStore`). The store is committed after all
    /// vectors are added.
    pub fn build_with(
        embedder: Box<dyn Embedder>,
        mut vector: Box<dyn VectorStore>,
        chunks: Vec<Chunk>,
    ) -> Result<Self> {
        let lexical = LexicalIndex::build(&chunks)?;
        vector.clear();
        let mut map = HashMap::with_capacity(chunks.len());
        for c in chunks {
            vector.add(c.id, embedder.embed(&c.text));
            map.insert(c.id, c);
        }
        vector.commit()?;
        Ok(Self { embedder, vector, lexical, chunks: map })
    }

    pub fn len(&self) -> usize {
        self.chunks.len()
    }

    pub fn is_empty(&self) -> bool {
        self.chunks.is_empty()
    }

    /// Retrieve the top-`k` chunks for `query`, fusing vector + lexical ranks.
    /// Each ranker contributes its own top `k * pool` before fusion so a result
    /// strong in one modality but absent from the other still surfaces.
    pub fn search(&self, query: &str, k: usize) -> Result<Vec<ScoredChunk>> {
        let pool = (k * 4).max(20);

        let qvec = self.embedder.embed(query);
        let vec_ids: Vec<u64> = self
            .vector
            .search(&qvec, pool)
            .into_iter()
            .map(|(id, _)| id)
            .collect();

        let lex_ids: Vec<u64> = self
            .lexical
            .search(query, pool)?
            .into_iter()
            .map(|(id, _)| id)
            .collect();

        let fused = reciprocal_rank_fusion(&[vec_ids, lex_ids]);

        let mut scored: Vec<ScoredChunk> = fused
            .into_iter()
            .filter_map(|(id, score)| {
                self.chunks.get(&id).map(|c| ScoredChunk { chunk: c.clone(), rrf_score: score })
            })
            .collect();
        scored.sort_by(|a, b| {
            b.rrf_score
                .partial_cmp(&a.rrf_score)
                .unwrap_or(std::cmp::Ordering::Equal)
        });
        scored.truncate(k);
        Ok(scored)
    }
}
