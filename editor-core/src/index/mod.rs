//! Workspace index engine.
//!
//! Phase 1 covers the Merkle layer: gitignore-aware walking + delta detection.
//! The symbol graph (tree-sitter) and embeddings (LanceDB) hang off the
//! `SyncDelta` this produces — they only ever process `added` + `modified`
//! files, never the whole repo.

pub mod merkle;

use std::fs;
use std::path::{Path, PathBuf};
use std::time::Instant;

use anyhow::{Context, Result};
use ignore::WalkBuilder;
use tracing::{debug, info};

use merkle::{build_snapshot, diff, mtime_to_ns, Candidate, Snapshot, SyncDelta};

use crate::symbols::classifier::EditSuggestion;
use crate::symbols::store::{RefRow, SymbolRow};
use crate::symbols::{SymbolGraph, SymbolSyncStats};

/// Directory under the workspace root where we persist index state.
const INDEX_DIR: &str = ".agentic/index";
const SNAPSHOT_FILE: &str = "merkle.json";

/// Owns the persisted snapshot + symbol graph for one workspace.
pub struct IndexEngine {
    workspace_root: PathBuf,
    snapshot: Snapshot,
    graph: SymbolGraph,
}

impl IndexEngine {
    /// Open the engine for `workspace_root`, loading any previous snapshot so
    /// the first sync is already a delta rather than a full index.
    pub fn open(workspace_root: impl AsRef<Path>) -> Result<Self> {
        let workspace_root = workspace_root.as_ref().to_path_buf();
        let mut snapshot = Self::load_snapshot(&workspace_root).unwrap_or_default();
        let graph = SymbolGraph::open(&workspace_root)?;

        // Consistency guard: the Merkle snapshot and the symbol DB are separate
        // persisted stores and can diverge (e.g. the DB was deleted, or a new
        // consumer was added after the snapshot was written). If the graph is
        // empty but the snapshot tracks files, those files would never re-enter
        // the delta. Reset the snapshot so the next sync reprocesses everything.
        if graph.symbol_count().unwrap_or(0) == 0 && !snapshot.entries.is_empty() {
            info!("symbol graph empty but snapshot non-empty; forcing full reindex");
            snapshot = Snapshot::default();
        }

        info!(
            files = snapshot.entries.len(),
            root = %snapshot.root,
            "opened index engine"
        );
        Ok(Self { workspace_root, snapshot, graph })
    }

    fn snapshot_path(root: &Path) -> PathBuf {
        root.join(INDEX_DIR).join(SNAPSHOT_FILE)
    }

    fn load_snapshot(root: &Path) -> Option<Snapshot> {
        let path = Self::snapshot_path(root);
        let bytes = fs::read(&path).ok()?;
        serde_json::from_slice(&bytes).ok()
    }

    fn persist_snapshot(&self) -> Result<()> {
        let dir = self.workspace_root.join(INDEX_DIR);
        fs::create_dir_all(&dir).context("creating index dir")?;
        let path = Self::snapshot_path(&self.workspace_root);
        let bytes = serde_json::to_vec(&self.snapshot).context("serializing snapshot")?;
        // Atomic-ish write: temp file then rename so a crash mid-write can't
        // corrupt the persisted snapshot.
        let tmp = path.with_extension("json.tmp");
        fs::write(&tmp, &bytes).context("writing temp snapshot")?;
        fs::rename(&tmp, &path).context("renaming snapshot into place")?;
        Ok(())
    }

    /// Walk the workspace, hashing only files whose metadata changed, diff
    /// against the previous snapshot, then update the symbol graph from the
    /// delta. Persists the new snapshot on success.
    pub fn sync(&mut self) -> Result<SyncResult> {
        let started = Instant::now();
        let candidates = self.collect_candidates();
        let total = candidates.len();
        debug!(total, "collected walk candidates");

        let (current, hashed) = build_snapshot(candidates, &self.snapshot);
        let (added, modified, removed) = diff(&self.snapshot, &current);
        let root = current.root.clone();
        self.snapshot = current;
        self.persist_snapshot()?;

        // Update the symbol graph from this delta only (never the whole repo).
        // The closure feeds each file's content hash from the new snapshot.
        let snapshot = &self.snapshot;
        let hash_of =
            |path: &str| snapshot.entries.get(path).map(|e| e.hash.clone());
        let outcome = self.graph.apply_delta(&added, &modified, &removed, &hash_of)?;

        let delta = SyncDelta {
            added,
            modified,
            removed,
            root,
            total_files: total,
            hashed_files: hashed,
            elapsed_ms: started.elapsed().as_millis(),
        };
        info!(
            total,
            hashed,
            added = delta.added.len(),
            modified = delta.modified.len(),
            removed = delta.removed.len(),
            ms = delta.elapsed_ms,
            "sync complete"
        );
        Ok(SyncResult {
            delta,
            symbols: outcome.stats,
            suggestions: outcome.suggestions,
        })
    }

    /// Find symbol definitions by exact name.
    pub fn find_symbol(&self, name: &str) -> Result<Vec<SymbolRow>> {
        self.graph.find_symbol(name)
    }

    /// Find call sites of a name — powers Next Edit Prediction.
    pub fn call_sites(&self, name: &str) -> Result<Vec<RefRow>> {
        self.graph.call_sites(name)
    }

    /// Snapshot summary without re-walking — used by `index/status`.
    pub fn status(&self) -> IndexStatus {
        IndexStatus {
            root: self.snapshot.root.clone(),
            indexed_files: self.snapshot.entries.len(),
            symbols: self.graph.symbol_count().unwrap_or(0),
            workspace: self.workspace_root.display().to_string(),
        }
    }

    /// Gitignore-aware walk. We let the `ignore` crate honor `.gitignore`,
    /// `.ignore`, and global git excludes, then add our own index dir and the
    /// usual binary/noise directories on top.
    fn collect_candidates(&self) -> Vec<Candidate> {
        let mut builder = WalkBuilder::new(&self.workspace_root);
        builder
            .hidden(false) // we want dotfiles like .env.example, but...
            .git_ignore(true)
            .git_global(true)
            .git_exclude(true)
            // Honor .gitignore even when the workspace isn't (yet) a git repo.
            .require_git(false)
            .parents(true);
        // ...always skip our own state and well-known heavy dirs.
        let mut overrides = ignore::overrides::OverrideBuilder::new(&self.workspace_root);
        for pat in ["!.git/", "!.agentic/", "!node_modules/", "!target/", "!.venv/"] {
            let _ = overrides.add(pat);
        }
        if let Ok(ov) = overrides.build() {
            builder.overrides(ov);
        }

        let mut candidates = Vec::new();
        for result in builder.build() {
            let entry = match result {
                Ok(e) => e,
                Err(_) => continue,
            };
            // Only regular files.
            if !entry.file_type().map(|t| t.is_file()).unwrap_or(false) {
                continue;
            }
            let abs_path = entry.into_path();
            let meta = match fs::metadata(&abs_path) {
                Ok(m) => m,
                Err(_) => continue,
            };
            let rel_path = match abs_path.strip_prefix(&self.workspace_root) {
                Ok(p) => p.to_string_lossy().replace('\\', "/"),
                Err(_) => continue,
            };
            candidates.push(Candidate {
                rel_path,
                abs_path,
                mtime_ns: mtime_to_ns(&meta),
                size: meta.len(),
            });
        }
        candidates
    }
}

/// Lightweight status payload returned over IPC.
#[derive(Debug, serde::Serialize)]
pub struct IndexStatus {
    pub root: String,
    pub indexed_files: usize,
    pub symbols: usize,
    pub workspace: String,
}

/// Full result of a sync pass: Merkle delta, symbol-graph stats, and any
/// Next-Edit suggestions for the editor to render as "Tab to jump" indicators.
#[derive(Debug, serde::Serialize)]
pub struct SyncResult {
    #[serde(flatten)]
    pub delta: SyncDelta,
    pub symbols: SymbolSyncStats,
    pub suggestions: Vec<EditSuggestion>,
}
