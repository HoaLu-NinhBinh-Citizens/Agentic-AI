//! End-to-end tests for the Merkle index engine: first sync indexes
//! everything, a no-op sync hashes nothing, and edits show up as deltas.

use std::fs;

use aircore::index::IndexEngine;
use tempfile::TempDir;

fn write(dir: &TempDir, rel: &str, contents: &str) {
    let path = dir.path().join(rel);
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).unwrap();
    }
    fs::write(path, contents).unwrap();
}

#[test]
fn first_sync_indexes_all_files() {
    let dir = TempDir::new().unwrap();
    write(&dir, "a.rs", "fn a() {}");
    write(&dir, "src/b.rs", "fn b() {}");

    let mut engine = IndexEngine::open(dir.path()).unwrap();
    let delta = engine.sync().unwrap().delta;

    assert_eq!(delta.total_files, 2);
    assert_eq!(delta.hashed_files, 2);
    assert_eq!(delta.added.len(), 2);
    assert!(delta.modified.is_empty());
    assert!(delta.removed.is_empty());
}

#[test]
fn second_sync_is_a_noop_when_nothing_changes() {
    let dir = TempDir::new().unwrap();
    write(&dir, "a.rs", "fn a() {}");

    let mut engine = IndexEngine::open(dir.path()).unwrap();
    engine.sync().unwrap();
    let delta = engine.sync().unwrap().delta;

    // Metadata unchanged -> nothing re-hashed, no deltas.
    assert_eq!(delta.hashed_files, 0);
    assert!(delta.added.is_empty());
    assert!(delta.modified.is_empty());
    assert!(delta.removed.is_empty());
}

#[test]
fn edits_and_deletes_show_up_as_deltas() {
    let dir = TempDir::new().unwrap();
    write(&dir, "a.rs", "fn a() {}");
    write(&dir, "b.rs", "fn b() {}");

    let mut engine = IndexEngine::open(dir.path()).unwrap();
    engine.sync().unwrap();

    // Modify a, delete b, add c.
    write(&dir, "a.rs", "fn a() { /* changed */ }");
    fs::remove_file(dir.path().join("b.rs")).unwrap();
    write(&dir, "c.rs", "fn c() {}");

    let delta = engine.sync().unwrap().delta;
    assert_eq!(delta.modified, vec!["a.rs".to_string()]);
    assert_eq!(delta.removed, vec!["b.rs".to_string()]);
    assert_eq!(delta.added, vec!["c.rs".to_string()]);
}

#[test]
fn root_hash_is_stable_across_reopen() {
    let dir = TempDir::new().unwrap();
    write(&dir, "a.rs", "fn a() {}");

    let root1 = {
        let mut engine = IndexEngine::open(dir.path()).unwrap();
        engine.sync().unwrap().delta.root
    };
    // Reopen from the persisted snapshot; status root must match.
    let engine = IndexEngine::open(dir.path()).unwrap();
    assert_eq!(engine.status().root, root1);
}

#[test]
fn gitignored_files_are_skipped() {
    let dir = TempDir::new().unwrap();
    write(&dir, ".gitignore", "ignored.rs\n");
    write(&dir, "kept.rs", "fn kept() {}");
    write(&dir, "ignored.rs", "fn ignored() {}");

    let mut engine = IndexEngine::open(dir.path()).unwrap();
    let delta = engine.sync().unwrap().delta;

    assert!(delta.added.contains(&"kept.rs".to_string()));
    assert!(delta.added.contains(&".gitignore".to_string()));
    assert!(!delta.added.contains(&"ignored.rs".to_string()));
}
