//! Built-in detectors. Each is a small, single-responsibility rule that maps a
//! tree-sitter pattern to a [`Finding`] with a fix suggestion.

use super::{finding_at, Detector, FileContext, Finding, Severity};
use crate::symbols::lang::Lang;

/// `rust/unwrap` — flags `.unwrap()` / `.expect()` on `Result`/`Option`.
///
/// A panic on the unhappy path takes down the whole process. In an agent/daemon
/// that means one missing file (a model checkpoint, a config) kills every
/// session. The fix is to propagate with `?` or attach context.
pub struct UnwrapDetector;

impl Detector for UnwrapDetector {
    fn id(&self) -> &'static str {
        "rust/unwrap"
    }
    fn description(&self) -> &'static str {
        "Panic-prone .unwrap()/.expect(); propagate the error with `?` instead"
    }
    fn severity(&self) -> Severity {
        Severity::High
    }
    fn applies_to(&self, lang: Lang) -> bool {
        lang == Lang::Rust
    }

    fn check(&self, ctx: &FileContext) -> Vec<Finding> {
        // Method-call form: `<expr>.unwrap()` / `<expr>.expect(...)`.
        let query = r#"
            (call_expression
              function: (field_expression
                field: (field_identifier) @method)) @call
        "#;
        let mut out = Vec::new();
        ctx.for_each_match(query, |m| {
            let Some(method) = m.text("method") else { return };
            if method != "unwrap" && method != "expect" {
                return;
            }
            let Some(node) = m.node("method") else { return };
            let line = ctx.line_text(node.start_byte());
            // Suggested fix: turn the unwrap into error propagation.
            let after = if method == "unwrap" {
                Some(line.replace(".unwrap()", "?"))
            } else {
                // .expect("msg") -> .with_context(|| "msg")? keeps the message.
                Some(format!("{line}  // replace `.expect(..)` with `.with_context(|| ..)?`"))
            };
            out.push(finding_at(
                ctx,
                node,
                self.id(),
                self.severity(),
                format!(
                    "`.{method}()` panics on the error/none case; propagate with `?` so a \
                     missing file or bad input can't crash the process"
                ),
                after,
            ));
        });
        out
    }
}

/// `rust/unsafe-block` — surfaces every `unsafe { .. }` block for review.
///
/// `unsafe` opts out of the compiler's guarantees (aliasing, lifetimes, FFI
/// memory). It's sometimes necessary, but each block should carry a `// SAFETY:`
/// note proving the invariants. We flag blocks lacking one.
pub struct UnsafeBlockDetector;

impl Detector for UnsafeBlockDetector {
    fn id(&self) -> &'static str {
        "rust/unsafe-block"
    }
    fn description(&self) -> &'static str {
        "`unsafe` block without a `// SAFETY:` justification"
    }
    fn severity(&self) -> Severity {
        Severity::Medium
    }
    fn applies_to(&self, lang: Lang) -> bool {
        lang == Lang::Rust
    }

    fn check(&self, ctx: &FileContext) -> Vec<Finding> {
        let query = r#"(unsafe_block) @b"#;
        let mut out = Vec::new();
        ctx.for_each_match(query, |m| {
            let Some(node) = m.node("b") else { return };
            // Look just above the block for a SAFETY comment; if present, the
            // author already justified it — don't nag.
            if has_safety_comment(ctx, node.start_byte()) {
                return;
            }
            out.push(finding_at(
                ctx,
                node,
                self.id(),
                self.severity(),
                "`unsafe` block has no `// SAFETY:` comment documenting the invariants \
                 it upholds (aliasing, lifetimes, FFI memory ownership)",
                Some("// SAFETY: <state why this is sound> then keep the unsafe block".to_string()),
            ));
        });
        out
    }
}

/// True if the line(s) immediately preceding `byte` contain a `SAFETY:` comment.
fn has_safety_comment(ctx: &FileContext, byte: usize) -> bool {
    let s = &ctx.source;
    let byte = byte.min(s.len());
    // Take up to ~200 bytes before the block and look for the marker on a
    // comment line — cheap and good enough; avoids a second parse.
    let start = byte.saturating_sub(200);
    let window = String::from_utf8_lossy(&s[start..byte]);
    window
        .lines()
        .rev()
        .take(3)
        .any(|l| l.trim_start().starts_with("//") && l.to_ascii_uppercase().contains("SAFETY"))
}

/// `ml/hardcoded-hyperparam` — flags ML hyper-parameters hardcoded as literals.
///
/// `learning_rate`, `batch_size`, `epochs`, `seed`, … baked into code (rather
/// than read from a `config.toml`/`serde` struct) make experiments
/// irreproducible and force a recompile to tune. Applies to Rust and Python.
pub struct HardcodedConfigDetector;

/// Identifier names we treat as hyper-parameters / config knobs.
const CONFIG_NAMES: &[&str] = &[
    "learning_rate",
    "lr",
    "batch_size",
    "epochs",
    "n_epochs",
    "num_epochs",
    "seed",
    "momentum",
    "weight_decay",
    "dropout",
    "hidden_size",
];

impl Detector for HardcodedConfigDetector {
    fn id(&self) -> &'static str {
        "ml/hardcoded-hyperparam"
    }
    fn description(&self) -> &'static str {
        "Hardcoded ML hyper-parameter literal; load it from config instead"
    }
    fn severity(&self) -> Severity {
        Severity::Medium
    }
    fn applies_to(&self, lang: Lang) -> bool {
        matches!(lang, Lang::Rust | Lang::Python)
    }

    fn check(&self, ctx: &FileContext) -> Vec<Finding> {
        let query = match ctx.lang {
            Lang::Rust => {
                r#"
                (let_declaration pattern: (identifier) @name value: (integer_literal) @val)
                (let_declaration pattern: (identifier) @name value: (float_literal) @val)
                "#
            }
            Lang::Python => {
                r#"
                (assignment left: (identifier) @name right: (integer) @val)
                (assignment left: (identifier) @name right: (float) @val)
                "#
            }
            _ => return Vec::new(),
        };
        let mut out = Vec::new();
        ctx.for_each_match(query, |m| {
            let Some(name) = m.text("name") else { return };
            if !CONFIG_NAMES.contains(&name) {
                return;
            }
            let Some(name_node) = m.node("name") else { return };
            let val = m.text("val").unwrap_or("<literal>");
            out.push(finding_at(
                ctx,
                name_node,
                self.id(),
                self.severity(),
                format!(
                    "hyper-parameter `{name} = {val}` is hardcoded; load it from a config \
                     file (serde + config.toml) so runs are reproducible and tunable without \
                     a recompile"
                ),
                Some(format!("{name} = config.{name}  // read from a typed config struct")),
            ));
        });
        out
    }
}
