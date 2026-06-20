//! Detector framework: AST rules that flag bugs with a fix suggestion.
//!
//! A `Detector` is a single rule. It receives a parsed [`FileContext`] and
//! returns [`Finding`]s — each with a severity, a precise `file:line:col`, a
//! short explanation, and (where the fix is mechanical) `before`/`after`
//! snippets the editor can render as a one-click patch.
//!
//! Rules are registered in a [`DetectorRegistry`]. New rules implement the
//! trait and are added to `with_defaults` (or injected at runtime via
//! `register`) — nothing else changes. Rules can be toggled off by id, which is
//! the hook a future `config.toml` (ADR: detector config) wires into.

pub mod rules;

use std::collections::HashSet;

use anyhow::{Context as _, Result};
use serde::{Deserialize, Serialize};
use tree_sitter::{Language, Node, Parser, Query, QueryCursor, Tree};

use crate::symbols::lang::Lang;

/// How urgent a finding is. Ordered so `Critical` sorts first (lowest rank).
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Severity {
    Critical,
    High,
    Medium,
    Low,
}

impl Severity {
    pub fn as_str(self) -> &'static str {
        match self {
            Severity::Critical => "critical",
            Severity::High => "high",
            Severity::Medium => "medium",
            Severity::Low => "low",
        }
    }
}

/// One problem found in one place, with an optional mechanical fix.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Finding {
    /// Stable rule id, e.g. `"rust/unwrap"`. The editor groups + filters on this.
    pub rule_id: String,
    pub severity: Severity,
    pub file: String,
    /// 1-based line and column (editors are 1-based; tree-sitter is 0-based).
    pub line: usize,
    pub column: usize,
    /// One-sentence, human-facing explanation of *why* this is a problem.
    pub message: String,
    /// The offending source line, verbatim. `None` if not applicable.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub before: Option<String>,
    /// A suggested replacement / guidance. `None` when the fix isn't mechanical.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub after: Option<String>,
}

/// A parsed file handed to every detector. Owns its source + tree so detectors
/// borrow, never re-parse.
pub struct FileContext {
    pub path: String,
    pub lang: Lang,
    pub language: Language,
    pub source: Vec<u8>,
    pub tree: Tree,
}

impl FileContext {
    /// Parse `source` for `lang`. Errors only if the grammar can't be set;
    /// tree-sitter always returns *a* tree (with ERROR nodes) for bad input.
    pub fn parse(path: &str, lang: Lang, source: Vec<u8>) -> Result<Self> {
        let language = lang.ts_language();
        let mut parser = Parser::new();
        parser
            .set_language(&language)
            .context("setting tree-sitter language")?;
        let tree = parser
            .parse(&source, None)
            .context("tree-sitter parse returned None")?;
        Ok(Self { path: path.to_string(), lang, language, source, tree })
    }

    /// The verbatim source line containing `byte` (trimmed), for `before`.
    pub fn line_text(&self, byte: usize) -> String {
        let s = &self.source;
        let byte = byte.min(s.len());
        let start = s[..byte].iter().rposition(|&b| b == b'\n').map(|p| p + 1).unwrap_or(0);
        let end = s[byte..].iter().position(|&b| b == b'\n').map(|p| byte + p).unwrap_or(s.len());
        String::from_utf8_lossy(&s[start..end]).trim().to_string()
    }

    /// Run a tree-sitter query and call `f` once per match with a small helper
    /// to pull captured nodes by name. Compiles the query each call (queries are
    /// tiny); a malformed query is logged and skipped rather than panicking.
    pub fn for_each_match(&self, query_src: &str, mut f: impl FnMut(&MatchView)) {
        let query = match Query::new(&self.language, query_src) {
            Ok(q) => q,
            Err(e) => {
                tracing::debug!(error = %e, "detector query failed to compile; skipping");
                return;
            }
        };
        let names = query.capture_names();
        let mut cursor = QueryCursor::new();
        let mut it = cursor.matches(&query, self.tree.root_node(), self.source.as_slice());
        use streaming_iterator::StreamingIterator;
        while let Some(m) = it.next() {
            let view = MatchView { m, names, source: &self.source };
            f(&view);
        }
    }
}

/// A thin view over one query match: fetch a captured node (and its text) by
/// capture name without juggling indices in every rule.
pub struct MatchView<'a, 'tree> {
    m: &'a tree_sitter::QueryMatch<'a, 'tree>,
    names: &'a [&'a str],
    source: &'a [u8],
}

impl<'a, 'tree> MatchView<'a, 'tree> {
    pub fn node(&self, capture: &str) -> Option<Node<'tree>> {
        self.m
            .captures
            .iter()
            .find(|c| self.names[c.index as usize] == capture)
            .map(|c| c.node)
    }

    pub fn text(&self, capture: &str) -> Option<&'a str> {
        self.node(capture).and_then(|n| n.utf8_text(self.source).ok())
    }
}

/// A single bug-finding rule.
pub trait Detector: Send + Sync {
    /// Stable id (also the `Finding.rule_id` prefix), e.g. `"rust/unwrap"`.
    fn id(&self) -> &'static str;
    /// One-line description for `--list-detectors` / config UIs.
    fn description(&self) -> &'static str;
    /// Default severity (a finding may still override per-occurrence).
    fn severity(&self) -> Severity;
    /// Languages this rule applies to. Empty findings for others.
    fn applies_to(&self, lang: Lang) -> bool;
    /// Inspect the file and return any findings.
    fn check(&self, ctx: &FileContext) -> Vec<Finding>;
}

/// Holds the active detectors. `with_defaults` registers the built-ins; ids in
/// `disabled` are skipped (the config-file toggle hook).
pub struct DetectorRegistry {
    detectors: Vec<Box<dyn Detector>>,
    disabled: HashSet<String>,
}

impl DetectorRegistry {
    pub fn with_defaults() -> Self {
        Self {
            detectors: vec![
                Box::new(rules::UnwrapDetector),
                Box::new(rules::UnsafeBlockDetector),
                Box::new(rules::HardcodedConfigDetector),
            ],
            disabled: HashSet::new(),
        }
    }

    /// Start empty (tests / fully custom setups).
    pub fn empty() -> Self {
        Self { detectors: Vec::new(), disabled: HashSet::new() }
    }

    pub fn register(&mut self, d: Box<dyn Detector>) {
        self.detectors.push(d);
    }

    /// Turn a rule off by id (e.g. from `config.toml`). No-op if unknown.
    pub fn disable(&mut self, id: &str) {
        self.disabled.insert(id.to_string());
    }

    pub fn ids(&self) -> Vec<&'static str> {
        self.detectors.iter().map(|d| d.id()).collect()
    }

    /// Run every enabled, applicable detector over one parsed file. Findings are
    /// sorted Critical-first, then by line, then by rule id — stable output.
    pub fn run(&self, ctx: &FileContext) -> Vec<Finding> {
        let mut findings: Vec<Finding> = self
            .detectors
            .iter()
            .filter(|d| !self.disabled.contains(d.id()) && d.applies_to(ctx.lang))
            .flat_map(|d| d.check(ctx))
            .collect();
        findings.sort_by(|a, b| {
            a.severity
                .cmp(&b.severity)
                .then(a.line.cmp(&b.line))
                .then(a.rule_id.cmp(&b.rule_id))
        });
        findings
    }

    /// Convenience: detect language from path, parse, and run. Files in an
    /// unsupported language return `Ok(vec![])` (not an error).
    pub fn analyze(&self, path: &str, source: Vec<u8>) -> Result<Vec<Finding>> {
        let Some(lang) = Lang::from_path(path) else {
            return Ok(Vec::new());
        };
        let ctx = FileContext::parse(path, lang, source)?;
        Ok(self.run(&ctx))
    }
}

impl Default for DetectorRegistry {
    fn default() -> Self {
        Self::with_defaults()
    }
}

/// Helper for rules: build a `Finding` from a node, filling line/column from the
/// node's start position (converted to 1-based) and `before` from its line.
pub(crate) fn finding_at(
    ctx: &FileContext,
    node: Node,
    rule_id: &str,
    severity: Severity,
    message: impl Into<String>,
    after: Option<String>,
) -> Finding {
    let pos = node.start_position();
    Finding {
        rule_id: rule_id.to_string(),
        severity,
        file: ctx.path.clone(),
        line: pos.row + 1,
        column: pos.column + 1,
        message: message.into(),
        before: Some(ctx.line_text(node.start_byte())),
        after,
    }
}
