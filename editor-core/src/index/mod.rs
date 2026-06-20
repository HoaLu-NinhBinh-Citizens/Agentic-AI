//! Workspace index engine.
//!
//! Phase 1 covers the Merkle layer: gitignore-aware walking + delta detection.
//! The symbol graph (tree-sitter) and embeddings (LanceDB) hang off the
//! `SyncDelta` this produces — they only ever process `added` + `modified`
//! files, never the whole repo.

pub mod merkle;

use std::collections::HashSet;
use std::fs;
use std::path::{Path, PathBuf};
use std::time::Instant;

use anyhow::{Context, Result};
use ignore::WalkBuilder;
use tracing::{debug, info};

use merkle::{build_snapshot, diff, mtime_to_ns, Candidate, Snapshot, SyncDelta};

use crate::context::{BuildRequest, BuiltPrompt, SemanticContextBuilder, Task};
use crate::detector::{DetectorConfig, DetectorRegistry, Finding, RuleMetadata};
use crate::planner::{Plan, PlanRequest, Planner};
use crate::retrieval::chunks::{chunk_file, Chunk};
use crate::retrieval::embed::{Embedder, HashEmbedder};
use crate::retrieval::lance_store::LanceVectorStore;
use crate::retrieval::ollama::OllamaEmbedder;
use crate::retrieval::vector::VectorStore;
use crate::retrieval::HybridRetriever;
use crate::semantic::{ImportEdge, ResolvedSymbol, SemanticContext, SemanticEngine, SemanticRequest};
use crate::symbols::classifier::EditSuggestion;
use crate::symbols::extract::extract;
use crate::symbols::lang::Lang;
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
    /// Hybrid retriever, built lazily and invalidated on each sync. A full
    /// rebuild (not incremental) for now — fine for moderate repos; the cost is
    /// logged so it's never a silent surprise.
    retriever: Option<HybridRetriever>,
    retrieval_cfg: RetrievalConfig,
    /// Bug-finding rules run on demand via `diagnose` (the `/fix` foundation).
    detectors: DetectorRegistry,
}

/// Selects which embedder + vector store the retriever uses. Default is the
/// offline HashEmbedder + in-memory store (no external deps); production wires
/// Ollama + LanceDB.
#[derive(Clone)]
pub struct RetrievalConfig {
    pub use_ollama: bool,
    pub ollama_host: String,
    pub ollama_model: String,
    pub ollama_dim: usize,
    pub use_lance: bool,
}

impl Default for RetrievalConfig {
    fn default() -> Self {
        Self {
            use_ollama: false,
            ollama_host: "http://localhost:11434".to_string(),
            ollama_model: "nomic-embed-text".to_string(),
            ollama_dim: 768,
            use_lance: false,
        }
    }
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

        // Auto-load a detector config from the workspace; a missing config.toml
        // is a clean fallback to built-in defaults (a malformed one errors).
        let detector_cfg = DetectorConfig::discover(&workspace_root)
            .context("loading detector config")?;

        info!(
            files = snapshot.entries.len(),
            root = %snapshot.root,
            "opened index engine"
        );
        Ok(Self {
            workspace_root,
            snapshot,
            graph,
            retriever: None,
            retrieval_cfg: RetrievalConfig::default(),
            detectors: DetectorRegistry::with_config(detector_cfg),
        })
    }

    /// Run the bug detectors over one workspace-relative file. Reads the file
    /// fresh (the editor may have unsaved-then-saved it) and returns findings
    /// sorted Critical-first. Powers a `diagnostics/file` request and, later,
    /// `/fix @file:line`.
    pub fn diagnose(&self, file: &str) -> Result<Vec<Finding>> {
        let abs = self.workspace_root.join(file);
        let source = fs::read(&abs).with_context(|| format!("reading {file} for diagnostics"))?;
        self.detectors.analyze(file, source)
    }

    /// Apply byte-range `edits` to `file`, then *verify* by re-running the
    /// detectors on the patched bytes and diffing against the pre-edit findings.
    /// This closes the detect -> fix -> verify loop behind `/fix`.
    ///
    /// `dry_run` computes the full diff (resolved / introduced) and returns the
    /// patched content WITHOUT touching disk, so the editor can preview a patch
    /// and gate on a clean verify. A real apply writes atomically (temp +
    /// rename) so a crash mid-write can't leave a half-patched file.
    ///
    /// Offsets index the file's *current* on-disk bytes. Edits must stay in
    /// bounds, not overlap, and land on UTF-8 char boundaries — otherwise the
    /// call errors and nothing is written.
    pub fn apply_fix(&self, file: &str, edits: &[Edit], dry_run: bool) -> Result<FixOutcome> {
        let abs = self.workspace_root.join(file);
        let original = fs::read(&abs).with_context(|| format!("reading {file} for fix/apply"))?;
        let patched = apply_edits(&original, edits)
            .with_context(|| format!("applying edits to {file}"))?;

        // Verify: run the same detectors over the old and new bytes and diff.
        // Files in an unsupported language yield empty findings on both sides —
        // the apply still works, just without a verification signal.
        let before = self.detectors.analyze(file, original)?;
        let after = self.detectors.analyze(file, patched.clone())?;
        let (resolved, introduced) = diff_findings(&before, &after);

        let mut applied = false;
        if !dry_run {
            write_atomic(&abs, &patched).with_context(|| format!("writing patched {file}"))?;
            applied = true;
        }

        info!(
            file,
            dry_run,
            applied,
            before = before.len(),
            after = after.len(),
            resolved = resolved.len(),
            introduced = introduced.len(),
            "fix/apply verified"
        );

        Ok(FixOutcome {
            file: file.to_string(),
            dry_run,
            applied,
            before_count: before.len(),
            after_count: after.len(),
            resolved,
            introduced,
            // Hand the patched text back only on a dry run (the editor already
            // has the file once it's written).
            patched: if dry_run {
                Some(String::from_utf8_lossy(&patched).into_owned())
            } else {
                None
            },
        })
    }

    /// Replace the detector config at run time (e.g. an inline config passed in
    /// `initialize`, overriding the auto-discovered file).
    pub fn set_detector_config(&mut self, cfg: DetectorConfig) {
        self.detectors.set_config(cfg);
    }

    /// Metadata for every registered detector under the current config (id,
    /// description, effective severity, enabled state, languages, options).
    pub fn detector_metadata(&self) -> Vec<RuleMetadata> {
        self.detectors.metadata()
    }

    /// Override retrieval backends (Ollama embedder / LanceDB store). Invalidates
    /// any built retriever so the next build uses the new config.
    pub fn set_retrieval_config(&mut self, cfg: RetrievalConfig) {
        self.retrieval_cfg = cfg;
        self.retriever = None;
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

        // Keep the retriever fresh. If it's built and supports incremental
        // updates (in-memory backend), patch only the changed files instead of
        // dropping the whole index (which forced a full rebuild every save).
        // Otherwise (not built yet, or LanceDB backend) drop for a lazy rebuild.
        let incremental = self
            .retriever
            .as_ref()
            .map(|r| r.supports_incremental())
            .unwrap_or(false);
        if incremental {
            let stale: Vec<String> =
                modified.iter().chain(removed.iter()).cloned().collect();
            let fresh = self.chunk_paths(added.iter().chain(modified.iter()));
            let mut ok = true;
            if let Some(r) = self.retriever.as_mut() {
                if let Err(e) = r.apply_delta(&stale, fresh) {
                    debug!(error = %e, "retriever incremental update failed; dropping for rebuild");
                    ok = false;
                }
            }
            if !ok {
                self.retriever = None;
            } else if self.persistable_retriever() {
                // Re-snapshot so the next session loads instead of rebuilding.
                let dir = self.retriever_dir();
                if let Some(r) = self.retriever.as_ref() {
                    if let Err(e) = r.persist(&dir, &root) {
                        debug!(error = %e, "retriever persist failed");
                    }
                }
            }
        } else {
            self.retriever = None;
        }

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

    /// Resolve a name used in `from_file` to its definition(s), ranked by scope
    /// with a confidence verdict (semantic cross-file resolution).
    pub fn resolve_symbol(&self, name: &str, from_file: &str) -> Result<Vec<ResolvedSymbol>> {
        SemanticEngine::new(&self.graph).resolve(name, from_file)
    }

    /// The minimal relevant code for a task centered on a focus symbol — the
    /// semantic context a planner/agent consumes instead of raw grep results.
    pub fn semantic_context(&self, req: &SemanticRequest) -> Result<SemanticContext> {
        SemanticEngine::new(&self.graph).context(req)
    }

    /// File-level dependency edges (resolved imports) for `file`.
    pub fn file_dependencies(&self, file: &str) -> Result<Vec<ImportEdge>> {
        SemanticEngine::new(&self.graph).file_dependencies(file)
    }

    /// Build a deterministic, rule-based execution plan for a request. The plan
    /// is the contract the future Execution Engine consumes: an intent, a task
    /// DAG, a dependency-ordered schedule, and per-task context/verification
    /// plans. This sits *above* the semantic engine — it produces context
    /// *requests*, it does not resolve them (no symbol lookup, no LLM).
    pub fn plan(&self, req: &PlanRequest) -> Plan {
        Planner::plan(req)
    }

    /// Parse + chunk the given workspace-relative paths (skipping non-code).
    fn chunk_paths<'a>(&self, paths: impl Iterator<Item = &'a String>) -> Vec<Chunk> {
        let mut out = Vec::new();
        for path in paths {
            let Some(lang) = Lang::from_path(path) else { continue };
            let abs = self.workspace_root.join(path);
            let Ok(source) = fs::read(&abs) else { continue };
            let defs = match extract(lang, &source) {
                Ok((defs, _refs)) => defs,
                Err(_) => continue,
            };
            out.extend(chunk_file(path, &source, &defs));
        }
        out
    }

    fn make_embedder(&self) -> Box<dyn Embedder> {
        let cfg = &self.retrieval_cfg;
        if cfg.use_ollama {
            Box::new(OllamaEmbedder::new(
                cfg.ollama_host.clone(),
                cfg.ollama_model.clone(),
                cfg.ollama_dim,
            ))
        } else {
            Box::new(HashEmbedder::default())
        }
    }

    fn retriever_dir(&self) -> PathBuf {
        self.workspace_root.join(INDEX_DIR).join("retriever")
    }

    /// Whether the retriever can persist + update incrementally (in-memory
    /// backend). The LanceDB backend persists vectors itself but isn't wired
    /// for our snapshot persistence, so it stays on lazy full rebuild.
    fn persistable_retriever(&self) -> bool {
        !self.retrieval_cfg.use_lance
    }

    /// Ensure the retriever exists: load a valid persisted index, else build it
    /// (persisting on the way for the persistable in-memory backend).
    fn ensure_retriever(&mut self) -> Result<()> {
        if self.retriever.is_some() {
            return Ok(());
        }
        let started = Instant::now();

        if self.persistable_retriever() {
            let dir = self.retriever_dir();
            // Try the persisted index first — skips the rebuild on reopen.
            if let Some(r) =
                HybridRetriever::try_load(self.make_embedder(), &dir, &self.snapshot.root)?
            {
                info!(ms = started.elapsed().as_millis(), "loaded persisted retriever");
                self.retriever = Some(r);
                return Ok(());
            }
            let all_chunks = self.chunk_paths(self.snapshot.entries.keys());
            let n = all_chunks.len();
            let r = HybridRetriever::build_persistent(self.make_embedder(), all_chunks, &dir)?;
            r.persist(&dir, &self.snapshot.root)?;
            info!(chunks = n, ms = started.elapsed().as_millis(), "built + persisted hybrid retriever");
            self.retriever = Some(r);
            return Ok(());
        }

        // LanceDB path: in-RAM lexical, vectors in Lance, lazy rebuild.
        let all_chunks = self.chunk_paths(self.snapshot.entries.keys());
        let n = all_chunks.len();
        let embedder = self.make_embedder();
        let dim = embedder.dim();
        let uri = self.workspace_root.join(INDEX_DIR).join("vectors.lance");
        let store: Box<dyn VectorStore> = Box::new(LanceVectorStore::open(&uri.to_string_lossy(), dim)?);
        let retriever = HybridRetriever::build_with(embedder, store, all_chunks)?;
        info!(chunks = n, lance = true, ms = started.elapsed().as_millis(), "built hybrid retriever");
        self.retriever = Some(retriever);
        Ok(())
    }

    /// Build a completion prompt for a cursor position (FIM). Semantic-first:
    /// the cursor symbol's resolved callees/imports lead, retrieval fills the
    /// rest. Falls back to retrieval-only when the cursor isn't in a known symbol.
    pub fn build_completion_context(
        &mut self,
        file: &str,
        cursor_byte: usize,
        max_tokens: usize,
        query: Option<String>,
    ) -> Result<BuiltPrompt> {
        self.build_context(&BuildRequest {
            task: Task::Completion,
            file: file.to_string(),
            cursor_byte,
            query,
            max_tokens,
            focus_symbol: None,
        })
    }

    /// The default context entry point for *every* coding request (completion,
    /// chat, agent). Routes through the semantic context engine, with hybrid
    /// retrieval as the low-confidence fallback. The Planner/Execution Engine
    /// consume this rather than raw retrieval.
    pub fn build_context(&mut self, req: &BuildRequest) -> Result<BuiltPrompt> {
        self.ensure_retriever()?;
        let retriever = self.retriever.as_ref().expect("retriever just built");
        let cb = SemanticContextBuilder::new(&self.graph, retriever, &self.workspace_root);
        cb.build(req)
    }

    /// Retrieve the top-`k` relevant snippets for a free-form query. Powers
    /// Cmd+K inline edit (and, later, chat): the editor composes the instruct
    /// prompt; the daemon supplies the codebase context.
    pub fn retrieve(&mut self, query: &str, k: usize) -> Result<Vec<RetrievedSnippet>> {
        self.ensure_retriever()?;
        let retriever = self.retriever.as_ref().expect("retriever just built");
        Ok(retriever
            .search(query, k)?
            .into_iter()
            .map(|sc| RetrievedSnippet {
                file: sc.chunk.file,
                start_row: sc.chunk.start_row,
                text: sc.chunk.text,
            })
            .collect())
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

/// One edit to apply to a file: replace the byte range `[start_byte, end_byte)`
/// with `new_text`. Offsets index the file's current on-disk bytes. A pure
/// insertion is `start_byte == end_byte`; a deletion is an empty `new_text`.
#[derive(Debug, Clone, serde::Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Edit {
    pub start_byte: usize,
    pub end_byte: usize,
    pub new_text: String,
}

/// Result of an `apply_fix`. Reports the verify diff so the editor can show
/// "fixed N, introduced M" and refuse to apply a patch that regresses.
#[derive(Debug, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct FixOutcome {
    pub file: String,
    pub dry_run: bool,
    /// True once the patched bytes are on disk (always false for a dry run).
    pub applied: bool,
    /// Detector findings before the edit (current file).
    pub before_count: usize,
    /// Detector findings after the edit (the patched bytes).
    pub after_count: usize,
    /// Findings present before but gone after — what this patch fixed.
    pub resolved: Vec<Finding>,
    /// Findings present only after — regressions the patch introduced. An empty
    /// list is the "clean verify" the editor should gate a real apply on.
    pub introduced: Vec<Finding>,
    /// The full patched file content, returned only on a dry run for preview.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub patched: Option<String>,
}

/// Splice `edits` into `src`. Edits are sorted by start offset, then validated
/// (in bounds, non-overlapping) and applied left-to-right. Errors rather than
/// silently producing garbage so a bad edit set never reaches disk.
fn apply_edits(src: &[u8], edits: &[Edit]) -> Result<Vec<u8>> {
    let mut ordered: Vec<&Edit> = edits.iter().collect();
    ordered.sort_by_key(|e| e.start_byte);

    let mut out = Vec::with_capacity(src.len());
    let mut cursor = 0usize;
    for e in ordered {
        if e.start_byte > e.end_byte {
            anyhow::bail!("edit start_byte {} > end_byte {}", e.start_byte, e.end_byte);
        }
        if e.end_byte > src.len() {
            anyhow::bail!(
                "edit end_byte {} past end of file ({} bytes)",
                e.end_byte,
                src.len()
            );
        }
        // `cursor` is the end of the previous edit; a start before it overlaps.
        if e.start_byte < cursor {
            anyhow::bail!("overlapping edits near byte {}", e.start_byte);
        }
        out.extend_from_slice(&src[cursor..e.start_byte]);
        out.extend_from_slice(e.new_text.as_bytes());
        cursor = e.end_byte;
    }
    out.extend_from_slice(&src[cursor..]);

    // Offsets that split a multi-byte char would corrupt the file; the detectors
    // tolerate it (lossy), but we must never write invalid UTF-8 source.
    if std::str::from_utf8(&out).is_err() {
        anyhow::bail!("edit produced invalid UTF-8 (an offset is not on a char boundary)");
    }
    Ok(out)
}

/// Diff two finding sets keyed by `(rule_id, offending line)` rather than line
/// number — an edit shifts line numbers, but the offending source text is a
/// stable identity. `resolved` = before − after, `introduced` = after − before.
fn diff_findings(before: &[Finding], after: &[Finding]) -> (Vec<Finding>, Vec<Finding>) {
    fn key(f: &Finding) -> (String, String) {
        (f.rule_id.clone(), f.before.clone().unwrap_or_else(|| f.message.clone()))
    }
    let before_keys: HashSet<(String, String)> = before.iter().map(key).collect();
    let after_keys: HashSet<(String, String)> = after.iter().map(key).collect();
    let resolved = before.iter().filter(|f| !after_keys.contains(&key(f))).cloned().collect();
    let introduced = after.iter().filter(|f| !before_keys.contains(&key(f))).cloned().collect();
    (resolved, introduced)
}

/// Write `bytes` to `path` atomically: write a sibling temp file, then rename
/// over the target (rename is atomic on the same filesystem).
fn write_atomic(path: &Path, bytes: &[u8]) -> Result<()> {
    let mut tmp = path.as_os_str().to_owned();
    tmp.push(".aircore-tmp");
    let tmp = PathBuf::from(tmp);
    fs::write(&tmp, bytes).context("writing temp file")?;
    fs::rename(&tmp, path).context("renaming patched file into place")?;
    Ok(())
}

/// Lightweight status payload returned over IPC.
#[derive(Debug, serde::Serialize)]
pub struct IndexStatus {
    pub root: String,
    pub indexed_files: usize,
    pub symbols: usize,
    pub workspace: String,
}

/// A retrieved context snippet returned to the editor (Cmd+K / chat).
#[derive(Debug, serde::Serialize)]
pub struct RetrievedSnippet {
    pub file: String,
    pub start_row: usize,
    pub text: String,
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
