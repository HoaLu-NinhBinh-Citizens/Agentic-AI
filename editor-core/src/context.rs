//! ContextBuilder — turns `(file, cursor, query)` into a budgeted prompt.
//!
//! This is where engineering spend goes (ADR-001): a small model with a
//! well-built prompt beats a big model with a poor one. Two rules drive it:
//!
//! 1. **Select by fused retrieval score, ORDER by proximity to the cursor.**
//! 2. **Nearest-cursor snippet goes nearest the FIM middle** (models attend
//!    most to tokens adjacent to the insertion point); farthest goes at the top.
//!
//! Budget is packed nearest-first (closest context survives truncation) and any
//! overflow is reported as `dropped` — never silently cut.

use std::path::{Path, PathBuf};

use anyhow::Result;
use serde::Serialize;

use crate::retrieval::embed::Embedder;
use crate::retrieval::{HybridRetriever, ScoredChunk};

/// How many candidates to pull from retrieval before budget packing.
const CANDIDATE_K: usize = 12;
/// Rough chars-per-token for budget estimation.
const CHARS_PER_TOKEN: usize = 4;
/// Bytes of local prefix used as the retrieval query for completion.
const QUERY_TAIL_BYTES: usize = 512;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Task {
    Completion,
    Chat,
    /// Generate the edit at a call site for a semantic signature change.
    NextEditSemantic,
}

/// Distance class from the cursor — the ORDERING key (not the RRF score).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Proximity {
    SameFile { byte_distance: usize },
    SameModule,
    CrossModule,
}

impl Proximity {
    /// Lower = nearer. Used for nearest-first inclusion ordering.
    fn rank(&self) -> (u8, usize) {
        match self {
            Proximity::SameFile { byte_distance } => (0, *byte_distance),
            Proximity::SameModule => (1, 0),
            Proximity::CrossModule => (2, 0),
        }
    }
}

pub struct BuildRequest {
    pub task: Task,
    pub file: String,
    pub cursor_byte: usize,
    pub query: Option<String>,
    pub max_tokens: usize,
}

/// Provenance of one included item — logged for ADR-001.
#[derive(Debug, Clone, Serialize)]
pub struct SnippetRef {
    pub file: String,
    pub start_row: usize,
    pub kind: &'static str, // "retrieved"
}

#[derive(Debug, Clone, Serialize)]
pub struct BuiltPrompt {
    pub text: String,
    pub token_estimate: usize,
    pub included: Vec<SnippetRef>,
    /// Candidates that didn't fit the budget — surfaced, never hidden.
    pub dropped: usize,
}

pub struct ContextBuilder<'a, E: Embedder> {
    retriever: &'a HybridRetriever<E>,
    workspace_root: PathBuf,
}

fn est_tokens(s: &str) -> usize {
    s.len() / CHARS_PER_TOKEN + 1
}

fn dir_of(path: &str) -> &str {
    path.rsplit_once('/').map(|(d, _)| d).unwrap_or("")
}

impl<'a, E: Embedder> ContextBuilder<'a, E> {
    pub fn new(retriever: &'a HybridRetriever<E>, workspace_root: impl AsRef<Path>) -> Self {
        Self { retriever, workspace_root: workspace_root.as_ref().to_path_buf() }
    }

    /// Read the file and split it at the cursor into (prefix, suffix). Empty
    /// strings if the file can't be read.
    fn local_split(&self, file: &str, cursor_byte: usize) -> (String, String) {
        let abs = self.workspace_root.join(file);
        let Ok(bytes) = std::fs::read(&abs) else {
            return (String::new(), String::new());
        };
        let cut = cursor_byte.min(bytes.len());
        let prefix = String::from_utf8_lossy(&bytes[..cut]).to_string();
        let suffix = String::from_utf8_lossy(&bytes[cut..]).to_string();
        (prefix, suffix)
    }

    fn proximity(&self, req: &BuildRequest, sc: &ScoredChunk) -> Proximity {
        if sc.chunk.file == req.file {
            let d = sc.chunk.start_byte.abs_diff(req.cursor_byte);
            Proximity::SameFile { byte_distance: d }
        } else if dir_of(&sc.chunk.file) == dir_of(&req.file) {
            Proximity::SameModule
        } else {
            Proximity::CrossModule
        }
    }

    /// Build the prompt.
    pub fn build(&self, req: &BuildRequest) -> Result<BuiltPrompt> {
        let (prefix, suffix) = self.local_split(&req.file, req.cursor_byte);

        // Derive the retrieval query.
        let query = match (&req.query, req.task) {
            (Some(q), _) => q.clone(),
            (None, _) => {
                let start = prefix.len().saturating_sub(QUERY_TAIL_BYTES);
                prefix[start..].to_string()
            }
        };

        // Candidates, minus the chunk that contains the cursor (that's already
        // in the local prefix/suffix).
        let candidates: Vec<(ScoredChunk, Proximity)> = self
            .retriever
            .search(&query, CANDIDATE_K)?
            .into_iter()
            .filter(|sc| {
                !(sc.chunk.file == req.file
                    && sc.chunk.start_byte <= req.cursor_byte
                    && req.cursor_byte < sc.chunk.end_byte)
            })
            .map(|sc| {
                let p = self.proximity(req, &sc);
                (sc, p)
            })
            .collect();

        // Inclusion order: nearest-first so the closest context survives the
        // budget.
        let mut by_nearest = candidates;
        by_nearest.sort_by_key(|(_, p)| p.rank());

        let reserved = est_tokens(&prefix) + est_tokens(&suffix);
        let snippet_budget = req.max_tokens.saturating_sub(reserved);

        let mut included: Vec<(ScoredChunk, Proximity)> = Vec::new();
        let mut used = 0usize;
        let mut dropped = 0usize;
        for (sc, p) in by_nearest {
            let cost = est_tokens(&sc.chunk.text);
            if used + cost <= snippet_budget {
                used += cost;
                included.push((sc, p));
            } else {
                dropped += 1;
            }
        }

        // Placement order: farthest-first, so the nearest snippet sits last —
        // adjacent to the local prefix and thus the FIM middle.
        included.sort_by_key(|(_, p)| std::cmp::Reverse(p.rank()));

        let header = included
            .iter()
            .map(|(sc, _)| format!("// {}:{}\n{}\n", sc.chunk.file, sc.chunk.start_row, sc.chunk.text))
            .collect::<String>();

        let text = match req.task {
            Task::Completion => format!(
                "<|fim_prefix|>{header}{prefix}<|fim_suffix|>{suffix}<|fim_middle|>"
            ),
            Task::Chat | Task::NextEditSemantic => {
                format!("// Relevant context:\n{header}\n// Request:\n{query}\n")
            }
        };

        let included_refs = included
            .iter()
            .map(|(sc, _)| SnippetRef {
                file: sc.chunk.file.clone(),
                start_row: sc.chunk.start_row,
                kind: "retrieved",
            })
            .collect();

        Ok(BuiltPrompt {
            token_estimate: est_tokens(&text),
            text,
            included: included_refs,
            dropped,
        })
    }
}
