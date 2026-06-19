//! Lexical (BM25) index over chunk text, backed by an in-RAM Tantivy index.
//!
//! Lexical search catches exact identifiers that embeddings miss (a function
//! name, an error string), which is why hybrid retrieval fuses it with the
//! vector store rather than choosing one.

use anyhow::{Context, Result};
use tantivy::collector::TopDocs;
use tantivy::query::QueryParser;
use tantivy::schema::{Field, Schema, Value, STORED, STRING, TEXT};
use tantivy::{doc, Index, TantivyDocument, Term};

use super::chunks::Chunk;

pub struct LexicalIndex {
    index: Index,
    id_field: Field,
    text_field: Field,
    /// STRING (untokenized) file path, so we can delete a file's docs by term
    /// for incremental updates.
    file_field: Field,
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
        let file_field = sb.add_text_field("file", STRING | STORED);
        let schema = sb.build();

        let index = Index::create_in_ram(schema);
        {
            let mut writer = index.writer(50_000_000).context("tantivy writer")?;
            for c in chunks {
                writer
                    .add_document(doc!(id_field => c.id, text_field => c.text.clone(), file_field => c.file.clone()))
                    .context("tantivy add_document")?;
            }
            writer.commit().context("tantivy commit")?;
        }

        Ok(Self { index, id_field, text_field, file_field })
    }

    /// Incremental update: delete all docs for `stale_files`, then add
    /// `new_chunks`. One writer + commit covers both.
    pub fn update(&mut self, stale_files: &[String], new_chunks: &[Chunk]) -> Result<()> {
        let mut writer = self.index.writer(50_000_000).context("tantivy writer")?;
        for f in stale_files {
            writer.delete_term(Term::from_field_text(self.file_field, f));
        }
        for c in new_chunks {
            writer
                .add_document(doc!(self.id_field => c.id, self.text_field => c.text.clone(), self.file_field => c.file.clone()))
                .context("tantivy add_document")?;
        }
        writer.commit().context("tantivy commit")?;
        Ok(())
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
