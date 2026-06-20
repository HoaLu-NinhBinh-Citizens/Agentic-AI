//! Semantic-engine integration tests: drive a real multi-file workspace through
//! a sync, then exercise cross-file resolution, the file dependency graph, and
//! minimal-context assembly via the public `IndexEngine` API.

use std::fs;

use aircore::index::IndexEngine;
use aircore::semantic::{Confidence, FocusSpec, Scope, SemanticRequest};

/// Build a workspace on disk, open + sync the engine over it.
fn synced_workspace(files: &[(&str, &str)]) -> (tempfile::TempDir, IndexEngine) {
    let dir = tempfile::tempdir().unwrap();
    for (path, src) in files {
        let abs = dir.path().join(path);
        fs::create_dir_all(abs.parent().unwrap()).unwrap();
        fs::write(abs, src).unwrap();
    }
    let mut engine = IndexEngine::open(dir.path()).unwrap();
    engine.sync().unwrap();
    (dir, engine)
}

const CARGO: &str = "[package]\nname = \"demo\"\nversion = \"0.1.0\"\n";
const MATH: &str = "pub fn add(a: i32, b: i32) -> i32 {\n    a + b\n}\n";
const MAIN: &str = "use crate::math::add;\n\nfn run() -> i32 {\n    add(1, 2)\n}\n";

#[test]
fn resolves_imported_call_across_files() {
    let (_dir, engine) = synced_workspace(&[
        ("Cargo.toml", CARGO),
        ("src/math.rs", MATH),
        ("src/main.rs", MAIN),
    ]);

    let r = engine.resolve_symbol("add", "src/main.rs").unwrap();
    assert_eq!(r.len(), 1, "exactly one `add` definition: {r:?}");
    let best = &r[0];
    assert_eq!(best.def.file, "src/math.rs");
    assert_eq!(best.def.qualified_name, "src/math.rs::add");
    assert_eq!(best.scope, Scope::SameModule, "same src/ dir: {best:?}");
    assert!(best.imported, "`add` is explicitly `use`d in main.rs");
    assert_eq!(best.confidence, Confidence::High, "sole candidate is high-confidence");
}

#[test]
fn ambiguous_name_drops_confidence() {
    // Two `helper` definitions in different modules -> resolution is ambiguous.
    let (_dir, engine) = synced_workspace(&[
        ("Cargo.toml", CARGO),
        ("a/one.rs", "pub fn helper() -> i32 { 1 }\n"),
        ("b/two.rs", "pub fn helper() -> i32 { 2 }\n"),
        ("b/use_it.rs", "fn go() -> i32 { helper() }\n"),
    ]);

    let r = engine.resolve_symbol("helper", "b/use_it.rs").unwrap();
    assert_eq!(r.len(), 2, "two candidates: {r:?}");
    // The same-module (b/) one ranks first.
    assert_eq!(r[0].def.file, "b/two.rs");
    assert_eq!(r[0].scope, Scope::SameModule);
    // Unique nearest -> still High for the winner, Low for the far one.
    assert_eq!(r[0].confidence, Confidence::High);
    assert_eq!(r[1].confidence, Confidence::Low);
}

#[test]
fn file_dependencies_resolve_imports_to_files() {
    let (_dir, engine) = synced_workspace(&[
        ("Cargo.toml", CARGO),
        ("src/math.rs", MATH),
        ("src/main.rs", MAIN),
    ]);

    let edges = engine.file_dependencies("src/main.rs").unwrap();
    let add_edge = edges.iter().find(|e| e.name == "add").expect("add import edge");
    assert_eq!(add_edge.module_path, "crate::math");
    assert_eq!(add_edge.resolved_file.as_deref(), Some("src/math.rs"));
    assert!(!add_edge.is_glob);
}

#[test]
fn semantic_context_pulls_focus_plus_resolved_callee() {
    let (_dir, engine) = synced_workspace(&[
        ("Cargo.toml", CARGO),
        ("src/math.rs", MATH),
        ("src/main.rs", MAIN),
    ]);

    let req = SemanticRequest {
        focus: FocusSpec::Symbol("src/main.rs::run".to_string()),
        max_tokens: 2000,
        include_bodies: true,
    };
    let ctx = engine.semantic_context(&req).unwrap();

    assert_eq!(ctx.focus.qualified_name, "src/main.rs::run");
    assert!(ctx.focus.source.contains("add(1, 2)"), "focus source: {:?}", ctx.focus.source);

    // The resolved callee `add` (defined in another file) is pulled in.
    let dep = ctx
        .dependencies
        .iter()
        .find(|d| d.qualified_name == "src/math.rs::add")
        .expect("add should be a resolved dependency");
    assert_eq!(dep.file, "src/math.rs");
    assert!(dep.signature.contains("fn add"));
    assert!(
        dep.source.as_deref().unwrap_or("").contains("a + b"),
        "callee body included when requested: {dep:?}"
    );
}

#[test]
fn semantic_context_by_cursor_location() {
    let (_dir, engine) = synced_workspace(&[
        ("Cargo.toml", CARGO),
        ("src/math.rs", MATH),
        ("src/main.rs", MAIN),
    ]);

    // A byte offset inside `run`'s body (on the `add(1, 2)` call).
    let byte = MAIN.find("add(1, 2)").unwrap() + 1;
    let req = SemanticRequest {
        focus: FocusSpec::Location { file: "src/main.rs".to_string(), byte },
        max_tokens: 2000,
        include_bodies: false,
    };
    let ctx = engine.semantic_context(&req).unwrap();
    assert_eq!(ctx.focus.qualified_name, "src/main.rs::run", "cursor resolves to enclosing fn");
    // Bodies not requested -> callee carries a signature but no source.
    assert!(ctx.dependencies.iter().all(|d| d.source.is_none()));
}
