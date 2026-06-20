//! Tests for the semantic-first context provider (`IndexEngine::build_context`):
//! a coding request centered on a symbol pulls its resolved callees as context,
//! reports `mode = "semantic"`/`"hybrid"`, and degrades to retrieval-only when
//! no focus symbol resolves.

use std::fs;

use aircore::context::{BuildRequest, Task};
use aircore::index::IndexEngine;

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
fn chat_context_centers_on_symbol_and_pulls_callee() {
    let (_dir, mut engine) = synced_workspace(&[
        ("Cargo.toml", CARGO),
        ("src/math.rs", MATH),
        ("src/main.rs", MAIN),
    ]);

    let prompt = engine
        .build_context(&BuildRequest {
            task: Task::Chat,
            file: "src/main.rs".to_string(),
            cursor_byte: 0,
            query: Some("explain run".to_string()),
            max_tokens: 4000,
            focus_symbol: Some("src/main.rs::run".to_string()),
        })
        .unwrap();

    // Semantic core present: the focus and its resolved callee `add`.
    assert!(prompt.included.iter().any(|s| s.kind == "semantic.focus"));
    assert!(
        prompt.included.iter().any(|s| s.kind == "semantic.dep" && s.file == "src/math.rs"),
        "resolved callee should be included: {:?}",
        prompt.included
    );
    assert!(prompt.mode == "semantic" || prompt.mode == "hybrid", "mode = {}", prompt.mode);
    // The callee body (from another file) made it into the prompt text.
    assert!(prompt.text.contains("a + b"), "callee body in context: {}", prompt.text);
}

#[test]
fn completion_context_is_semantic_when_cursor_in_known_symbol() {
    let (_dir, mut engine) = synced_workspace(&[
        ("Cargo.toml", CARGO),
        ("src/math.rs", MATH),
        ("src/main.rs", MAIN),
    ]);

    // Cursor inside `run`, right after the `add(1, 2)` call.
    let byte = MAIN.find("add(1, 2)").unwrap() + 1;
    let prompt = engine
        .build_completion_context("src/main.rs", byte, 4000, None)
        .unwrap();

    // FIM framing preserved; semantic callee context present.
    assert!(prompt.text.contains("<|fim_prefix|>") && prompt.text.contains("<|fim_middle|>"));
    assert!(
        prompt.included.iter().any(|s| s.kind == "semantic.dep"),
        "cursor symbol's callee should lead: {:?} mode={}",
        prompt.included,
        prompt.mode
    );
}

#[test]
fn falls_back_to_retrieval_when_no_focus_symbol() {
    // A markdown file isn't in the symbol graph, so no focus resolves — the
    // provider must degrade to retrieval rather than error or return nothing.
    let (_dir, mut engine) = synced_workspace(&[
        ("Cargo.toml", CARGO),
        ("src/math.rs", MATH),
        ("notes.md", "# notes\nsome prose about add and arithmetic\n"),
    ]);

    let prompt = engine
        .build_context(&BuildRequest {
            task: Task::Chat,
            file: "notes.md".to_string(),
            cursor_byte: 0,
            query: Some("add".to_string()),
            max_tokens: 4000,
            focus_symbol: None,
        })
        .unwrap();

    assert_eq!(prompt.mode, "retrieval", "no resolvable symbol -> retrieval fallback");
    assert!(
        prompt.included.iter().all(|s| s.kind == "retrieved"),
        "fallback context is retrieval-only: {:?}",
        prompt.included
    );
}
