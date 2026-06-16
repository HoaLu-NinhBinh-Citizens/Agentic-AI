//! Merkle snapshot of a workspace: the foundation for delta-only indexing.
//!
//! The expensive operation in indexing is content hashing, so we gate it on
//! cheap filesystem metadata: a file is only re-hashed when its `(mtime, size)`
//! pair differs from the previous snapshot. The per-file content hashes are
//! then folded into a single `root` hash, giving an O(1) "did anything change
//! at all" check and an O(changed) re-index downstream.

use std::collections::BTreeMap;
use std::fs;
use std::path::Path;
use std::time::UNIX_EPOCH;

use rayon::prelude::*;
use serde::{Deserialize, Serialize};

/// One tracked file. `path` is workspace-relative and uses forward slashes so
/// snapshots are stable across OSes.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FileEntry {
    pub path: String,
    /// Modification time in nanoseconds since the Unix epoch.
    pub mtime_ns: u64,
    pub size: u64,
    /// Hex-encoded blake3 of the file contents.
    pub hash: String,
}

/// A complete content-addressed view of the workspace at one point in time.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct Snapshot {
    /// Keyed by relative path; BTreeMap keeps iteration order deterministic so
    /// the root hash is reproducible.
    pub entries: BTreeMap<String, FileEntry>,
    /// Hex blake3 over all `(path, hash)` pairs in sorted order.
    pub root: String,
}

impl Snapshot {
    /// Recompute the root from the current entries.
    pub fn recompute_root(&mut self) {
        let mut hasher = blake3::Hasher::new();
        for entry in self.entries.values() {
            hasher.update(entry.path.as_bytes());
            hasher.update(b"\0");
            hasher.update(entry.hash.as_bytes());
            hasher.update(b"\n");
        }
        self.root = hasher.finalize().to_hex().to_string();
    }
}

/// The result of diffing a freshly computed snapshot against the previous one.
#[derive(Debug, Default, Serialize)]
pub struct SyncDelta {
    pub added: Vec<String>,
    pub modified: Vec<String>,
    pub removed: Vec<String>,
    pub root: String,
    pub total_files: usize,
    /// How many files actually needed content hashing this pass (the rest were
    /// served from the previous snapshot via the mtime/size gate).
    pub hashed_files: usize,
    pub elapsed_ms: u128,
}

/// Hash a single file's contents. blake3 is memory-mapped internally for large
/// files and SIMD-accelerated, which is why it beats sha256 here.
fn hash_file(abs: &Path) -> std::io::Result<String> {
    let bytes = fs::read(abs)?;
    Ok(blake3::hash(&bytes).to_hex().to_string())
}

/// A candidate file discovered by the walker, with its cheap metadata already
/// stat'd so the hashing pass can decide whether to reuse a cached hash.
pub struct Candidate {
    pub rel_path: String,
    pub abs_path: std::path::PathBuf,
    pub mtime_ns: u64,
    pub size: u64,
}

/// Build a new snapshot from the walker's candidates, reusing hashes from
/// `previous` wherever `(mtime, size)` is unchanged. Hashing runs in parallel
/// across the candidates that actually changed.
pub fn build_snapshot(candidates: Vec<Candidate>, previous: &Snapshot) -> (Snapshot, usize) {
    // Partition into "reuse cached hash" and "must hash now".
    let entries: Vec<(String, FileEntry, bool)> = candidates
        .into_par_iter()
        .map(|c| {
            if let Some(prev) = previous.entries.get(&c.rel_path) {
                if prev.mtime_ns == c.mtime_ns && prev.size == c.size {
                    // Unchanged metadata: trust the cached content hash.
                    return (
                        c.rel_path.clone(),
                        FileEntry {
                            path: c.rel_path,
                            mtime_ns: c.mtime_ns,
                            size: c.size,
                            hash: prev.hash.clone(),
                        },
                        false,
                    );
                }
            }
            // New or changed: hash the contents. On a read error we skip the
            // file by emitting an empty hash sentinel the caller filters out.
            let hash = hash_file(&c.abs_path).unwrap_or_default();
            (
                c.rel_path.clone(),
                FileEntry { path: c.rel_path, mtime_ns: c.mtime_ns, size: c.size, hash },
                true,
            )
        })
        .collect();

    let mut snapshot = Snapshot::default();
    let mut hashed = 0usize;
    for (path, entry, was_hashed) in entries {
        if entry.hash.is_empty() {
            continue; // unreadable file, drop it
        }
        if was_hashed {
            hashed += 1;
        }
        snapshot.entries.insert(path, entry);
    }
    snapshot.recompute_root();
    (snapshot, hashed)
}

/// Diff `current` against `previous`, classifying each path.
pub fn diff(previous: &Snapshot, current: &Snapshot) -> (Vec<String>, Vec<String>, Vec<String>) {
    let mut added = Vec::new();
    let mut modified = Vec::new();
    let mut removed = Vec::new();

    for (path, cur) in &current.entries {
        match previous.entries.get(path) {
            None => added.push(path.clone()),
            Some(prev) if prev.hash != cur.hash => modified.push(path.clone()),
            Some(_) => {}
        }
    }
    for path in previous.entries.keys() {
        if !current.entries.contains_key(path) {
            removed.push(path.clone());
        }
    }
    (added, modified, removed)
}

/// Convert a `SystemTime` to nanoseconds since the Unix epoch (0 if it predates
/// the epoch, which only happens with corrupt metadata).
pub fn mtime_to_ns(meta: &fs::Metadata) -> u64 {
    meta.modified()
        .ok()
        .and_then(|t| t.duration_since(UNIX_EPOCH).ok())
        .map(|d| d.as_nanos() as u64)
        .unwrap_or(0)
}
