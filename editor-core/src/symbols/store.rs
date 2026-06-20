//! SQLite (WAL) store for the symbol graph — v1 schema.
//!
//! v1 normalizes files into a `files` table (integer `file_id` on symbols/refs)
//! and adds the columns ADR-002 needs: `signature_hash`, exact name spans on
//! definitions, and `end_byte` on refs. Since v0 carries no production data we
//! drop/create cleanly rather than running an in-place migration.
//!
//! WAL mode lets completion/Next-Edit reads run concurrently with a sync write.
//! All mutation is per-file and transactional.

use std::path::Path;

use anyhow::{Context, Result};
use rusqlite::{params, Connection, OptionalExtension};
use serde::Serialize;

use super::extract::{Import, SymbolDef, SymbolRef};

/// Bumped whenever the schema changes. A mismatch triggers a clean rebuild.
/// v2 adds the semantic layer: `imports`, `refs.enclosing_symbol_id` (call
/// edges), and `files.crate_root` (cross-file resolution scope).
const SCHEMA_VERSION: i64 = 2;

pub struct SymbolStore {
    conn: Connection,
}

/// A definition row returned to callers (e.g. "go to definition").
#[derive(Debug, Serialize)]
pub struct SymbolRow {
    pub file: String,
    pub name: String,
    pub kind: String,
    pub qualified_name: String,
    pub start_row: usize,
    pub signature: String,
}

/// A stored definition, read back for edit classification (OLD state, captured
/// before a file is re-upserted).
#[derive(Debug, Clone)]
pub struct StoredDef {
    pub name: String,
    pub kind: String,
    pub qualified_name: String,
    pub signature_hash: String,
    pub start_byte: usize,
}

/// A call-site row — the unit Next Edit Prediction iterates over.
#[derive(Debug, Serialize)]
pub struct RefRow {
    pub file: String,
    pub name: String,
    pub start_byte: usize,
    pub end_byte: usize,
    pub start_row: usize,
}

/// A full definition record for the resolver / semantic engine: identity plus
/// the byte span (to read its source) and the resolution-scope columns
/// (`file`, `crate_root`).
#[derive(Debug, Clone, Serialize)]
pub struct DefRecord {
    pub id: i64,
    pub file: String,
    pub name: String,
    pub kind: String,
    pub qualified_name: String,
    pub signature: String,
    pub start_byte: usize,
    pub end_byte: usize,
    pub start_row: usize,
    /// Workspace-relative crate root dir (nearest `Cargo.toml` ancestor), or
    /// empty when the file isn't inside a crate.
    pub crate_root: String,
}

/// One import row brought into a file's scope.
#[derive(Debug, Clone, Serialize)]
pub struct ImportRow {
    pub module_path: String,
    pub name: String,
    pub is_glob: bool,
    pub start_row: usize,
}

/// A distinct callee name referenced inside one definition (a call edge's
/// target name, pre-resolution).
#[derive(Debug, Clone)]
pub struct RefName {
    pub name: String,
    pub start_row: usize,
}

impl SymbolStore {
    pub fn open(db_path: &Path) -> Result<Self> {
        if let Some(parent) = db_path.parent() {
            std::fs::create_dir_all(parent).ok();
        }
        let conn = Connection::open(db_path).context("opening symbols.db")?;
        conn.pragma_update(None, "journal_mode", "WAL")?;
        conn.pragma_update(None, "synchronous", "NORMAL")?;
        conn.pragma_update(None, "foreign_keys", "ON")?;

        let store = Self { conn };
        store.ensure_schema()?;
        Ok(store)
    }

    /// Create the schema, dropping any older version first (no prod data yet).
    fn ensure_schema(&self) -> Result<()> {
        let version: i64 = self
            .conn
            .query_row("PRAGMA user_version", [], |r| r.get(0))
            .unwrap_or(0);

        if version != SCHEMA_VERSION {
            self.conn.execute_batch(
                "DROP TABLE IF EXISTS imports;
                 DROP TABLE IF EXISTS refs;
                 DROP TABLE IF EXISTS symbols;
                 DROP TABLE IF EXISTS files;",
            )?;
        }

        self.conn.execute_batch(
            r#"
            CREATE TABLE IF NOT EXISTS files (
                id           INTEGER PRIMARY KEY,
                path         TEXT NOT NULL UNIQUE,
                lang         TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                indexed_at   INTEGER NOT NULL,
                crate_root   TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS symbols (
                id              INTEGER PRIMARY KEY,
                file_id         INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
                name            TEXT NOT NULL,
                kind            TEXT NOT NULL,
                parent_id       INTEGER REFERENCES symbols(id) ON DELETE CASCADE,
                qualified_name  TEXT NOT NULL,
                start_byte      INTEGER NOT NULL,
                end_byte        INTEGER NOT NULL,
                start_row       INTEGER NOT NULL,
                name_start_byte INTEGER NOT NULL,
                name_end_byte   INTEGER NOT NULL,
                signature       TEXT NOT NULL,
                signature_hash  TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_symbols_name  ON symbols(name);
            CREATE INDEX IF NOT EXISTS idx_symbols_file  ON symbols(file_id);
            CREATE INDEX IF NOT EXISTS idx_symbols_qname ON symbols(qualified_name);

            CREATE TABLE IF NOT EXISTS refs (
                id                  INTEGER PRIMARY KEY,
                file_id             INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
                name                TEXT NOT NULL,
                start_byte          INTEGER NOT NULL,
                end_byte            INTEGER NOT NULL,
                start_row           INTEGER NOT NULL,
                enclosing_symbol_id INTEGER REFERENCES symbols(id) ON DELETE SET NULL
            );
            CREATE INDEX IF NOT EXISTS idx_refs_name ON refs(name);
            CREATE INDEX IF NOT EXISTS idx_refs_file ON refs(file_id);
            CREATE INDEX IF NOT EXISTS idx_refs_enclosing ON refs(enclosing_symbol_id);

            CREATE TABLE IF NOT EXISTS imports (
                id          INTEGER PRIMARY KEY,
                file_id     INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
                module_path TEXT NOT NULL,
                name        TEXT NOT NULL,
                is_glob     INTEGER NOT NULL,
                start_row   INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_imports_file ON imports(file_id);
            CREATE INDEX IF NOT EXISTS idx_imports_name ON imports(name);
            "#,
        )?;

        self.conn
            .pragma_update(None, "user_version", SCHEMA_VERSION)?;
        Ok(())
    }

    /// Resolve (insert or update) the files row for `path`, returning its id.
    fn upsert_file_row(
        tx: &rusqlite::Transaction,
        path: &str,
        lang: &str,
        content_hash: &str,
        indexed_at: i64,
        crate_root: &str,
    ) -> Result<i64> {
        tx.execute(
            "INSERT INTO files (path, lang, content_hash, indexed_at, crate_root)
             VALUES (?1, ?2, ?3, ?4, ?5)
             ON CONFLICT(path) DO UPDATE SET
                 lang = excluded.lang,
                 content_hash = excluded.content_hash,
                 indexed_at = excluded.indexed_at,
                 crate_root = excluded.crate_root",
            params![path, lang, content_hash, indexed_at, crate_root],
        )?;
        let id: i64 = tx.query_row(
            "SELECT id FROM files WHERE path = ?1",
            params![path],
            |r| r.get(0),
        )?;
        Ok(id)
    }

    /// Replace all symbols/refs for `file` in one transaction.
    #[allow(clippy::too_many_arguments)]
    pub fn upsert_file(
        &mut self,
        file: &str,
        lang: &str,
        content_hash: &str,
        indexed_at: i64,
        crate_root: &str,
        defs: &[SymbolDef],
        refs: &[SymbolRef],
        imports: &[Import],
    ) -> Result<()> {
        let qnames = qualified_names(file, defs);
        let tx = self.conn.transaction()?;
        let file_id =
            Self::upsert_file_row(&tx, file, lang, content_hash, indexed_at, crate_root)?;

        // Clear prior rows for this file before reinserting (delete by file_id).
        tx.execute("DELETE FROM imports WHERE file_id = ?1", params![file_id])?;
        tx.execute("DELETE FROM refs WHERE file_id = ?1", params![file_id])?;
        tx.execute("DELETE FROM symbols WHERE file_id = ?1", params![file_id])?;

        // Two passes: insert with NULL parent_id collecting row ids, then patch
        // parent_id now that every def has an id.
        let mut ids = vec![0i64; defs.len()];
        for (i, d) in defs.iter().enumerate() {
            tx.execute(
                "INSERT INTO symbols
                   (file_id, name, kind, parent_id, qualified_name,
                    start_byte, end_byte, start_row,
                    name_start_byte, name_end_byte, signature, signature_hash)
                 VALUES (?1, ?2, ?3, NULL, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11)",
                params![
                    file_id,
                    d.name,
                    d.kind,
                    qnames[i],
                    d.start_byte as i64,
                    d.end_byte as i64,
                    d.start_row as i64,
                    d.name_start_byte as i64,
                    d.name_end_byte as i64,
                    d.signature,
                    d.signature_hash,
                ],
            )?;
            ids[i] = tx.last_insert_rowid();
        }
        for (i, d) in defs.iter().enumerate() {
            if let Some(p) = d.parent {
                tx.execute(
                    "UPDATE symbols SET parent_id = ?1 WHERE id = ?2",
                    params![ids[p], ids[i]],
                )?;
            }
        }

        for r in refs {
            // Map the in-file enclosing-def index to its freshly inserted row id
            // (the call edge's source symbol), NULL at top level.
            let enclosing_id = r.enclosing.map(|idx| ids[idx]);
            tx.execute(
                "INSERT INTO refs (file_id, name, start_byte, end_byte, start_row, enclosing_symbol_id)
                 VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
                params![
                    file_id,
                    r.name,
                    r.start_byte as i64,
                    r.end_byte as i64,
                    r.start_row as i64,
                    enclosing_id,
                ],
            )?;
        }

        for im in imports {
            tx.execute(
                "INSERT INTO imports (file_id, module_path, name, is_glob, start_row)
                 VALUES (?1, ?2, ?3, ?4, ?5)",
                params![file_id, im.module_path, im.name, im.is_glob as i64, im.start_row as i64],
            )?;
        }

        tx.commit()?;
        Ok(())
    }

    /// Drop a deleted file from the graph (cascade removes its symbols/refs).
    pub fn delete_file(&mut self, file: &str) -> Result<()> {
        self.conn
            .execute("DELETE FROM files WHERE path = ?1", params![file])?;
        Ok(())
    }

    /// Definitions matching `name` (exact). Drives "go to definition".
    pub fn find_symbol(&self, name: &str) -> Result<Vec<SymbolRow>> {
        let mut stmt = self.conn.prepare(
            "SELECT f.path, s.name, s.kind, s.qualified_name, s.start_row, s.signature
             FROM symbols s JOIN files f ON f.id = s.file_id
             WHERE s.name = ?1 ORDER BY f.path, s.start_row",
        )?;
        let rows = stmt
            .query_map(params![name], |r| {
                Ok(SymbolRow {
                    file: r.get(0)?,
                    name: r.get(1)?,
                    kind: r.get(2)?,
                    qualified_name: r.get(3)?,
                    start_row: r.get::<_, i64>(4)? as usize,
                    signature: r.get(5)?,
                })
            })?
            .collect::<rusqlite::Result<Vec<_>>>()?;
        Ok(rows)
    }

    /// All definitions of one file, ordered by position. Captured as the OLD
    /// state right before a re-upsert so the classifier can diff it against the
    /// freshly parsed defs.
    pub fn symbols_of_file(&self, file: &str) -> Result<Vec<StoredDef>> {
        let mut stmt = self.conn.prepare(
            "SELECT s.name, s.kind, s.qualified_name, s.signature_hash, s.start_byte
             FROM symbols s JOIN files f ON f.id = s.file_id
             WHERE f.path = ?1 ORDER BY s.start_byte",
        )?;
        let rows = stmt
            .query_map(params![file], |r| {
                Ok(StoredDef {
                    name: r.get(0)?,
                    kind: r.get(1)?,
                    qualified_name: r.get(2)?,
                    signature_hash: r.get(3)?,
                    start_byte: r.get::<_, i64>(4)? as usize,
                })
            })?
            .collect::<rusqlite::Result<Vec<_>>>()?;
        Ok(rows)
    }

    /// Call sites of `name` — the cheap SQL that powers Next Edit Prediction.
    pub fn call_sites(&self, name: &str) -> Result<Vec<RefRow>> {
        let mut stmt = self.conn.prepare(
            "SELECT f.path, r.name, r.start_byte, r.end_byte, r.start_row
             FROM refs r JOIN files f ON f.id = r.file_id
             WHERE r.name = ?1 ORDER BY f.path, r.start_row",
        )?;
        let rows = stmt
            .query_map(params![name], |r| {
                Ok(RefRow {
                    file: r.get(0)?,
                    name: r.get(1)?,
                    start_byte: r.get::<_, i64>(2)? as usize,
                    end_byte: r.get::<_, i64>(3)? as usize,
                    start_row: r.get::<_, i64>(4)? as usize,
                })
            })?
            .collect::<rusqlite::Result<Vec<_>>>()?;
        Ok(rows)
    }

    /// The `signature_hash` of a definition by qualified name, if present.
    /// The edit classifier compares this across a sync to tell rename from
    /// signature change.
    pub fn signature_hash_of(&self, qualified_name: &str) -> Result<Option<String>> {
        let hash = self
            .conn
            .query_row(
                "SELECT signature_hash FROM symbols WHERE qualified_name = ?1 LIMIT 1",
                params![qualified_name],
                |r| r.get(0),
            )
            .optional()?;
        Ok(hash)
    }

    /// How many definitions across the whole graph carry `name`. Next Edit
    /// Prediction uses this to tell a globally-unique rename (safe to apply at
    /// every call site) from an ambiguous one: if a definition of `old_name`
    /// still exists in another module, name-only call-site matching would
    /// over-match, so the rename must not auto-apply (SYMBOL_GRAPH_SPEC.md §5).
    pub fn def_count(&self, name: &str) -> Result<usize> {
        let n: i64 = self.conn.query_row(
            "SELECT COUNT(*) FROM symbols WHERE name = ?1",
            params![name],
            |r| r.get(0),
        )?;
        Ok(n as usize)
    }

    /// Total symbol count — used in status.
    pub fn symbol_count(&self) -> Result<usize> {
        let n: i64 = self
            .conn
            .query_row("SELECT COUNT(*) FROM symbols", [], |r| r.get(0))?;
        Ok(n as usize)
    }

    // ---- semantic layer: resolution + call graph ---------------------------

    /// Shared SELECT for [`DefRecord`] rows so every accessor maps the same
    /// columns in the same order.
    const DEF_SELECT: &'static str = "SELECT s.id, f.path, s.name, s.kind, s.qualified_name, \
         s.signature, s.start_byte, s.end_byte, s.start_row, f.crate_root \
         FROM symbols s JOIN files f ON f.id = s.file_id";

    fn map_def(r: &rusqlite::Row) -> rusqlite::Result<DefRecord> {
        Ok(DefRecord {
            id: r.get(0)?,
            file: r.get(1)?,
            name: r.get(2)?,
            kind: r.get(3)?,
            qualified_name: r.get(4)?,
            signature: r.get(5)?,
            start_byte: r.get::<_, i64>(6)? as usize,
            end_byte: r.get::<_, i64>(7)? as usize,
            start_row: r.get::<_, i64>(8)? as usize,
            crate_root: r.get(9)?,
        })
    }

    /// Every definition named `name` across the workspace — the candidate set the
    /// resolver ranks.
    pub fn resolve_candidates(&self, name: &str) -> Result<Vec<DefRecord>> {
        let sql = format!("{} WHERE s.name = ?1 ORDER BY f.path, s.start_byte", Self::DEF_SELECT);
        let mut stmt = self.conn.prepare(&sql)?;
        let rows = stmt
            .query_map(params![name], Self::map_def)?
            .collect::<rusqlite::Result<Vec<_>>>()?;
        Ok(rows)
    }

    /// A definition by its exact qualified name (`file::Mod::name`).
    pub fn def_by_qname(&self, qname: &str) -> Result<Option<DefRecord>> {
        let sql = format!("{} WHERE s.qualified_name = ?1 LIMIT 1", Self::DEF_SELECT);
        let def = self
            .conn
            .query_row(&sql, params![qname], Self::map_def)
            .optional()?;
        Ok(def)
    }

    /// The innermost definition in `file` whose byte range contains `byte` —
    /// "what symbol is the cursor in?".
    pub fn def_at(&self, file: &str, byte: usize) -> Result<Option<DefRecord>> {
        let sql = format!(
            "{} WHERE f.path = ?1 AND s.start_byte <= ?2 AND s.end_byte > ?2 \
             ORDER BY s.start_byte DESC LIMIT 1",
            Self::DEF_SELECT
        );
        let def = self
            .conn
            .query_row(&sql, params![file, byte as i64], Self::map_def)
            .optional()?;
        Ok(def)
    }

    /// Distinct callee names referenced inside the definition `symbol_id` — the
    /// outgoing call edges of one symbol, pre-resolution.
    pub fn refs_in_symbol(&self, symbol_id: i64) -> Result<Vec<RefName>> {
        let mut stmt = self.conn.prepare(
            "SELECT name, MIN(start_row) FROM refs
             WHERE enclosing_symbol_id = ?1 GROUP BY name ORDER BY MIN(start_row)",
        )?;
        let rows = stmt
            .query_map(params![symbol_id], |r| {
                Ok(RefName { name: r.get(0)?, start_row: r.get::<_, i64>(1)? as usize })
            })?
            .collect::<rusqlite::Result<Vec<_>>>()?;
        Ok(rows)
    }

    /// Imports a file brings into scope.
    pub fn imports_of_file(&self, file: &str) -> Result<Vec<ImportRow>> {
        let mut stmt = self.conn.prepare(
            "SELECT i.module_path, i.name, i.is_glob, i.start_row
             FROM imports i JOIN files f ON f.id = i.file_id
             WHERE f.path = ?1 ORDER BY i.start_row",
        )?;
        let rows = stmt
            .query_map(params![file], |r| {
                Ok(ImportRow {
                    module_path: r.get(0)?,
                    name: r.get(1)?,
                    is_glob: r.get::<_, i64>(2)? != 0,
                    start_row: r.get::<_, i64>(3)? as usize,
                })
            })?
            .collect::<rusqlite::Result<Vec<_>>>()?;
        Ok(rows)
    }

    /// The crate root recorded for `file` (empty string if none, `None` if the
    /// file isn't indexed).
    pub fn crate_root_of(&self, file: &str) -> Result<Option<String>> {
        let root = self
            .conn
            .query_row("SELECT crate_root FROM files WHERE path = ?1", params![file], |r| r.get(0))
            .optional()?;
        Ok(root)
    }
}

/// Build `file::A::B::name` qualified names by walking the parent chain.
fn qualified_names(file: &str, defs: &[SymbolDef]) -> Vec<String> {
    let mut out = Vec::with_capacity(defs.len());
    for (i, _) in defs.iter().enumerate() {
        let mut chain = Vec::new();
        let mut cur = Some(i);
        let mut guard = 0;
        while let Some(idx) = cur {
            chain.push(defs[idx].name.as_str());
            cur = defs[idx].parent;
            guard += 1;
            if guard > defs.len() {
                break; // cycle guard
            }
        }
        chain.reverse();
        out.push(format!("{file}::{}", chain.join("::")));
    }
    out
}
