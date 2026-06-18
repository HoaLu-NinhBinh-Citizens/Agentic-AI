//! Tree-sitter extraction: source bytes -> symbol definitions + call refs.
//!
//! Pure and side-effect-free so it can run on the rayon pool over many files
//! and be unit-tested without a database.

use anyhow::{Context, Result};
use streaming_iterator::StreamingIterator;
use tree_sitter::{Parser, Query, QueryCursor};

use super::lang::Lang;

/// A symbol definition (function, struct, class, ...).
#[derive(Debug, Clone)]
pub struct SymbolDef {
    pub name: String,
    pub kind: String,
    pub start_byte: usize,
    pub end_byte: usize,
    /// 0-based line of the definition start (editor jumps here).
    pub start_row: usize,
    /// Exact identifier span of the name token within the definition — lets a
    /// mechanical rename rewrite the definition site itself (ADR-002).
    pub name_start_byte: usize,
    pub name_end_byte: usize,
    /// First line of the definition, trimmed — a cheap human-facing signature.
    pub signature: String,
    /// blake3 of the normalized signature (name token replaced by a placeholder,
    /// whitespace collapsed). A rename leaves this UNCHANGED; a param/return
    /// change FLIPS it — the mechanical-vs-semantic decision (ADR-002).
    pub signature_hash: String,
    /// Index into the returned `Vec<SymbolDef>` of the enclosing definition,
    /// or `None` at top level. Lets the store build `File::Class::method` keys
    /// without name collisions.
    pub parent: Option<usize>,
}

/// A call-site reference: `name` is the callee identifier; the byte span is the
/// exact range to overwrite on a mechanical rename.
#[derive(Debug, Clone)]
pub struct SymbolRef {
    pub name: String,
    pub start_byte: usize,
    pub end_byte: usize,
    pub start_row: usize,
}

/// Extract definitions and references from `source` for `lang`.
pub fn extract(lang: Lang, source: &[u8]) -> Result<(Vec<SymbolDef>, Vec<SymbolRef>)> {
    let language = lang.ts_language();
    let mut parser = Parser::new();
    parser
        .set_language(&language)
        .context("setting tree-sitter language")?;
    let tree = parser
        .parse(source, None)
        .context("tree-sitter parse returned None")?;
    let root = tree.root_node();

    let mut defs = collect_defs(lang, &language, root, source)?;
    compute_parents(&mut defs);
    let refs = collect_refs(lang, &language, root, source)?;
    Ok((defs, refs))
}

/// Compute the human-facing signature (first line, trimmed) and its normalized
/// hash. Normalization removes the name token (so renames don't change the hash)
/// and collapses whitespace. `name_*` are absolute byte offsets into `source`.
fn signature_and_hash(
    source: &[u8],
    def_start: usize,
    def_end: usize,
    name_start: usize,
    name_end: usize,
) -> (String, String) {
    let def_end = def_end.min(source.len());
    let rel_newline = source[def_start..def_end]
        .iter()
        .position(|&b| b == b'\n')
        .map(|p| def_start + p)
        .unwrap_or(def_end);
    let line_end = rel_newline;

    let signature = String::from_utf8_lossy(&source[def_start..line_end])
        .trim()
        .to_string();

    // Build the name-stripped signature only when the name token sits on the
    // first line (it does for every kind we extract). Otherwise fall back to
    // the raw signature so we never panic on odd ranges.
    let normalized = if name_start >= def_start && name_end <= line_end && name_start <= name_end {
        let mut buf = Vec::with_capacity(line_end - def_start);
        buf.extend_from_slice(&source[def_start..name_start]);
        buf.extend_from_slice("§".as_bytes()); // placeholder for the removed name
        buf.extend_from_slice(&source[name_end..line_end]);
        String::from_utf8_lossy(&buf).split_whitespace().collect::<Vec<_>>().join(" ")
    } else {
        signature.split_whitespace().collect::<Vec<_>>().join(" ")
    };

    let hash = blake3::hash(normalized.as_bytes()).to_hex().to_string();
    (signature, hash)
}

fn collect_defs(
    lang: Lang,
    language: &tree_sitter::Language,
    root: tree_sitter::Node,
    source: &[u8],
) -> Result<Vec<SymbolDef>> {
    let query = Query::new(language, lang.defs_query()).context("compiling defs query")?;
    let names = query.capture_names();
    let mut cursor = QueryCursor::new();
    let mut defs = Vec::new();

    let mut it = cursor.matches(&query, root, source);
    while let Some(m) = it.next() {
        let mut name: Option<tree_sitter::Node> = None;
        let mut kind: Option<&str> = None;
        let mut def_node: Option<tree_sitter::Node> = None;

        for cap in m.captures {
            let cap_name = names[cap.index as usize];
            if cap_name == "name" {
                name = Some(cap.node);
            } else if let Some(k) = cap_name.strip_prefix("def.") {
                kind = Some(k);
                def_node = Some(cap.node);
            }
        }

        if let (Some(name), Some(kind), Some(def)) = (name, kind, def_node) {
            let name_text = name.utf8_text(source).unwrap_or("").to_string();
            if name_text.is_empty() {
                continue;
            }
            let (signature, signature_hash) = signature_and_hash(
                source,
                def.start_byte(),
                def.end_byte(),
                name.start_byte(),
                name.end_byte(),
            );
            defs.push(SymbolDef {
                name: name_text,
                kind: kind.to_string(),
                start_byte: def.start_byte(),
                end_byte: def.end_byte(),
                start_row: def.start_position().row,
                name_start_byte: name.start_byte(),
                name_end_byte: name.end_byte(),
                signature,
                signature_hash,
                parent: None,
            });
        }
    }
    Ok(defs)
}

fn collect_refs(
    lang: Lang,
    language: &tree_sitter::Language,
    root: tree_sitter::Node,
    source: &[u8],
) -> Result<Vec<SymbolRef>> {
    let query = Query::new(language, lang.refs_query()).context("compiling refs query")?;
    let names = query.capture_names();
    let mut cursor = QueryCursor::new();
    let mut refs = Vec::new();

    let mut it = cursor.matches(&query, root, source);
    while let Some(m) = it.next() {
        for cap in m.captures {
            if names[cap.index as usize] == "ref.call" {
                let name = cap.node.utf8_text(source).unwrap_or("").to_string();
                if name.is_empty() {
                    continue;
                }
                refs.push(SymbolRef {
                    name,
                    start_byte: cap.node.start_byte(),
                    end_byte: cap.node.end_byte(),
                    start_row: cap.node.start_position().row,
                });
            }
        }
    }
    // De-dup by start byte: broad C/C++ queries can capture the same span via
    // multiple patterns (e.g. a call's callee is also a bare identifier).
    refs.sort_by_key(|r| r.start_byte);
    refs.dedup_by_key(|r| r.start_byte);
    Ok(refs)
}

/// Assign each definition its innermost enclosing definition via byte-range
/// containment. Sorting outer-before-inner lets a simple stack do it in O(n).
fn compute_parents(defs: &mut [SymbolDef]) {
    // Sort by start ascending, then end descending so an enclosing def always
    // precedes the defs it contains.
    let mut order: Vec<usize> = (0..defs.len()).collect();
    order.sort_by(|&a, &b| {
        defs[a]
            .start_byte
            .cmp(&defs[b].start_byte)
            .then(defs[b].end_byte.cmp(&defs[a].end_byte))
    });

    // Stack of indices (into `defs`) of currently-open enclosing definitions.
    let mut stack: Vec<usize> = Vec::new();
    let mut parent_of = vec![None; defs.len()];
    for &idx in &order {
        let start = defs[idx].start_byte;
        while let Some(&top) = stack.last() {
            if defs[top].end_byte <= start {
                stack.pop();
            } else {
                break;
            }
        }
        parent_of[idx] = stack.last().copied();
        stack.push(idx);
    }
    for (i, p) in parent_of.into_iter().enumerate() {
        defs[i].parent = p;
    }
}
