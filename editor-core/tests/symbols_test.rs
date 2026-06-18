//! Symbol graph tests: extraction, nesting, call-site lookup (the query that
//! powers Next Edit Prediction), and delta-driven updates.

use std::fs;

use aircore::index::IndexEngine;
use aircore::symbols::extract::extract;
use aircore::symbols::lang::Lang;
use tempfile::TempDir;

fn write(dir: &TempDir, rel: &str, contents: &str) {
    let path = dir.path().join(rel);
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).unwrap();
    }
    fs::write(path, contents).unwrap();
}

#[test]
fn extracts_rust_defs_and_calls() {
    let src = br#"
fn helper() {}
fn main() {
    helper();
    helper();
}
"#;
    let (defs, refs) = extract(Lang::Rust, src).unwrap();
    let names: Vec<_> = defs.iter().map(|d| d.name.as_str()).collect();
    assert!(names.contains(&"helper"));
    assert!(names.contains(&"main"));
    // helper is called twice.
    let calls = refs.iter().filter(|r| r.name == "helper").count();
    assert_eq!(calls, 2);
}

#[test]
fn signature_hash_distinguishes_rename_from_signature_change() {
    // Baseline.
    let (base, _) = extract(Lang::Rust, b"fn area(w: i32, h: i32) -> i32 { w * h }").unwrap();
    let base = &base[0];

    // Pure rename: name differs, params/return identical -> SAME hash.
    let (renamed, _) =
        extract(Lang::Rust, b"fn surface(w: i32, h: i32) -> i32 { w * h }").unwrap();
    assert_eq!(
        base.signature_hash, renamed[0].signature_hash,
        "rename must not change signature_hash (mechanical edit)"
    );

    // Added a parameter: signature changed -> DIFFERENT hash.
    let (param, _) =
        extract(Lang::Rust, b"fn area(w: i32, h: i32, d: i32) -> i32 { w * h }").unwrap();
    assert_ne!(
        base.signature_hash, param[0].signature_hash,
        "param change must flip signature_hash (semantic edit)"
    );
}

#[test]
fn name_span_points_at_the_identifier() {
    let src = b"fn helper() {}";
    let (defs, _) = extract(Lang::Rust, src).unwrap();
    let d = &defs[0];
    // The recorded name span must slice out exactly the identifier.
    assert_eq!(&src[d.name_start_byte..d.name_end_byte], b"helper");
}

#[test]
fn ref_span_points_at_the_call_identifier() {
    let src = b"fn main() { helper(); }";
    let (_, refs) = extract(Lang::Rust, src).unwrap();
    let r = refs.iter().find(|r| r.name == "helper").unwrap();
    assert_eq!(&src[r.start_byte..r.end_byte], b"helper");
}

#[test]
fn extracts_c_functions_and_calls() {
    let src = b"int helper(int x) { return x; }\nint main(void) {\n    helper(1);\n    helper(2);\n    return 0;\n}\n";
    let (defs, refs) = extract(Lang::C, src).unwrap();
    let names: Vec<_> = defs.iter().map(|d| d.name.as_str()).collect();
    assert!(names.contains(&"helper"), "got {names:?}");
    assert!(names.contains(&"main"), "got {names:?}");
    assert_eq!(refs.iter().filter(|r| r.name == "helper").count(), 2);
}

#[test]
fn extracts_c_struct_and_typedef() {
    let src = b"struct Point { int x; int y; };\ntypedef struct Point PointT;\n";
    let (defs, _) = extract(Lang::C, src).unwrap();
    let kinds: Vec<_> = defs.iter().map(|d| (d.name.as_str(), d.kind.as_str())).collect();
    assert!(kinds.contains(&("Point", "struct")), "got {kinds:?}");
    assert!(kinds.contains(&("PointT", "typedef")), "got {kinds:?}");
}

#[test]
fn computes_python_method_nesting() {
    let src = br#"
class Foo:
    def bar(self):
        pass
"#;
    let (defs, _refs) = extract(Lang::Python, src).unwrap();
    let class_idx = defs.iter().position(|d| d.name == "Foo").unwrap();
    let bar = defs.iter().find(|d| d.name == "bar").unwrap();
    // bar's parent is the Foo class -> avoids name collisions across classes.
    assert_eq!(bar.parent, Some(class_idx));
    assert_eq!(bar.kind, "function");
}

#[test]
fn call_sites_query_finds_references_across_files() {
    let dir = TempDir::new().unwrap();
    write(&dir, "lib.rs", "pub fn target() {}\n");
    write(
        &dir,
        "main.rs",
        "fn main() {\n    target();\n    target();\n}\n",
    );

    let mut engine = IndexEngine::open(dir.path()).unwrap();
    let result = engine.sync().unwrap();
    assert!(result.symbols.symbols >= 2);

    // Definition lookup.
    let defs = engine.find_symbol("target").unwrap();
    assert_eq!(defs.len(), 1);
    assert_eq!(defs[0].file, "lib.rs");

    // Call-site lookup — the Next Edit Prediction primitive.
    let sites = engine.call_sites("target").unwrap();
    assert_eq!(sites.len(), 2);
    assert!(sites.iter().all(|s| s.file == "main.rs"));
}

#[test]
fn deleting_a_file_drops_its_symbols() {
    let dir = TempDir::new().unwrap();
    write(&dir, "a.rs", "fn gone() {}\n");

    let mut engine = IndexEngine::open(dir.path()).unwrap();
    engine.sync().unwrap();
    assert_eq!(engine.find_symbol("gone").unwrap().len(), 1);

    fs::remove_file(dir.path().join("a.rs")).unwrap();
    engine.sync().unwrap();
    assert_eq!(engine.find_symbol("gone").unwrap().len(), 0);
}

#[test]
fn rename_produces_mechanical_edits_at_all_call_sites() {
    let dir = TempDir::new().unwrap();
    write(&dir, "lib.rs", "pub fn area(w: i32, h: i32) -> i32 { w * h }\n");
    write(
        &dir,
        "main.rs",
        "fn main() {\n    area(1, 2);\n    area(3, 4);\n}\n",
    );

    let mut engine = IndexEngine::open(dir.path()).unwrap();
    engine.sync().unwrap(); // initial index, no suggestions

    // User renames the definition area -> surface (signature unchanged).
    write(&dir, "lib.rs", "pub fn surface(w: i32, h: i32) -> i32 { w * h }\n");
    let result = engine.sync().unwrap();

    let rename = result
        .suggestions
        .iter()
        .find(|s| s.old_name == "area")
        .expect("expected a rename suggestion for area");

    assert!(rename.mechanical, "a pure rename must be mechanical");
    assert_eq!(rename.new_name, "surface");
    // Both call sites in main.rs still say `area` and must be rewritten.
    let main_edits: Vec<_> = rename.edits.iter().filter(|e| e.file == "main.rs").collect();
    assert_eq!(main_edits.len(), 2);
    assert!(main_edits.iter().all(|e| e.new_text == "surface"));
}

#[test]
fn signature_change_is_semantic_not_mechanical() {
    let dir = TempDir::new().unwrap();
    write(&dir, "lib.rs", "pub fn f(a: i32) -> i32 { a }\n");
    write(&dir, "main.rs", "fn main() {\n    f(1);\n}\n");

    let mut engine = IndexEngine::open(dir.path()).unwrap();
    engine.sync().unwrap();

    // Add a parameter: signature changed, name unchanged.
    write(&dir, "lib.rs", "pub fn f(a: i32, b: i32) -> i32 { a + b }\n");
    let result = engine.sync().unwrap();

    let sig = result
        .suggestions
        .iter()
        .find(|s| s.old_name == "f")
        .expect("expected a signature-change suggestion for f");
    assert!(!sig.mechanical, "a signature change needs the model");
    assert!(sig.edits.is_empty(), "no mechanical edits for semantic change");
    assert!(!sig.sites.is_empty(), "must still list sites to revisit");
}

#[test]
fn reindexing_a_file_replaces_not_duplicates() {
    let dir = TempDir::new().unwrap();
    write(&dir, "a.rs", "fn one() {}\n");

    let mut engine = IndexEngine::open(dir.path()).unwrap();
    engine.sync().unwrap();

    // Rename the symbol; the old one must disappear, not accumulate.
    write(&dir, "a.rs", "fn two() {}\n");
    engine.sync().unwrap();

    assert_eq!(engine.find_symbol("one").unwrap().len(), 0);
    assert_eq!(engine.find_symbol("two").unwrap().len(), 1);
}
