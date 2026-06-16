//! Edit Classifier (ADR-002).
//!
//! Given the OLD definitions of a file (read from the DB before re-upsert) and
//! the NEW definitions (freshly parsed), decide what the user just did:
//!
//! - **Rename** — a definition's name changed but its `signature_hash` did not.
//!   Propagation is *mechanical*: replace the old identifier at every call site.
//!   Zero model tokens.
//! - **SignatureChange** — the `signature_hash` changed (params/return-type).
//!   Propagation is *semantic*: each call site needs the model.
//!
//! The match between OLD and NEW is structural — by `(parent path, kind,
//! sibling ordinal)` — because the name is exactly what may have changed.

use std::collections::HashMap;

use serde::Serialize;

use super::extract::SymbolDef;
use super::store::StoredDef;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum EditKind {
    Rename,
    SignatureChange,
}

/// A classified change to one definition.
#[derive(Debug, Clone)]
pub struct Classification {
    pub kind: EditKind,
    pub old_name: String,
    pub new_name: String,
}

/// A single mechanical text replacement: overwrite `[start_byte, end_byte)` in
/// `file` with `new_text`.
#[derive(Debug, Clone, Serialize)]
pub struct Replacement {
    pub file: String,
    pub start_byte: usize,
    pub end_byte: usize,
    pub new_text: String,
}

/// A jump target the editor renders as a "Tab to jump" indicator.
#[derive(Debug, Clone, Serialize)]
pub struct EditSite {
    pub file: String,
    pub start_row: usize,
    pub start_byte: usize,
    pub end_byte: usize,
}

/// One suggested propagation surfaced to the editor.
#[derive(Debug, Clone, Serialize)]
pub struct EditSuggestion {
    pub kind: EditKind,
    pub old_name: String,
    pub new_name: String,
    /// True when the edits can be applied verbatim with no model call.
    pub mechanical: bool,
    /// Ready-to-apply replacements (populated for mechanical renames).
    pub edits: Vec<Replacement>,
    /// Where to jump; for semantic changes these are the sites the model must
    /// revisit (no `edits` provided).
    pub sites: Vec<EditSite>,
}

/// Structural key that survives a leaf rename: parent path (no file, no leaf) +
/// kind + ordinal among same-parent same-kind siblings.
fn parent_path_from_qualified(qualified_name: &str) -> String {
    // "file::a::b::leaf" -> "a::b"
    let mut parts: Vec<&str> = qualified_name.split("::").collect();
    if !parts.is_empty() {
        parts.remove(0); // drop file
    }
    if !parts.is_empty() {
        parts.pop(); // drop leaf
    }
    parts.join("::")
}

fn parent_path_from_new(defs: &[SymbolDef], idx: usize) -> String {
    let mut chain = Vec::new();
    let mut cur = defs[idx].parent;
    let mut guard = 0;
    while let Some(p) = cur {
        chain.push(defs[p].name.as_str());
        cur = defs[p].parent;
        guard += 1;
        if guard > defs.len() {
            break;
        }
    }
    chain.reverse();
    chain.join("::")
}

/// Assign a stable structural key to each entry. `keys` are returned parallel to
/// the input order. Ordinal is computed within `(parent_path, kind)` buckets,
/// ordered by `start_byte`.
fn structural_keys<F>(len: usize, parent_path: F, kind: impl Fn(usize) -> String, start_byte: impl Fn(usize) -> usize) -> Vec<String>
where
    F: Fn(usize) -> String,
{
    // Order indices by start_byte to assign deterministic ordinals.
    let mut order: Vec<usize> = (0..len).collect();
    order.sort_by_key(|&i| start_byte(i));

    let mut counts: HashMap<String, usize> = HashMap::new();
    let mut keys = vec![String::new(); len];
    for &i in &order {
        let bucket = format!("{}|{}", parent_path(i), kind(i));
        let ord = counts.entry(bucket.clone()).or_insert(0);
        keys[i] = format!("{bucket}|{ord}");
        *ord += 1;
    }
    keys
}

/// Diff OLD vs NEW and classify each changed definition.
pub fn classify(old: &[StoredDef], new: &[SymbolDef]) -> Vec<Classification> {
    let old_keys = structural_keys(
        old.len(),
        |i| parent_path_from_qualified(&old[i].qualified_name),
        |i| old[i].kind.clone(),
        |i| old[i].start_byte,
    );
    let new_keys = structural_keys(
        new.len(),
        |i| parent_path_from_new(new, i),
        |i| new[i].kind.clone(),
        |i| new[i].start_byte,
    );

    let new_by_key: HashMap<&str, usize> =
        new_keys.iter().enumerate().map(|(i, k)| (k.as_str(), i)).collect();

    let mut out = Vec::new();
    for (oi, okey) in old_keys.iter().enumerate() {
        let Some(&ni) = new_by_key.get(okey.as_str()) else {
            continue; // removed or restructured — no propagation in v1
        };
        let o = &old[oi];
        let n = &new[ni];

        if o.name != n.name {
            // Name changed. Same signature => mechanical rename; otherwise the
            // body/params also changed, so treat as semantic.
            let kind = if o.signature_hash == n.signature_hash {
                EditKind::Rename
            } else {
                EditKind::SignatureChange
            };
            out.push(Classification { kind, old_name: o.name.clone(), new_name: n.name.clone() });
        } else if o.signature_hash != n.signature_hash {
            out.push(Classification {
                kind: EditKind::SignatureChange,
                old_name: o.name.clone(),
                new_name: n.name.clone(),
            });
        }
    }
    out
}
