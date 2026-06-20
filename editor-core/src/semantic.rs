//! Semantic engine: cross-file symbol resolution + minimal task context.
//!
//! The symbol graph stores *definitions*, *refs* (call edges, via
//! `enclosing_symbol_id`), and *imports*. This layer turns that raw graph into
//! the two things a planner/agent actually needs:
//!
//! 1. **Resolution** — given a name used in a file, which definition does it
//!    bind to? Without a full type-checker we rank candidates by scope (local →
//!    same-module → same-crate → workspace), using the file's imports as a
//!    confidence signal, and report how ambiguous the choice was.
//! 2. **Minimal context** — given a focus symbol (by qualified name or cursor),
//!    return its source plus the *resolved* definitions it calls, budgeted by
//!    tokens. This is the semantic replacement for "grep + paste the file".
//!
//! Everything is read-only over `SymbolGraph`; the engine borrows it per call.

use std::collections::HashSet;

use anyhow::{anyhow, Result};
use serde::{Deserialize, Serialize};

use crate::symbols::store::DefRecord;
use crate::symbols::SymbolGraph;

/// Rough chars-per-token for budget estimation (matches `context.rs`).
const CHARS_PER_TOKEN: usize = 4;

/// Where a resolved definition sits relative to the use site. Lower discriminant
/// = nearer = preferred. This is the ranking key.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Scope {
    /// Defined in the same file as the use site.
    Local,
    /// Same directory/module.
    SameModule,
    /// Same crate (shares a `Cargo.toml` root).
    SameCrate,
    /// Anywhere else in the workspace.
    Workspace,
}

impl Scope {
    fn rank(self) -> u8 {
        self as u8
    }
}

/// How sure the resolver is about a binding.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum Confidence {
    /// Sole candidate, or a strictly nearest one.
    High,
    /// Tied with others at the nearest scope.
    Medium,
    /// A farther candidate while nearer ones exist; weak match.
    Low,
}

/// One resolved binding for a name.
#[derive(Debug, Clone, Serialize)]
pub struct ResolvedSymbol {
    #[serde(flatten)]
    pub def: DefRecord,
    pub scope: Scope,
    pub confidence: Confidence,
    /// True if the name was explicitly imported into the use-site file (a `use`
    /// / `from import`). Informational — strengthens trust in the binding.
    pub imported: bool,
}

/// A file-level dependency edge: an import and the file it resolves to.
#[derive(Debug, Clone, Serialize)]
pub struct ImportEdge {
    pub module_path: String,
    pub name: String,
    pub is_glob: bool,
    /// The workspace file that defines `name`, if the resolver could pin one.
    /// `None` for globs or unresolved/external imports.
    pub resolved_file: Option<String>,
    /// How many definitions of `name` exist (ambiguity indicator).
    pub candidates: usize,
}

/// What to center the context on.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub enum FocusSpec {
    /// A definition's exact qualified name (`file::Mod::name`).
    Symbol(String),
    /// A cursor position; resolves to the innermost enclosing definition.
    Location { file: String, byte: usize },
}

/// A semantic-context request.
#[derive(Debug, Clone)]
pub struct SemanticRequest {
    pub focus: FocusSpec,
    pub max_tokens: usize,
    /// Include resolved callees' full bodies (within budget), not just their
    /// signatures.
    pub include_bodies: bool,
}

/// The focus symbol with its full source.
#[derive(Debug, Clone, Serialize)]
pub struct FocusEntry {
    pub qualified_name: String,
    pub file: String,
    pub kind: String,
    pub start_row: usize,
    pub signature: String,
    pub source: String,
}

/// One dependency of the focus: a resolved callee. `source` is its body when it
/// fit the budget (and bodies were requested), else `None` (signature only).
#[derive(Debug, Clone, Serialize)]
pub struct DepEntry {
    pub qualified_name: String,
    pub file: String,
    pub kind: String,
    pub start_row: usize,
    pub scope: Scope,
    pub confidence: Confidence,
    pub signature: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub source: Option<String>,
}

/// The minimal relevant code for a task.
#[derive(Debug, Clone, Serialize)]
pub struct SemanticContext {
    pub focus: FocusEntry,
    /// Resolved callees, nearest-scope first.
    pub dependencies: Vec<DepEntry>,
    /// File-level import edges for the focus' file.
    pub imports: Vec<ImportEdge>,
    pub token_estimate: usize,
    /// Callee bodies that didn't fit the budget (signature still included).
    pub dropped: usize,
}

fn est_tokens(s: &str) -> usize {
    s.len() / CHARS_PER_TOKEN + 1
}

fn dir_of(path: &str) -> &str {
    path.rsplit_once('/').map(|(d, _)| d).unwrap_or("")
}

/// Read a definition's source from disk by byte span.
fn read_span(graph: &SymbolGraph, def: &DefRecord) -> String {
    let abs = graph.workspace_root().join(&def.file);
    let Ok(bytes) = std::fs::read(&abs) else {
        return String::new();
    };
    let end = def.end_byte.min(bytes.len());
    let start = def.start_byte.min(end);
    String::from_utf8_lossy(&bytes[start..end]).to_string()
}

pub struct SemanticEngine<'a> {
    graph: &'a SymbolGraph,
}

impl<'a> SemanticEngine<'a> {
    pub fn new(graph: &'a SymbolGraph) -> Self {
        Self { graph }
    }

    /// Resolve every definition `name` could bind to from `from_file`, ranked
    /// nearest-scope first with a confidence verdict. Empty if `name` is unknown.
    pub fn resolve(&self, name: &str, from_file: &str) -> Result<Vec<ResolvedSymbol>> {
        let cands = self.graph.resolve_candidates(name)?;
        if cands.is_empty() {
            return Ok(Vec::new());
        }
        let imports = self.graph.imports_of_file(from_file)?;
        let imported = imports.iter().any(|i| !i.is_glob && i.name == name);
        let from_dir = dir_of(from_file).to_string();
        let from_crate = self.graph.crate_root_of(from_file)?.unwrap_or_default();

        let total = cands.len();
        let mut scored: Vec<ResolvedSymbol> = cands
            .into_iter()
            .map(|d| {
                let scope = if d.file == from_file {
                    Scope::Local
                } else if dir_of(&d.file) == from_dir {
                    Scope::SameModule
                } else if !from_crate.is_empty() && d.crate_root == from_crate {
                    Scope::SameCrate
                } else {
                    Scope::Workspace
                };
                ResolvedSymbol { def: d, scope, confidence: Confidence::Low, imported }
            })
            .collect();

        // Nearest scope first; stable tiebreak by file then position.
        scored.sort_by(|a, b| {
            a.scope
                .rank()
                .cmp(&b.scope.rank())
                .then(a.def.file.cmp(&b.def.file))
                .then(a.def.start_byte.cmp(&b.def.start_byte))
        });

        // Confidence: a sole candidate, or a strictly-nearest one, is High; a
        // tie at the nearest scope is Medium; anything farther is Low.
        let best_rank = scored[0].scope.rank();
        let best_count = scored.iter().filter(|s| s.scope.rank() == best_rank).count();
        for s in &mut scored {
            s.confidence = if total == 1 {
                Confidence::High
            } else if s.scope.rank() == best_rank {
                if best_count == 1 {
                    Confidence::High
                } else {
                    Confidence::Medium
                }
            } else {
                Confidence::Low
            };
        }
        Ok(scored)
    }

    /// File-level dependency edges: each import resolved to the file that
    /// defines it (where pinnable).
    pub fn file_dependencies(&self, file: &str) -> Result<Vec<ImportEdge>> {
        let imports = self.graph.imports_of_file(file)?;
        let mut edges = Vec::with_capacity(imports.len());
        for im in imports {
            let (resolved_file, candidates) = if im.is_glob {
                (None, 0)
            } else {
                let r = self.resolve(&im.name, file)?;
                // Prefer a cross-file definition (the actual dependency target)
                // over a same-file shadow.
                let target = r
                    .iter()
                    .find(|c| c.def.file != file)
                    .or_else(|| r.first())
                    .map(|c| c.def.file.clone());
                (target, r.len())
            };
            edges.push(ImportEdge {
                module_path: im.module_path,
                name: im.name,
                is_glob: im.is_glob,
                resolved_file,
                candidates,
            });
        }
        Ok(edges)
    }

    /// Build the minimal relevant code for a focus symbol: its source plus the
    /// resolved definitions it calls, packed nearest-first into `max_tokens`.
    pub fn context(&self, req: &SemanticRequest) -> Result<SemanticContext> {
        let focus_def = match &req.focus {
            FocusSpec::Symbol(q) => self.graph.def_by_qname(q)?,
            FocusSpec::Location { file, byte } => self.graph.def_at(file, *byte)?,
        }
        .ok_or_else(|| anyhow!("focus symbol not found in the index"))?;

        let focus_source = read_span(self.graph, &focus_def);
        let mut used = est_tokens(&focus_source);

        // Resolve the focus' outgoing call edges to concrete definitions.
        let mut deps: Vec<ResolvedSymbol> = Vec::new();
        let mut seen: HashSet<i64> = HashSet::from([focus_def.id]);
        for rn in self.graph.refs_in_symbol(focus_def.id)? {
            let resolved = self.resolve(&rn.name, &focus_def.file)?;
            if let Some(best) = resolved.into_iter().next() {
                if seen.insert(best.def.id) {
                    deps.push(best);
                }
            }
        }
        // Nearest-scope, highest-confidence dependencies first.
        deps.sort_by(|a, b| {
            a.scope.rank().cmp(&b.scope.rank()).then(a.def.qualified_name.cmp(&b.def.qualified_name))
        });

        // Always include each callee's signature (cheap, minimal). Add the full
        // body only when requested and it fits; otherwise count it as dropped.
        let mut dependencies = Vec::with_capacity(deps.len());
        let mut dropped = 0usize;
        for d in deps {
            used += est_tokens(&d.def.signature);
            let mut source = None;
            if req.include_bodies {
                let body = read_span(self.graph, &d.def);
                let cost = est_tokens(&body);
                if used + cost <= req.max_tokens {
                    used += cost;
                    source = Some(body);
                } else {
                    dropped += 1;
                }
            }
            dependencies.push(DepEntry {
                qualified_name: d.def.qualified_name,
                file: d.def.file,
                kind: d.def.kind,
                start_row: d.def.start_row,
                scope: d.scope,
                confidence: d.confidence,
                signature: d.def.signature,
                source,
            });
        }

        let imports = self.file_dependencies(&focus_def.file)?;

        Ok(SemanticContext {
            focus: FocusEntry {
                qualified_name: focus_def.qualified_name,
                file: focus_def.file,
                kind: focus_def.kind,
                start_row: focus_def.start_row,
                signature: focus_def.signature,
                source: focus_source,
            },
            dependencies,
            imports,
            token_estimate: used,
            dropped,
        })
    }
}
