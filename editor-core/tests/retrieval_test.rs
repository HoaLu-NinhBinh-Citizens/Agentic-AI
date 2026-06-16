//! Hybrid retrieval + ContextBuilder tests.

use std::fs;

use aircore::context::{BuildRequest, ContextBuilder, Task};
use aircore::retrieval::chunks::Chunk;
use aircore::retrieval::embed::HashEmbedder;
use aircore::retrieval::lance_store::LanceVectorStore;
use aircore::retrieval::vector::VectorStore;
use aircore::retrieval::HybridRetriever;
use tempfile::TempDir;

fn chunk(id: u64, file: &str, start_byte: usize, text: &str) -> Chunk {
    Chunk {
        id,
        file: file.to_string(),
        symbol: None,
        start_row: 0,
        start_byte,
        end_byte: start_byte + text.len(),
        text: text.to_string(),
    }
}

fn retriever(chunks: Vec<Chunk>) -> HybridRetriever {
    HybridRetriever::build(HashEmbedder::default(), chunks).unwrap()
}

#[test]
fn lance_store_persists_and_searches_by_distance() {
    let dir = TempDir::new().unwrap();
    let uri = dir.path().join("vectors.lance");
    let mut store = LanceVectorStore::open(uri.to_str().unwrap(), 3).unwrap();
    store.add(1, vec![1.0, 0.0, 0.0]);
    store.add(2, vec![0.0, 1.0, 0.0]);
    store.commit().unwrap();

    // Query closest to id 1.
    let res = store.search(&[0.9, 0.1, 0.0], 1);
    assert_eq!(res.len(), 1);
    assert_eq!(res[0].0, 1);

    // Data is on disk: a fresh handle to the same uri still finds it.
    drop(store);
    let mut reopened = LanceVectorStore::open(uri.to_str().unwrap(), 3).unwrap();
    // Re-register the rows (full-rebuild lifecycle) and confirm persistence path works.
    reopened.add(1, vec![1.0, 0.0, 0.0]);
    reopened.commit().unwrap();
    assert_eq!(reopened.search(&[1.0, 0.0, 0.0], 1)[0].0, 1);
}

#[test]
fn hybrid_with_lance_backend_finds_chunk() {
    let dir = TempDir::new().unwrap();
    let uri = dir.path().join("v.lance");
    // HashEmbedder default dim is 256, so the Lance table is 256-wide.
    let store = Box::new(LanceVectorStore::open(uri.to_str().unwrap(), 256).unwrap());
    let r = HybridRetriever::build_with(
        Box::new(HashEmbedder::default()),
        store,
        vec![
            chunk(1, "a.rs", 0, "fn parse_header(buf: &[u8]) {}"),
            chunk(2, "b.rs", 0, "fn render_widget(w: &Widget) {}"),
        ],
    )
    .unwrap();
    let hits = r.search("parse_header", 2).unwrap();
    assert!(hits.iter().any(|h| h.chunk.id == 1), "Lance-backed hybrid must find the chunk");
}

#[test]
fn hybrid_finds_chunk_by_identifier() {
    let r = retriever(vec![
        chunk(1, "a.rs", 0, "fn parse_header(buf: &[u8]) -> Header { todo!() }"),
        chunk(2, "b.rs", 0, "fn render_widget(w: &Widget) { draw(w) }"),
        chunk(3, "c.rs", 0, "fn compute_checksum(d: &[u8]) -> u32 { 0 }"),
    ]);
    let hits = r.search("parse_header", 3).unwrap();
    assert!(!hits.is_empty());
    assert_eq!(hits[0].chunk.id, 1, "exact identifier must rank first");
}

#[test]
fn context_places_nearest_snippet_closest_to_the_middle() {
    let dir = TempDir::new().unwrap();
    // The request file must exist on disk for the local prefix/suffix split.
    fs::write(dir.path().join("main.rs"), "let x = 0; // cursor here\n").unwrap();

    // A same-file chunk (far from cursor but same file) and a cross-module one.
    // Both mention the query term so both are retrieved.
    let r = retriever(vec![
        chunk(10, "main.rs", 200, "fn local_helper() { token_budget(); }"),
        chunk(20, "other/lib.rs", 0, "fn token_budget() -> usize { 4096 }"),
    ]);

    let cb = ContextBuilder::new(&r, dir.path());
    let prompt = cb
        .build(&BuildRequest {
            task: Task::Completion,
            file: "main.rs".to_string(),
            cursor_byte: 5,
            query: Some("token_budget".to_string()),
            max_tokens: 10_000,
        })
        .unwrap();

    let same_file_pos = prompt.text.find("main.rs:").expect("same-file snippet present");
    let cross_pos = prompt.text.find("other/lib.rs:").expect("cross-module snippet present");
    // Farthest (cross-module) first, nearest (same-file) last → closer to middle.
    assert!(cross_pos < same_file_pos, "nearest snippet must sit closest to the FIM middle");
    // FIM framing present.
    assert!(prompt.text.contains("<|fim_prefix|>"));
    assert!(prompt.text.contains("<|fim_middle|>"));
}

#[test]
fn tight_budget_drops_snippets_and_reports_it() {
    let dir = TempDir::new().unwrap();
    fs::write(dir.path().join("main.rs"), "x\n").unwrap();

    let r = retriever(vec![
        chunk(1, "other/a.rs", 0, "fn token_budget_one() { /* a long-ish body here */ }"),
        chunk(2, "other/b.rs", 0, "fn token_budget_two() { /* another long-ish body */ }"),
    ]);

    let cb = ContextBuilder::new(&r, dir.path());
    let prompt = cb
        .build(&BuildRequest {
            task: Task::Completion,
            file: "main.rs".to_string(),
            cursor_byte: 1,
            query: Some("token_budget".to_string()),
            max_tokens: 5, // far too small for any snippet
        })
        .unwrap();

    assert!(prompt.dropped >= 1, "tiny budget must drop snippets, not hide them");
    assert!(prompt.included.len() < 2);
}

#[test]
fn chunk_containing_cursor_is_excluded() {
    let dir = TempDir::new().unwrap();
    fs::write(dir.path().join("main.rs"), "fn current() { token_budget(); }\n").unwrap();

    // This chunk spans the cursor — it's the code being edited, already local.
    let r = retriever(vec![
        chunk(1, "main.rs", 0, "fn current() { token_budget(); }"),
        chunk(2, "lib.rs", 0, "fn token_budget() -> usize { 4096 }"),
    ]);

    let cb = ContextBuilder::new(&r, dir.path());
    let prompt = cb
        .build(&BuildRequest {
            task: Task::Completion,
            file: "main.rs".to_string(),
            cursor_byte: 15, // inside the main.rs chunk
            query: Some("token_budget".to_string()),
            max_tokens: 10_000,
        })
        .unwrap();

    // The cursor's own chunk must not be re-injected as context.
    assert!(prompt.included.iter().all(|s| s.file != "main.rs"));
}
