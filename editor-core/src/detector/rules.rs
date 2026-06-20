//! Built-in detectors. Each is a small, single-responsibility rule that maps a
//! tree-sitter pattern to a [`Finding`] with a fix suggestion.

use super::{finding_at, Detector, FileContext, Finding, RuleOptions, Severity};
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

/// `ml/data-leakage` — flags a scaler/normalizer fit on the *whole* dataset
/// before the train/test split (linfa / smartcore / sklearn).
///
/// Calling `.fit(X)` / `.fit_transform(X)` on the full data lets test-set
/// statistics (mean, variance, min/max) bleed into preprocessing, inflating
/// reported metrics. The fit must happen on the train split only, then the
/// fitted transform is applied to the test split. We flag a fit whose argument
/// is *not* a recognizable train split (no `train` in the operand name).
pub struct DataLeakageDetector;

/// Fit-style methods that learn statistics from their argument.
const FIT_METHODS: &[&str] = &["fit", "fit_transform"];

/// Default substring that marks an operand as the train split. Overridable via
/// the `split_keyword` option (e.g. a project that names splits `learn_x`).
const DEFAULT_SPLIT_KEYWORD: &str = "train";

impl Detector for DataLeakageDetector {
    fn id(&self) -> &'static str {
        "ml/data-leakage"
    }
    fn description(&self) -> &'static str {
        "Scaler/normalizer fit on the full dataset before the train/test split"
    }
    fn severity(&self) -> Severity {
        Severity::High
    }
    fn applies_to(&self, lang: Lang) -> bool {
        matches!(lang, Lang::Rust | Lang::Python)
    }

    fn check(&self, ctx: &FileContext) -> Vec<Finding> {
        self.check_with(ctx, &RuleOptions::new())
    }

    fn check_with(&self, ctx: &FileContext, options: &RuleOptions) -> Vec<Finding> {
        // `split_keyword` lets a project override the train-split naming token.
        let split_keyword = options
            .get("split_keyword")
            .and_then(|v| v.as_str())
            .unwrap_or(DEFAULT_SPLIT_KEYWORD)
            .to_ascii_lowercase();
        let query = match ctx.lang {
            Lang::Rust => {
                r#"
                (call_expression
                  function: (field_expression field: (field_identifier) @method)
                  arguments: (arguments) @args) @call
                "#
            }
            Lang::Python => {
                r#"
                (call
                  function: (attribute attribute: (identifier) @method)
                  arguments: (argument_list) @args) @call
                "#
            }
            _ => return Vec::new(),
        };
        let mut out = Vec::new();
        ctx.for_each_match(query, |m| {
            let Some(method) = m.text("method") else { return };
            if !FIT_METHODS.contains(&method) {
                return;
            }
            // The operand(s) being fit. If they name a train split (`X_train`,
            // `train_x`, …) the fit is correctly scoped — don't flag.
            let args = m.text("args").unwrap_or("");
            if args.to_ascii_lowercase().contains(&split_keyword) {
                return;
            }
            let Some(node) = m.node("method") else { return };
            out.push(finding_at(
                ctx,
                node,
                self.id(),
                self.severity(),
                format!(
                    "`.{method}(..)` appears to fit preprocessing on the full dataset; \
                     fit on the train split only, then transform the test split — otherwise \
                     test statistics leak in and inflate your metrics"
                ),
                Some("scaler.fit(x_train); /* then */ scaler.transform(x_test)".to_string()),
            ));
        });
        out
    }
}

/// `ml/device-mismatch` — flags a tensor pinned to the CPU inside code that
/// otherwise targets a CUDA/GPU device (tch-rs / candle).
///
/// Mixing a CPU tensor with a model (or other tensors) on the GPU panics at
/// runtime (`expected device cuda, got cpu`). When a file clearly uses CUDA, an
/// explicit `Device::Cpu` / `"cpu"` placement is almost always a leftover that
/// should follow the model's device instead.
pub struct DeviceMismatchDetector;

impl Detector for DeviceMismatchDetector {
    fn id(&self) -> &'static str {
        "ml/device-mismatch"
    }
    fn description(&self) -> &'static str {
        "CPU tensor placement in CUDA/GPU code; place it on the model's device"
    }
    fn severity(&self) -> Severity {
        Severity::High
    }
    fn applies_to(&self, lang: Lang) -> bool {
        matches!(lang, Lang::Rust | Lang::Python)
    }

    fn check(&self, ctx: &FileContext) -> Vec<Finding> {
        // Only meaningful when the file actually targets a GPU; otherwise a CPU
        // device is intentional. Cheap source-level gate before the AST walk.
        let src = String::from_utf8_lossy(&ctx.source).to_ascii_lowercase();
        if !src.contains("cuda") && !src.contains("gpu") {
            return Vec::new();
        }
        let query = match ctx.lang {
            Lang::Rust => {
                r#"
                (call_expression
                  function: (field_expression field: (field_identifier) @method)
                  arguments: (arguments) @args) @call
                "#
            }
            Lang::Python => {
                r#"
                (call
                  function: (attribute attribute: (identifier) @method)
                  arguments: (argument_list) @args) @call
                "#
            }
            _ => return Vec::new(),
        };
        let mut out = Vec::new();
        ctx.for_each_match(query, |m| {
            let Some(method) = m.text("method") else { return };
            // Placement methods across tch-rs (`to_device`/`to`) and PyTorch (`to`/`cpu`).
            if method != "to" && method != "to_device" && method != "cpu" {
                return;
            }
            let args = m.text("args").unwrap_or("").to_ascii_lowercase();
            let places_on_cpu = method == "cpu" || args.contains("cpu");
            if !places_on_cpu {
                return;
            }
            let Some(node) = m.node("method") else { return };
            out.push(finding_at(
                ctx,
                node,
                self.id(),
                self.severity(),
                "tensor is placed on the CPU while this file targets a CUDA/GPU device; \
                 mixing devices panics at runtime — place it on the model's device instead",
                Some("tensor.to(model_device)  // follow the model's device, not a hardcoded Cpu".to_string()),
            ));
        });
        out
    }
}

/// `ml/no-grad-eval` — flags an eval/inference function that runs a forward
/// pass without disabling gradient tracking (tch / burn / candle / PyTorch).
///
/// Building the autograd graph during evaluation wastes memory and time, and on
/// large inputs can OOM. Inference should run under `no_grad` (tch
/// `tch::no_grad`, PyTorch `torch.no_grad()` / `inference_mode`, candle's
/// detached tensors). We flag eval-named functions that call `forward` but
/// never mention a no-grad guard.
pub struct NoGradEvalDetector;

/// Function-name fragments that mark an evaluation / inference entry point.
const EVAL_NAME_HINTS: &[&str] = &["eval", "valid", "infer", "predict"];

impl Detector for NoGradEvalDetector {
    fn id(&self) -> &'static str {
        "ml/no-grad-eval"
    }
    fn description(&self) -> &'static str {
        "Eval/inference forward pass without a no_grad guard"
    }
    fn severity(&self) -> Severity {
        Severity::Medium
    }
    fn applies_to(&self, lang: Lang) -> bool {
        matches!(lang, Lang::Rust | Lang::Python)
    }

    fn check(&self, ctx: &FileContext) -> Vec<Finding> {
        let query = match ctx.lang {
            Lang::Rust => r#"(function_item name: (identifier) @name body: (block) @body) @fn"#,
            Lang::Python => {
                r#"(function_definition name: (identifier) @name body: (block) @body) @fn"#
            }
            _ => return Vec::new(),
        };
        let mut out = Vec::new();
        ctx.for_each_match(query, |m| {
            let Some(name) = m.text("name") else { return };
            let lname = name.to_ascii_lowercase();
            if !EVAL_NAME_HINTS.iter().any(|h| lname.contains(h)) {
                return;
            }
            let Some(body) = m.node("body") else { return };
            let Some(body_text) = m.text("body") else { return };
            // Must actually run a forward pass to be an inference path…
            if !body_text.contains("forward(") {
                return;
            }
            // …and must lack any no-grad guard to be a problem.
            if body_text.contains("no_grad") || body_text.contains("inference_mode") {
                return;
            }
            out.push(finding_at(
                ctx,
                body,
                self.id(),
                self.severity(),
                format!(
                    "`{name}` runs a forward pass but never disables gradient tracking; \
                     wrap inference in a no-grad guard to avoid building the autograd graph \
                     (wasted memory, possible OOM)"
                ),
                Some("// tch: tch::no_grad(|| { .. });  PyTorch: with torch.no_grad():".to_string()),
            ));
        });
        out
    }
}

/// `rust/unsafe-ffi-lifetime` — flags raw CUDA/FFI allocations whose memory
/// lifetime isn't managed by an RAII wrapper.
///
/// `cudaMalloc` / `cuMemAlloc` (and `Box`/`Vec` round-trips via raw pointers)
/// hand back memory with no destructor. A missing `cudaFree` on an error path
/// leaks GPU memory; a double free corrupts the device heap. The fix is to wrap
/// the handle in a type whose `Drop` frees it, never to free by hand.
pub struct UnsafeFfiLifetimeDetector;

/// FFI allocators whose result must be paired with a manual free.
const FFI_ALLOC_FNS: &[&str] = &[
    "cudaMalloc",
    "cudaMallocManaged",
    "cuMemAlloc",
    "cudaHostAlloc",
];

impl Detector for UnsafeFfiLifetimeDetector {
    fn id(&self) -> &'static str {
        "rust/unsafe-ffi-lifetime"
    }
    fn description(&self) -> &'static str {
        "Raw CUDA/FFI allocation without an RAII (Drop) owner managing its lifetime"
    }
    fn severity(&self) -> Severity {
        Severity::Critical
    }
    fn applies_to(&self, lang: Lang) -> bool {
        lang == Lang::Rust
    }

    fn check(&self, ctx: &FileContext) -> Vec<Finding> {
        // Call by bare name or via a path (`ffi::cudaMalloc`).
        let query = r#"
            (call_expression function: (identifier) @fn)
            (call_expression function: (scoped_identifier name: (identifier) @fn))
        "#;
        let mut out = Vec::new();
        ctx.for_each_match(query, |m| {
            let Some(name) = m.text("fn") else { return };
            if !FFI_ALLOC_FNS.contains(&name) {
                return;
            }
            let Some(node) = m.node("fn") else { return };
            out.push(finding_at(
                ctx,
                node,
                self.id(),
                self.severity(),
                format!(
                    "`{name}` returns device memory with no destructor; an early return or \
                     panic before the matching free leaks (or double-frees) GPU memory — wrap \
                     the handle in a type whose `Drop` frees it instead of freeing by hand"
                ),
                Some("struct DeviceBuf(*mut c_void); impl Drop for DeviceBuf { fn drop(&mut self){ unsafe { cudaFree(self.0); } } }".to_string()),
            ));
        });
        out
    }
}

/// `c/unsafe-libc` — flags unbounded C/C++ string functions that are classic
/// buffer-overflow sources.
///
/// `gets`, `strcpy`, `strcat`, `sprintf`, and bare `scanf("%s")` write without a
/// length bound, so attacker-controlled input overruns the destination buffer.
/// Each has a bounded replacement (`fgets`, `strncpy`/`strlcpy`, `snprintf`,
/// width-limited `scanf`). Applies to firmware C and C++.
pub struct UnsafeLibcDetector;

/// Unbounded libc functions and their bounded replacements.
const UNSAFE_LIBC: &[(&str, &str)] = &[
    ("gets", "fgets(buf, sizeof buf, stdin)"),
    ("strcpy", "strncpy / strlcpy with the destination size"),
    ("strcat", "strncat / strlcat with the remaining space"),
    ("sprintf", "snprintf(buf, sizeof buf, ..)"),
];

impl Detector for UnsafeLibcDetector {
    fn id(&self) -> &'static str {
        "c/unsafe-libc"
    }
    fn description(&self) -> &'static str {
        "Unbounded C string function (gets/strcpy/strcat/sprintf); use the bounded form"
    }
    fn severity(&self) -> Severity {
        Severity::High
    }
    fn applies_to(&self, lang: Lang) -> bool {
        matches!(lang, Lang::C | Lang::Cpp)
    }

    fn check(&self, ctx: &FileContext) -> Vec<Finding> {
        self.check_with(ctx, &RuleOptions::new())
    }

    fn check_with(&self, ctx: &FileContext, options: &RuleOptions) -> Vec<Finding> {
        // `extra` adds project-banned functions (e.g. `["memcpy", "alloca"]`) on
        // top of the always-flagged unbounded libc set.
        let extra: Vec<String> = options
            .get("extra")
            .and_then(|v| v.as_array())
            .map(|a| a.iter().filter_map(|v| v.as_str().map(str::to_string)).collect())
            .unwrap_or_default();
        let query = r#"(call_expression function: (identifier) @fn) @call"#;
        let mut out = Vec::new();
        ctx.for_each_match(query, |m| {
            let Some(name) = m.text("fn") else { return };
            let builtin = UNSAFE_LIBC.iter().find(|(f, _)| *f == name).map(|(_, fix)| *fix);
            let fix = match builtin {
                Some(fix) => fix.to_string(),
                None if extra.iter().any(|e| e == name) => {
                    "use a bounded/safe alternative (project policy)".to_string()
                }
                None => return,
            };
            let Some(node) = m.node("fn") else { return };
            out.push(finding_at(
                ctx,
                node,
                self.id(),
                self.severity(),
                format!(
                    "`{name}` writes without a length bound; attacker-controlled input \
                     overruns the destination buffer — use the bounded form"
                ),
                Some(format!("// replace `{name}` with: {fix}")),
            ));
        });
        out
    }
}
