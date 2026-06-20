//! Tests for the detect -> fix -> verify loop (`IndexEngine::apply_fix`):
//! a real apply writes and resolves the finding, a dry run previews without
//! touching disk, a regressing patch is reported, and bad edits error out.

use std::fs;

use aircore::index::{Edit, IndexEngine};

/// A workspace with one file; returns (tempdir, engine). The tempdir is kept
/// alive by the caller.
fn workspace(name: &str, src: &str) -> (tempfile::TempDir, IndexEngine) {
    let dir = tempfile::tempdir().unwrap();
    fs::write(dir.path().join(name), src).unwrap();
    let engine = IndexEngine::open(dir.path()).unwrap();
    (dir, engine)
}

/// Byte range of the first occurrence of `needle` in `src`.
fn span(src: &str, needle: &str) -> (usize, usize) {
    let start = src.find(needle).expect("needle present");
    (start, start + needle.len())
}

const UNWRAP_SRC: &str = "fn load() {\n    let f = std::fs::read(\"model.bin\").unwrap();\n}\n";

#[test]
fn apply_resolves_finding_and_writes_file() {
    let (dir, engine) = workspace("load.rs", UNWRAP_SRC);

    // Replace `.unwrap()` with `?` — the fix `rust/unwrap` suggests.
    let (s, e) = span(UNWRAP_SRC, ".unwrap()");
    let edits = vec![Edit { start_byte: s, end_byte: e, new_text: "?".to_string() }];

    let out = engine.apply_fix("load.rs", &edits, false).unwrap();

    assert!(out.applied, "non-dry-run must write: {out:?}");
    assert!(
        out.resolved.iter().any(|f| f.rule_id == "rust/unwrap"),
        "the unwrap finding should be resolved: {out:?}"
    );
    assert!(out.introduced.is_empty(), "clean fix introduces nothing: {out:?}");
    assert_eq!(out.after_count, 0, "no findings remain: {out:?}");

    // The file on disk now contains the patch.
    let on_disk = fs::read_to_string(dir.path().join("load.rs")).unwrap();
    assert!(on_disk.contains('?') && !on_disk.contains(".unwrap()"), "patched: {on_disk:?}");
}

#[test]
fn dry_run_previews_without_writing() {
    let (dir, engine) = workspace("load.rs", UNWRAP_SRC);
    let (s, e) = span(UNWRAP_SRC, ".unwrap()");
    let edits = vec![Edit { start_byte: s, end_byte: e, new_text: "?".to_string() }];

    let out = engine.apply_fix("load.rs", &edits, true).unwrap();

    assert!(!out.applied, "dry run must not write");
    assert!(out.resolved.iter().any(|f| f.rule_id == "rust/unwrap"));
    let patched = out.patched.expect("dry run returns patched content");
    assert!(patched.contains('?') && !patched.contains(".unwrap()"));

    // File on disk is untouched.
    let on_disk = fs::read_to_string(dir.path().join("load.rs")).unwrap();
    assert_eq!(on_disk, UNWRAP_SRC, "dry run left the file unchanged");
}

#[test]
fn regressing_patch_is_reported_as_introduced() {
    // Start clean (uses `?`), then patch it back to `.unwrap()` — verify catches
    // the new finding the edit introduced.
    let clean = "fn load() -> anyhow::Result<()> {\n    let f = std::fs::read(\"m.bin\")?;\n    Ok(())\n}\n";
    let (_dir, engine) = workspace("load.rs", clean);

    let (s, e) = span(clean, ")?;");
    let edits = vec![Edit { start_byte: s, end_byte: e, new_text: ").unwrap();".to_string() }];

    let out = engine.apply_fix("load.rs", &edits, true).unwrap();
    assert!(
        out.introduced.iter().any(|f| f.rule_id == "rust/unwrap"),
        "patch that adds an unwrap must be reported as introduced: {out:?}"
    );
}

#[test]
fn out_of_bounds_edit_errors_and_does_not_write() {
    let (dir, engine) = workspace("load.rs", UNWRAP_SRC);
    let edits = vec![Edit { start_byte: 0, end_byte: 10_000, new_text: "x".to_string() }];

    assert!(engine.apply_fix("load.rs", &edits, false).is_err(), "oob edit must error");
    assert_eq!(
        fs::read_to_string(dir.path().join("load.rs")).unwrap(),
        UNWRAP_SRC,
        "a failed apply must leave the file untouched"
    );
}

#[test]
fn overlapping_edits_error() {
    let (_dir, engine) = workspace("load.rs", UNWRAP_SRC);
    let edits = vec![
        Edit { start_byte: 0, end_byte: 5, new_text: "a".to_string() },
        Edit { start_byte: 3, end_byte: 8, new_text: "b".to_string() },
    ];
    assert!(engine.apply_fix("load.rs", &edits, true).is_err(), "overlapping edits must error");
}
