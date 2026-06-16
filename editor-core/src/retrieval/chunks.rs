//! Symbol-aware chunking: one chunk per definition (its byte span), with a
//! whole-file fallback when a file has no extracted symbols. Chunking on symbol
//! boundaries keeps a function/class intact instead of splitting mid-body.

use crate::symbols::extract::SymbolDef;

#[derive(Debug, Clone)]
pub struct Chunk {
    pub id: u64,
    pub file: String,
    pub symbol: Option<String>,
    pub start_row: usize,
    pub start_byte: usize,
    pub end_byte: usize,
    pub text: String,
}

fn fnv1a(bytes: &[u8]) -> u64 {
    let mut h: u64 = 0xcbf29ce484222325;
    for &b in bytes {
        h ^= b as u64;
        h = h.wrapping_mul(0x100000001b3);
    }
    h
}

/// Stable id from file + byte offset so re-chunking the same definition yields
/// the same id.
fn chunk_id(file: &str, start_byte: usize) -> u64 {
    fnv1a(format!("{file}:{start_byte}").as_bytes())
}

/// Build chunks for one file. `defs` come from the symbol graph; `source` is the
/// file's bytes. Falls back to a single whole-file chunk if there are no defs.
pub fn chunk_file(file: &str, source: &[u8], defs: &[SymbolDef]) -> Vec<Chunk> {
    if defs.is_empty() {
        let text = String::from_utf8_lossy(source).to_string();
        if text.trim().is_empty() {
            return Vec::new();
        }
        return vec![Chunk {
            id: chunk_id(file, 0),
            file: file.to_string(),
            symbol: None,
            start_row: 0,
            start_byte: 0,
            end_byte: source.len(),
            text,
        }];
    }

    defs.iter()
        .filter_map(|d| {
            let end = d.end_byte.min(source.len());
            if d.start_byte >= end {
                return None;
            }
            let text = String::from_utf8_lossy(&source[d.start_byte..end]).to_string();
            Some(Chunk {
                id: chunk_id(file, d.start_byte),
                file: file.to_string(),
                symbol: Some(d.name.clone()),
                start_row: d.start_row,
                start_byte: d.start_byte,
                end_byte: end,
                text,
            })
        })
        .collect()
}
