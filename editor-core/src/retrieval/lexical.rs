//! Lexical (BM25) index over chunk text, backed by an in-RAM Tantivy index.
//!
//! Lexical search catches exact identifiers that embeddings miss (a function
//! name, an error string), which is why hybrid retrieval fuses it with the
//! vector store rather than choosing one.

use anyhow::{Context, Result};
use tantivy::collector::TopDocs;
use tantivy::query::QueryParser;
use tantivy::schema::{Schema, Value, STORED, TEXT};
use tantivy::{doc, Index, TantivyDocument};

use super::chunks::Chunk;

pub struct LexicalIndex {
    index: Index,
    id_field: tantivy::schema::Field,
    text_field: tantivy::schema::Field,
}

/// Strip query punctuation so code like `area(1, 2)` parses as terms, not
/// Tantivy query syntax.
fn sanitize(query: &str) -> String {
    query
        .chars()
        .map(|c| if c.is_alphanumeric() || c == '_' { c } else { ' ' })
        .collect()
}

impl LexicalIndex {
    /// Build a fresh in-RAM index from `chunks`.
    pub fn build(chunks: &[Chunk]) -> Result<Self> {
        let mut sb = Schema::builder();
        let id_field = sb.add_u64_field("id", STORED);
        let text_field = sb.add_text_field("text", TEXT);
        let schema = sb.build();

        let index = Index::create_in_ram(schema);
        {
            let mut writer = index.writer(50_000_000).context("tantivy writer")?;
            for c in chunks {
                writer
                    .add_document(doc!(id_field => c.id, text_field => c.text.clone()))
                    .context("tantivy add_document")?;
            }
            writer.commit().context("tantivy commit")?;
        }

        Ok(Self { index, id_field, text_field })
    }

    /// Top-`k` `(chunk_id, bm25_score)` for `query`.
    pub fn search(&self, query: &str, k: usize) -> Result<Vec<(u64, f32)>> {
        let cleaned = sanitize(query);
        let terms = cleaned.split_whitespace().collect::<Vec<_>>();
        if terms.is_empty() {
            return Ok(Vec::new());
        }

        let reader = self.index.reader().context("tantivy reader")?;
        let searcher = reader.searcher();
        let parser = QueryParser::for_index(&self.index, vec![self.text_field]);
        let query = parser
            .parse_query(&cleaned)
            .context("parsing lexical query")?;

        let hits = searcher
            .search(&query, &TopDocs::with_limit(k))
            .context("tantivy search")?;

        let mut out = Vec::with_capacity(hits.len());
        for (score, addr) in hits {
            let doc: TantivyDocument = searcher.doc(addr).context("tantivy doc fetch")?;
            if let Some(id) = doc.get_first(self.id_field).and_then(|v| v.as_u64()) {
                out.push((id, score));
            }
        }
        Ok(out)
    }
}
