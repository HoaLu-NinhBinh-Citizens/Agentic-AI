//! Symbol graph: tree-sitter definitions + call-site refs over the workspace.
//!
//! Driven by the Merkle `SyncDelta` — only `added` + `modified` files are
//! parsed, `removed` files are dropped. Parsing is pure (`extract`) so it runs
//! on the rayon pool; inserts are serial on the owning thread (SQLite).

pub mod extract;
pub mod lang;
pub mod store;

use std::path::{Path, PathBuf};
use std::time::{Instant, SystemTime, UNIX_EPOCH};

use anyhow::Result;
use rayon::prelude::*;
use serde::Serialize;
use tracing::{debug, info};

use extract::{extract, SymbolDef, SymbolRef};
use lang::Lang;
use store::{RefRow, SymbolRow, SymbolStore};

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

/// One parsed file's results, carried from the parallel parse to the serial
/// insert phase.
struct Parsed {
    file: String,
    lang: Lang,
    defs: Vec<SymbolDef>,
    refs: Vec<SymbolRef>,
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
    ) -> Result<SymbolSyncStats> {
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
                        Some(Parsed { file: file.clone(), lang: *lang, defs, refs })
                    }
                    Err(e) => {
                        debug!(file, error = %e, "extract failed; skipping");
                        None
                    }
                }
            })
            .collect();

        // Insert phase (serial, transactional per file).
        let indexed_at = now_ms();
        let mut stats = SymbolSyncStats::default();
        for p in &parsed {
            let content_hash = hash_of(&p.file).unwrap_or_default();
            self.store.upsert_file(
                &p.file,
                p.lang.name(),
                &content_hash,
                indexed_at,
                &p.defs,
                &p.refs,
            )?;
            stats.files_parsed += 1;
            stats.symbols += p.defs.len();
            stats.refs += p.refs.len();
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
            ms = stats.elapsed_ms,
            "symbol graph updated"
        );
        Ok(stats)
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
}
