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

use std::collections::HashSet;
use std::path::{Path, PathBuf};

use anyhow::Result;
use serde::Serialize;

use crate::retrieval::{HybridRetriever, ScoredChunk};
use crate::semantic::{FocusSpec, SemanticEngine, SemanticRequest};
use crate::symbols::SymbolGraph;

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
    /// Explicit focus by qualified name. When `None`, the focus is the symbol at
    /// `(file, cursor_byte)`. Lets chat/agent center context on a named symbol.
    pub focus_symbol: Option<String>,
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
    /// How the context was sourced: `"semantic"` (resolved symbols only),
    /// `"retrieval"` (fallback — no focus resolved), or `"hybrid"` (semantic
    /// core + retrieval fill). Lets the editor/telemetry see which path ran.
    pub mode: &'static str,
}

pub struct ContextBuilder<'a> {
    retriever: &'a HybridRetriever,
    workspace_root: PathBuf,
}

fn est_tokens(s: &str) -> usize {
    s.len() / CHARS_PER_TOKEN + 1
}

fn dir_of(path: &str) -> &str {
    path.rsplit_once('/').map(|(d, _)| d).unwrap_or("")
}

impl<'a> ContextBuilder<'a> {
    pub fn new(retriever: &'a HybridRetriever, workspace_root: impl AsRef<Path>) -> Self {
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
            mode: "retrieval",
        })
    }
}

/// Proximity of a chunk to the request's cursor — the placement-ordering key,
/// shared by the retrieval-fill path of the semantic builder.
fn proximity_of(req: &BuildRequest, chunk_file: &str, chunk_start_byte: usize) -> Proximity {
    if chunk_file == req.file {
        Proximity::SameFile { byte_distance: chunk_start_byte.abs_diff(req.cursor_byte) }
    } else if dir_of(chunk_file) == dir_of(&req.file) {
        Proximity::SameModule
    } else {
        Proximity::CrossModule
    }
}

/// Read `file` and split it at `cursor_byte` into (prefix, suffix). Empty
/// strings if the file can't be read.
fn split_local(workspace_root: &Path, file: &str, cursor_byte: usize) -> (String, String) {
    let abs = workspace_root.join(file);
    let Ok(bytes) = std::fs::read(&abs) else {
        return (String::new(), String::new());
    };
    let cut = cursor_byte.min(bytes.len());
    (
        String::from_utf8_lossy(&bytes[..cut]).to_string(),
        String::from_utf8_lossy(&bytes[cut..]).to_string(),
    )
}

/// The default context provider: **semantic-first, retrieval-fallback.**
///
/// 1. Resolve a focus symbol (explicit qualified name, or the symbol at the
///    cursor) and pull its minimal relevant code — resolved callees, their
///    signatures/bodies, and imports — via the [`SemanticEngine`].
/// 2. Fill any remaining token budget with hybrid retrieval, skipping files the
///    semantic core already covers.
///
/// When no focus resolves (cursor outside any known symbol, or a pure
/// exploratory query), it degrades to retrieval-only — the same behavior as the
/// legacy [`ContextBuilder`]. When semantic resolution is *thin* (few/low-
/// confidence callees), more budget is left for retrieval automatically, so
/// retrieval naturally dominates exactly when semantic confidence is low.
pub struct SemanticContextBuilder<'a> {
    graph: &'a SymbolGraph,
    retriever: &'a HybridRetriever,
    workspace_root: PathBuf,
}

impl<'a> SemanticContextBuilder<'a> {
    pub fn new(
        graph: &'a SymbolGraph,
        retriever: &'a HybridRetriever,
        workspace_root: impl AsRef<Path>,
    ) -> Self {
        Self { graph, retriever, workspace_root: workspace_root.as_ref().to_path_buf() }
    }

    pub fn build(&self, req: &BuildRequest) -> Result<BuiltPrompt> {
        let is_completion = req.task == Task::Completion;
        let (prefix, suffix) = split_local(&self.workspace_root, &req.file, req.cursor_byte);

        // Derive the retrieval query (explicit, else the local prefix tail).
        let query = req.query.clone().unwrap_or_else(|| {
            let start = prefix.len().saturating_sub(QUERY_TAIL_BYTES);
            prefix[start..].to_string()
        });

        // For completion the local file *is* the focus (prefix/suffix), so reserve
        // its budget and use the cursor symbol's callees as context. For chat the
        // focus source is itself useful context, so include it.
        let focus = match &req.focus_symbol {
            Some(sym) => FocusSpec::Symbol(sym.clone()),
            None => FocusSpec::Location { file: req.file.clone(), byte: req.cursor_byte },
        };
        let reserved = if is_completion {
            est_tokens(&prefix) + est_tokens(&suffix)
        } else {
            0
        };
        let sem_budget = req.max_tokens.saturating_sub(reserved);

        // Completion wants compact signatures (budget is precious next to the
        // local file); chat/agent benefit from full callee bodies.
        let sem = SemanticEngine::new(self.graph);
        let semctx = sem
            .context(&SemanticRequest { focus, max_tokens: sem_budget, include_bodies: !is_completion })
            .ok();

        let mut header = String::new();
        let mut included: Vec<SnippetRef> = Vec::new();
        let mut used = reserved;
        let mut covered: HashSet<String> = HashSet::new();
        let mut has_semantic = false;

        if let Some(ctx) = &semctx {
            covered.insert(ctx.focus.file.clone());
            // Chat/agent: the focus body itself is context. Completion: skip — it's
            // already the local prefix/suffix.
            if !is_completion {
                let block =
                    format!("// {} ({})\n{}\n", ctx.focus.qualified_name, ctx.focus.file, ctx.focus.source);
                used += est_tokens(&block);
                header.push_str(&block);
                included.push(SnippetRef {
                    file: ctx.focus.file.clone(),
                    start_row: ctx.focus.start_row,
                    kind: "semantic.focus",
                });
                has_semantic = true;
            }
            for dep in &ctx.dependencies {
                let body = dep.source.clone().unwrap_or_else(|| dep.signature.clone());
                let block = format!("// {} ({})\n{}\n", dep.qualified_name, dep.file, body);
                let cost = est_tokens(&block);
                if used + cost > req.max_tokens {
                    continue;
                }
                used += cost;
                header.push_str(&block);
                covered.insert(dep.file.clone());
                included.push(SnippetRef {
                    file: dep.file.clone(),
                    start_row: dep.start_row,
                    kind: "semantic.dep",
                });
                has_semantic = true;
            }
        }

        // Retrieval fill: spend any leftover budget on hybrid retrieval, skipping
        // files the semantic core already covers and the chunk under the cursor.
        let mut dropped = 0usize;
        let mut has_retrieval = false;
        if used < req.max_tokens {
            let mut ordered: Vec<(ScoredChunk, Proximity)> = self
                .retriever
                .search(&query, CANDIDATE_K)?
                .into_iter()
                .filter(|sc| !covered.contains(&sc.chunk.file))
                .filter(|sc| {
                    // Drop the chunk containing the cursor (already in prefix/suffix).
                    !(sc.chunk.file == req.file
                        && sc.chunk.start_byte <= req.cursor_byte
                        && req.cursor_byte < sc.chunk.end_byte)
                })
                .map(|sc| {
                    let p = proximity_of(req, &sc.chunk.file, sc.chunk.start_byte);
                    (sc, p)
                })
                .collect();
            ordered.sort_by_key(|(_, p)| p.rank());

            for (sc, _) in ordered {
                let block = format!("// {}:{}\n{}\n", sc.chunk.file, sc.chunk.start_row, sc.chunk.text);
                let cost = est_tokens(&block);
                if used + cost <= req.max_tokens {
                    used += cost;
                    header.push_str(&block);
                    included.push(SnippetRef {
                        file: sc.chunk.file.clone(),
                        start_row: sc.chunk.start_row,
                        kind: "retrieved",
                    });
                    has_retrieval = true;
                } else {
                    dropped += 1;
                }
            }
        }

        let text = if is_completion {
            format!("<|fim_prefix|>{header}{prefix}<|fim_suffix|>{suffix}<|fim_middle|>")
        } else {
            format!("// Relevant context:\n{header}\n// Request:\n{query}\n")
        };

        let mode = match (has_semantic, has_retrieval) {
            (true, true) => "hybrid",
            (true, false) => "semantic",
            _ => "retrieval",
        };

        Ok(BuiltPrompt {
            token_estimate: est_tokens(&text),
            text,
            included,
            dropped,
            mode,
        })
    }
}
