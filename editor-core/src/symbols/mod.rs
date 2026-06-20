//! Symbol graph: tree-sitter definitions + call-site refs over the workspace.
//!
//! Driven by the Merkle `SyncDelta` — only `added` + `modified` files are
//! parsed, `removed` files are dropped. Parsing is pure (`extract`) so it runs
//! on the rayon pool; inserts are serial on the owning thread (SQLite).

pub mod classifier;
pub mod extract;
pub mod lang;
pub mod store;

use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::time::{Instant, SystemTime, UNIX_EPOCH};

use anyhow::Result;
use rayon::prelude::*;
use serde::Serialize;
use tracing::{debug, info, warn};

use classifier::{classify, EditKind, EditSite, EditSuggestion, Replacement};
use extract::{extract, extract_imports, Import, SymbolDef, SymbolRef};
use lang::Lang;
use store::{DefRecord, ImportRow, RefName, RefRow, SymbolRow, SymbolStore};

const SYMBOLS_DB: &str = ".agentic/index/symbols.db";

pub struct SymbolGraph {
    workspace_root: PathBuf,
    store: SymbolStore,
}

#[derive(Debug, Default, Serialize)]
pub struct SymbolSyncStats {
    pub files_parsed: usize,
    pub files_removed: usize,
    pub symbols: usize,
    pub refs: usize,
    pub elapsed_ms: u128,
}

/// The full outcome of a delta: graph stats plus any Next-Edit suggestions the
/// classifier produced for the files that changed.
#[derive(Debug, Default, Serialize)]
pub struct DeltaOutcome {
    #[serde(flatten)]
    pub stats: SymbolSyncStats,
    pub suggestions: Vec<EditSuggestion>,
}

/// One parsed file's results, carried from the parallel parse to the serial
/// insert phase.
struct Parsed {
    file: String,
    lang: Lang,
    defs: Vec<SymbolDef>,
    refs: Vec<SymbolRef>,
    imports: Vec<Import>,
}

fn now_ms() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis() as i64)
        .unwrap_or(0)
}

impl SymbolGraph {
    pub fn open(workspace_root: impl AsRef<Path>) -> Result<Self> {
        let workspace_root = workspace_root.as_ref().to_path_buf();
        let store = SymbolStore::open(&workspace_root.join(SYMBOLS_DB))?;
        Ok(Self { workspace_root, store })
    }

    /// Apply a Merkle delta: parse added+modified, delete removed. `hash_of`
    /// returns the file's content hash (from the Merkle snapshot) so the files
    /// row records exactly which bytes were parsed.
    pub fn apply_delta(
        &mut self,
        added: &[String],
        modified: &[String],
        removed: &[String],
        hash_of: &dyn Fn(&str) -> Option<String>,
    ) -> Result<DeltaOutcome> {
        let started = Instant::now();

        // Parse phase (parallel, pure). Skip files with no known language.
        let to_parse: Vec<(String, Lang)> = added
            .iter()
            .chain(modified.iter())
            .filter_map(|p| Lang::from_path(p).map(|l| (p.clone(), l)))
            .collect();

        let parsed: Vec<Parsed> = to_parse
            .par_iter()
            .filter_map(|(file, lang)| {
                let abs = self.workspace_root.join(file);
                let source = std::fs::read(&abs).ok()?;
                match extract(*lang, &source) {
                    Ok((defs, refs)) => {
                        // Imports are best-effort: a parse hiccup here shouldn't
                        // drop the file's symbols, just its import edges.
                        let imports = extract_imports(*lang, &source).unwrap_or_default();
                        Some(Parsed { file: file.clone(), lang: *lang, defs, refs, imports })
                    }
                    Err(e) => {
                        debug!(file, error = %e, "extract failed; skipping");
                        None
                    }
                }
            })
            .collect();

        // Insert phase (serial, transactional per file). For each file we
        // capture the OLD defs *before* overwriting, then classify against the
        // NEW defs *after* the upsert (so call-site queries see current refs).
        let indexed_at = now_ms();
        let mut stats = SymbolSyncStats::default();
        let mut suggestions = Vec::new();
        let mut crate_cache: HashMap<String, String> = HashMap::new();
        for p in &parsed {
            let old_defs = self.store.symbols_of_file(&p.file)?;
            let content_hash = hash_of(&p.file).unwrap_or_default();
            let crate_root = self.crate_root_for(&p.file, &mut crate_cache);
            self.store.upsert_file(
                &p.file,
                p.lang.name(),
                &content_hash,
                indexed_at,
                &crate_root,
                &p.defs,
                &p.refs,
                &p.imports,
            )?;
            stats.files_parsed += 1;
            stats.symbols += p.defs.len();
            stats.refs += p.refs.len();

            // Only files that already existed can yield a meaningful diff.
            if !old_defs.is_empty() {
                for c in classify(&old_defs, &p.defs) {
                    suggestions.push(self.build_suggestion(c, &p.file)?);
                }
            }
        }
        for file in removed {
            self.store.delete_file(file)?;
            stats.files_removed += 1;
        }

        stats.elapsed_ms = started.elapsed().as_millis();
        info!(
            parsed = stats.files_parsed,
            removed = stats.files_removed,
            symbols = stats.symbols,
            refs = stats.refs,
            suggestions = suggestions.len(),
            ms = stats.elapsed_ms,
            "symbol graph updated"
        );
        Ok(DeltaOutcome { stats, suggestions })
    }

    /// Turn a classification into an editor-facing suggestion. A rename pulls
    /// every call site of the OLD name and turns it into a mechanical
    /// replacement; a signature change lists the sites for the model to revisit.
    fn build_suggestion(
        &self,
        c: classifier::Classification,
        file: &str,
    ) -> Result<EditSuggestion> {
        let refs = self.store.call_sites(&c.old_name)?;
        let sites: Vec<EditSite> = refs
            .iter()
            .map(|r| EditSite {
                file: r.file.clone(),
                start_row: r.start_row,
                start_byte: r.start_byte,
                end_byte: r.end_byte,
            })
            .collect();

        // Safe-rename resolution (SYMBOL_GRAPH_SPEC.md §5). Classification runs
        // *after* the upsert, so the renamed definition already carries the new
        // name. If NO definition named `old_name` survives anywhere in the repo,
        // every remaining `old_name` reference must have bound to the symbol we
        // just renamed — applying the rewrite verbatim cannot over-match. If a
        // definition of `old_name` still exists (e.g. a same-named function in
        // another module), name-only matching is ambiguous, so we surface the
        // sites for manual review instead of auto-applying.
        let is_rename = c.kind == EditKind::Rename;
        let surviving = self.store.def_count(&c.old_name)?;
        let mechanical = is_rename && surviving == 0;

        if is_rename && surviving > 0 {
            warn!(
                file,
                old_name = %c.old_name,
                new_name = %c.new_name,
                surviving_defs = surviving,
                sites = sites.len(),
                "rename is ambiguous (name still defined elsewhere); surfacing sites for manual review, not auto-applying (name-based match, SYMBOL_GRAPH_SPEC §5)"
            );
        }

        let edits = if mechanical {
            refs.iter()
                .map(|r| Replacement {
                    file: r.file.clone(),
                    start_byte: r.start_byte,
                    end_byte: r.end_byte,
                    new_text: c.new_name.clone(),
                })
                .collect()
        } else {
            Vec::new()
        };

        Ok(EditSuggestion {
            kind: c.kind,
            old_name: c.old_name,
            new_name: c.new_name,
            mechanical,
            edits,
            sites,
        })
    }

    pub fn find_symbol(&self, name: &str) -> Result<Vec<SymbolRow>> {
        self.store.find_symbol(name)
    }

    pub fn call_sites(&self, name: &str) -> Result<Vec<RefRow>> {
        self.store.call_sites(name)
    }

    pub fn symbol_count(&self) -> Result<usize> {
        self.store.symbol_count()
    }

    /// Workspace root, so the semantic engine can read a definition's source.
    pub fn workspace_root(&self) -> &Path {
        &self.workspace_root
    }

    /// Nearest-ancestor crate root for a workspace-relative `file`: walk up its
    /// directory chain for the first dir holding a `Cargo.toml`. Returns the
    /// workspace-relative dir (`""` = workspace root crate, or no crate). Memoized
    /// per directory across one sync.
    fn crate_root_for(&self, file: &str, cache: &mut HashMap<String, String>) -> String {
        let dir = file.rsplit_once('/').map(|(d, _)| d).unwrap_or("");
        if let Some(c) = cache.get(dir) {
            return c.clone();
        }
        let mut cur = dir.to_string();
        let root = loop {
            let manifest = if cur.is_empty() {
                self.workspace_root.join("Cargo.toml")
            } else {
                self.workspace_root.join(&cur).join("Cargo.toml")
            };
            if manifest.is_file() {
                break cur.clone();
            }
            if cur.is_empty() {
                break String::new();
            }
            cur = cur.rsplit_once('/').map(|(d, _)| d.to_string()).unwrap_or_default();
        };
        cache.insert(dir.to_string(), root.clone());
        root
    }

    // ---- semantic-layer primitives (consumed by the semantic engine) -------

    pub fn resolve_candidates(&self, name: &str) -> Result<Vec<DefRecord>> {
        self.store.resolve_candidates(name)
    }

    pub fn def_by_qname(&self, qname: &str) -> Result<Option<DefRecord>> {
        self.store.def_by_qname(qname)
    }

    pub fn def_at(&self, file: &str, byte: usize) -> Result<Option<DefRecord>> {
        self.store.def_at(file, byte)
    }

    pub fn refs_in_symbol(&self, symbol_id: i64) -> Result<Vec<RefName>> {
        self.store.refs_in_symbol(symbol_id)
    }

    pub fn imports_of_file(&self, file: &str) -> Result<Vec<ImportRow>> {
        self.store.imports_of_file(file)
    }

    pub fn crate_root_of(&self, file: &str) -> Result<Option<String>> {
        self.store.crate_root_of(file)
    }
}
