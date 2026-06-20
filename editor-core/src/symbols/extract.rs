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
    /// Index into the file's `Vec<SymbolDef>` of the innermost definition whose
    /// byte range encloses this ref (the *caller*), or `None` at top level.
    /// Turns a flat ref list into call edges: callee `name` is used *inside*
    /// this definition. Resolved to a row id at store time.
    pub enclosing: Option<usize>,
}

/// An `import` brought into a file's scope: Rust `use`, Python
/// `import`/`from`, or C/C++ `#include`. Drives cross-file symbol resolution
/// (does this file import `name`, and from which module?) and the file-level
/// dependency graph.
#[derive(Debug, Clone)]
pub struct Import {
    /// Module path the name comes from, e.g. `crate::detector` or `numpy`.
    /// Empty when not expressible (a bare `use Foo;` or a C header).
    pub module_path: String,
    /// The name bound into scope (the leaf, or its `as` alias). `"*"` for a
    /// glob/wildcard import (`use a::*`, `from a import *`).
    pub name: String,
    pub is_glob: bool,
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
    let mut refs = collect_refs(lang, &language, root, source)?;
    // Attribute each ref to its enclosing definition (the caller), so the flat
    // ref list becomes call edges once stored.
    for r in &mut refs {
        r.enclosing = enclosing_def(&defs, r.start_byte);
    }
    Ok((defs, refs))
}

/// Index of the innermost definition whose `[start_byte, end_byte)` contains
/// `byte`. Innermost = the containing def with the largest start offset.
fn enclosing_def(defs: &[SymbolDef], byte: usize) -> Option<usize> {
    let mut best: Option<usize> = None;
    for (i, d) in defs.iter().enumerate() {
        if d.start_byte <= byte && byte < d.end_byte {
            match best {
                Some(b) if defs[b].start_byte >= d.start_byte => {}
                _ => best = Some(i),
            }
        }
    }
    best
}

/// Extract the imports a file brings into scope (`use` / `import` / `#include`).
/// Heuristic string-parsing of the import path text — robust to the common
/// shapes (groups, aliases, globs) without a full module-path resolver, which
/// the cross-file resolver layers on top.
pub fn extract_imports(lang: Lang, source: &[u8]) -> Result<Vec<Import>> {
    let language = lang.ts_language();
    let mut parser = Parser::new();
    parser.set_language(&language).context("setting tree-sitter language")?;
    let tree = parser.parse(source, None).context("tree-sitter parse returned None")?;

    let query = Query::new(&language, lang.imports_query()).context("compiling imports query")?;
    let names = query.capture_names();
    let mut cursor = QueryCursor::new();
    let mut out = Vec::new();

    let mut it = cursor.matches(&query, tree.root_node(), source);
    while let Some(m) = it.next() {
        for cap in m.captures {
            let text = cap.node.utf8_text(source).unwrap_or("");
            let row = cap.node.start_position().row;
            match names[cap.index as usize] {
                "use.arg" => parse_rust_use(text, row, &mut out),
                "py.import" => parse_python_import(text, row, &mut out),
                "c.include" => {
                    // `"foo.h"` or `<foo.h>` -> stem `foo` as the module name.
                    let path = text.trim_matches(['"', '<', '>'].as_ref());
                    let stem = path.rsplit('/').next().unwrap_or(path);
                    let stem = stem.rsplit_once('.').map(|(s, _)| s).unwrap_or(stem);
                    out.push(Import {
                        module_path: path.to_string(),
                        name: stem.to_string(),
                        is_glob: false,
                        start_row: row,
                    });
                }
                _ => {}
            }
        }
    }
    Ok(out)
}

/// Split a `use` group body (`A, B::{C, D}`) on top-level commas only, so a
/// nested group isn't split on its inner commas.
fn split_top(s: &str) -> Vec<&str> {
    let mut out = Vec::new();
    let (mut depth, mut start) = (0i32, 0usize);
    for (i, ch) in s.char_indices() {
        match ch {
            '{' => depth += 1,
            '}' => depth -= 1,
            ',' if depth == 0 => {
                out.push(&s[start..i]);
                start = i + 1;
            }
            _ => {}
        }
    }
    out.push(&s[start..]);
    out
}

/// Parse a Rust `use` argument (the text after `use`, before `;`) into imports.
fn parse_rust_use(arg: &str, row: usize, out: &mut Vec<Import>) {
    let arg = arg.trim().trim_end_matches(';').trim();
    if let Some(open) = arg.find('{') {
        let close = arg.rfind('}').unwrap_or(arg.len());
        let prefix = arg[..open].trim().trim_end_matches("::").trim();
        let inner = arg.get(open + 1..close).unwrap_or("");
        for raw in split_top(inner) {
            let part = raw.trim();
            if !part.is_empty() {
                push_use_leaf(prefix, part, row, out);
            }
        }
    } else {
        push_use_leaf("", arg, row, out);
    }
}

/// Resolve one leaf of a `use` (after group expansion) to an [`Import`].
fn push_use_leaf(prefix: &str, part: &str, row: usize, out: &mut Vec<Import>) {
    // `use a::b::{self}` re-imports `b` itself.
    if part == "self" {
        let name = prefix.rsplit("::").next().unwrap_or(prefix).to_string();
        let module_path = prefix.rsplit_once("::").map(|(m, _)| m).unwrap_or("").to_string();
        out.push(Import { module_path, name, is_glob: false, start_row: row });
        return;
    }
    if part.ends_with('*') {
        let mp = if prefix.is_empty() {
            part.trim_end_matches('*').trim_end_matches("::").to_string()
        } else {
            prefix.to_string()
        };
        out.push(Import { module_path: mp, name: "*".into(), is_glob: true, start_row: row });
        return;
    }
    let (path, alias) = match part.split_once(" as ") {
        Some((p, a)) => (p.trim(), Some(a.trim())),
        None => (part, None),
    };
    let full = match (prefix.is_empty(), path.is_empty()) {
        (true, _) => path.to_string(),
        (false, true) => prefix.to_string(),
        (false, false) => format!("{prefix}::{path}"),
    };
    let leaf = full.rsplit("::").next().unwrap_or(&full).to_string();
    let module_path = full.rsplit_once("::").map(|(m, _)| m).unwrap_or("").to_string();
    let name = alias.map(str::to_string).unwrap_or(leaf);
    out.push(Import { module_path, name, is_glob: false, start_row: row });
}

/// Parse a Python `import` / `from ... import ...` statement into imports.
fn parse_python_import(text: &str, row: usize, out: &mut Vec<Import>) {
    let t = text.trim();
    if let Some(rest) = t.strip_prefix("from ") {
        if let Some((module, names)) = rest.split_once(" import ") {
            let module = module.trim();
            for raw in names.split(',') {
                let part = raw.trim().trim_matches(['(', ')'].as_ref()).trim();
                if part.is_empty() {
                    continue;
                }
                if part == "*" {
                    out.push(Import {
                        module_path: module.to_string(),
                        name: "*".into(),
                        is_glob: true,
                        start_row: row,
                    });
                    continue;
                }
                let (n, alias) = match part.split_once(" as ") {
                    Some((n, a)) => (n.trim(), Some(a.trim())),
                    None => (part, None),
                };
                out.push(Import {
                    module_path: module.to_string(),
                    name: alias.unwrap_or(n).to_string(),
                    is_glob: false,
                    start_row: row,
                });
            }
        }
    } else if let Some(rest) = t.strip_prefix("import ") {
        for raw in rest.split(',') {
            let part = raw.trim();
            if part.is_empty() {
                continue;
            }
            let (module, alias) = match part.split_once(" as ") {
                Some((m, a)) => (m.trim(), Some(a.trim())),
                None => (part, None),
            };
            // `import a.b.c` binds `a`; `import a.b.c as x` binds `x`.
            let name = alias
                .map(str::to_string)
                .unwrap_or_else(|| module.split('.').next().unwrap_or(module).to_string());
            out.push(Import {
                module_path: module.to_string(),
                name,
                is_glob: false,
                start_row: row,
            });
        }
    }
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
                    enclosing: None,
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
