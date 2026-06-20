//! Lexical (BM25) index over chunk text, backed by an in-RAM Tantivy index.
//!
//! Lexical search catches exact identifiers that embeddings miss (a function
//! name, an error string), which is why hybrid retrieval fuses it with the
//! vector store rather than choosing one.

use anyhow::{Context, Result};
use std::path::Path;

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
    fn schema() -> (Schema, Field, Field, Field) {
        let mut sb = Schema::builder();
        let id_field = sb.add_u64_field("id", STORED);
        let text_field = sb.add_text_field("text", TEXT);
        let file_field = sb.add_text_field("file", STRING | STORED);
        (sb.build(), id_field, text_field, file_field)
    }

    /// Wrap an `Index`, resolving field handles; optionally index initial chunks.
    fn from_index(index: Index, initial: Option<&[Chunk]>) -> Result<Self> {
        let schema = index.schema();
        let id_field = schema.get_field("id").context("id field")?;
        let text_field = schema.get_field("text").context("text field")?;
        let file_field = schema.get_field("file").context("file field")?;
        let me = Self { index, id_field, text_field, file_field };
        if let Some(chunks) = initial {
            let mut writer = me.index.writer(50_000_000).context("tantivy writer")?;
            for c in chunks {
                writer
                    .add_document(doc!(me.id_field => c.id, me.text_field => c.text.clone(), me.file_field => c.file.clone()))
                    .context("tantivy add_document")?;
            }
            writer.commit().context("tantivy commit")?;
        }
        Ok(me)
    }

    /// In-RAM index (default / tests).
    pub fn build(chunks: &[Chunk]) -> Result<Self> {
        let (schema, ..) = Self::schema();
        Self::from_index(Index::create_in_ram(schema), Some(chunks))
    }

    /// Fresh on-disk index at `dir` (caller wipes the dir first).
    pub fn build_at(dir: &Path, chunks: &[Chunk]) -> Result<Self> {
        std::fs::create_dir_all(dir).ok();
        let (schema, ..) = Self::schema();
        let index = Index::create_in_dir(dir, schema).context("tantivy create_in_dir")?;
        Self::from_index(index, Some(chunks))
    }

    /// Open an existing on-disk index (no re-indexing).
    pub fn open_at(dir: &Path) -> Result<Self> {
        let index = Index::open_in_dir(dir).context("tantivy open_in_dir")?;
        Self::from_index(index, None)
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
