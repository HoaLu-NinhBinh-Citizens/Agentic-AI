//! Detector-layer tests: each built-in rule fires on the bad case, stays quiet
//! on the good case, and reports a precise location + fix suggestion. Also
//! covers the registry (severity ordering, language filtering, toggling).

use aircore::detector::{DetectorRegistry, Severity};

fn analyze(path: &str, src: &str) -> Vec<aircore::detector::Finding> {
    DetectorRegistry::with_defaults()
        .analyze(path, src.as_bytes().to_vec())
        .unwrap()
}

// ---- rust/unwrap ----------------------------------------------------------

#[test]
fn flags_unwrap_and_expect() {
    let src = r#"
fn load() {
    let f = std::fs::read("model.bin").unwrap();
    let g = std::fs::read("cfg.toml").expect("missing config");
}
"#;
    let f = analyze("src/load.rs", src);
    let ids: Vec<_> = f.iter().filter(|x| x.rule_id == "rust/unwrap").collect();
    assert_eq!(ids.len(), 2, "should flag both unwrap and expect: {f:?}");
    assert!(ids.iter().all(|x| x.severity == Severity::High));
    // Precise location + a copy-pasteable fix.
    let unwrap = ids.iter().find(|x| x.before.as_deref().unwrap().contains("unwrap")).unwrap();
    assert_eq!(unwrap.line, 3);
    assert!(unwrap.after.as_deref().unwrap().contains('?'), "fix should propagate with ?");
}

#[test]
fn does_not_flag_clean_error_handling() {
    let src = r#"
fn load() -> anyhow::Result<()> {
    let f = std::fs::read("model.bin")?;
    Ok(())
}
"#;
    let f = analyze("src/load.rs", src);
    assert!(f.iter().all(|x| x.rule_id != "rust/unwrap"), "clean `?` must not flag: {f:?}");
}

// ---- rust/unsafe-block ----------------------------------------------------

#[test]
fn flags_unsafe_block_without_safety_comment() {
    let src = r#"
fn poke(p: *mut u8) {
    unsafe { *p = 1; }
}
"#;
    let f = analyze("src/ffi.rs", src);
    let u: Vec<_> = f.iter().filter(|x| x.rule_id == "rust/unsafe-block").collect();
    assert_eq!(u.len(), 1, "unsafe block without SAFETY should flag: {f:?}");
    assert_eq!(u[0].severity, Severity::Medium);
}

#[test]
fn unsafe_block_with_safety_comment_is_ok() {
    let src = r#"
fn poke(p: *mut u8) {
    // SAFETY: p is a valid, unique, aligned pointer for the call's duration.
    unsafe { *p = 1; }
}
"#;
    let f = analyze("src/ffi.rs", src);
    assert!(
        f.iter().all(|x| x.rule_id != "rust/unsafe-block"),
        "documented unsafe must not flag: {f:?}"
    );
}

// ---- ml/hardcoded-hyperparam ---------------------------------------------

#[test]
fn flags_hardcoded_hyperparams_rust() {
    let src = r#"
fn train() {
    let learning_rate = 0.001;
    let batch_size = 32;
    let user_count = 5; // not a hyper-parameter -> must not flag
}
"#;
    let f = analyze("src/train.rs", src);
    let h: Vec<_> = f.iter().filter(|x| x.rule_id == "ml/hardcoded-hyperparam").collect();
    assert_eq!(h.len(), 2, "should flag learning_rate + batch_size only: {f:?}");
    assert!(h.iter().any(|x| x.message.contains("learning_rate")));
    assert!(h.iter().all(|x| x.after.as_deref().unwrap().contains("config")));
}

#[test]
fn flags_hardcoded_hyperparams_python() {
    let src = "epochs = 100\nseed = 42\nname = 7\n";
    let f = analyze("train.py", src);
    let h: Vec<_> = f.iter().filter(|x| x.rule_id == "ml/hardcoded-hyperparam").collect();
    assert_eq!(h.len(), 2, "epochs + seed, not `name`: {f:?}");
}

// ---- registry behavior ----------------------------------------------------

#[test]
fn findings_are_sorted_critical_first_then_by_line() {
    // unsafe (Medium, line 5) + unwrap (High, line 3): High must come first.
    let src = r#"
fn f(p: *mut u8) {
    let x = foo().unwrap();
    let y = 1;
    unsafe { *p = 1; }
}
"#;
    let f = analyze("src/f.rs", src);
    assert!(f.len() >= 2);
    // High (unwrap) sorts before Medium (unsafe).
    assert_eq!(f[0].rule_id, "rust/unwrap");
    assert!(f.windows(2).all(|w| w[0].severity <= w[1].severity));
}

#[test]
fn unsupported_language_yields_no_findings() {
    // Markdown isn't a known Lang -> analyze returns empty, not an error.
    let f = analyze("README.md", "let x = foo().unwrap();");
    assert!(f.is_empty());
}

#[test]
fn disabled_detector_is_skipped() {
    let mut reg = DetectorRegistry::with_defaults();
    reg.disable("rust/unwrap");
    let findings = reg
        .analyze("src/load.rs", b"fn f(){ let x = g().unwrap(); }".to_vec())
        .unwrap();
    assert!(
        findings.iter().all(|x| x.rule_id != "rust/unwrap"),
        "disabled rule must not fire: {findings:?}"
    );
}

#[test]
fn default_registry_lists_all_builtins() {
    let ids = DetectorRegistry::with_defaults().ids();
    for id in [
        "rust/unwrap",
        "rust/unsafe-block",
        "ml/hardcoded-hyperparam",
        "ml/data-leakage",
        "ml/device-mismatch",
        "ml/no-grad-eval",
        "rust/unsafe-ffi-lifetime",
        "c/unsafe-libc",
    ] {
        assert!(ids.contains(&id), "missing builtin {id}: {ids:?}");
    }
}

// ---- ml/data-leakage ------------------------------------------------------

#[test]
fn flags_fit_on_full_dataset_but_not_on_train_split() {
    let src = r#"
fn prep(x: &Data, x_train: &Data) {
    scaler.fit(x);            // leakage: fit on full data
    scaler.fit(x_train);      // ok: fit on the train split
}
"#;
    let f = analyze("src/prep.rs", src);
    let l: Vec<_> = f.iter().filter(|x| x.rule_id == "ml/data-leakage").collect();
    assert_eq!(l.len(), 1, "only the full-dataset fit should flag: {f:?}");
    assert_eq!(l[0].severity, Severity::High);
    assert_eq!(l[0].line, 3);
}

#[test]
fn flags_fit_transform_python() {
    let src = "scaler = StandardScaler()\nx = scaler.fit_transform(data)\n";
    let f = analyze("prep.py", src);
    assert!(f.iter().any(|x| x.rule_id == "ml/data-leakage"), "{f:?}");
}

// ---- ml/device-mismatch ---------------------------------------------------

#[test]
fn flags_cpu_tensor_in_cuda_code() {
    let src = r#"
fn run() {
    let dev = Device::Cuda(0);
    let t = input.to_device(Device::Cpu);  // mismatch
}
"#;
    let f = analyze("src/run.rs", src);
    let d: Vec<_> = f.iter().filter(|x| x.rule_id == "ml/device-mismatch").collect();
    assert_eq!(d.len(), 1, "cpu placement in cuda code should flag: {f:?}");
}

#[test]
fn does_not_flag_cpu_when_no_gpu_in_file() {
    let src = r#"
fn run() {
    let t = input.to_device(Device::Cpu);
}
"#;
    let f = analyze("src/run.rs", src);
    assert!(
        f.iter().all(|x| x.rule_id != "ml/device-mismatch"),
        "cpu-only file must not flag: {f:?}"
    );
}

// ---- ml/no-grad-eval ------------------------------------------------------

#[test]
fn flags_eval_forward_without_no_grad() {
    let src = r#"
fn evaluate(model: &Net, x: &Tensor) -> Tensor {
    model.forward(x)
}
"#;
    let f = analyze("src/eval.rs", src);
    let n: Vec<_> = f.iter().filter(|x| x.rule_id == "ml/no-grad-eval").collect();
    assert_eq!(n.len(), 1, "eval forward without no_grad should flag: {f:?}");
}

#[test]
fn eval_with_no_grad_is_ok() {
    let src = r#"
fn evaluate(model: &Net, x: &Tensor) -> Tensor {
    tch::no_grad(|| model.forward(x))
}
"#;
    let f = analyze("src/eval.rs", src);
    assert!(
        f.iter().all(|x| x.rule_id != "ml/no-grad-eval"),
        "guarded eval must not flag: {f:?}"
    );
}

// ---- rust/unsafe-ffi-lifetime ---------------------------------------------

#[test]
fn flags_unmanaged_cuda_alloc() {
    let src = r#"
fn alloc(n: usize) {
    let mut p = std::ptr::null_mut();
    unsafe { cudaMalloc(&mut p, n); }
}
"#;
    let f = analyze("src/cuda.rs", src);
    let c: Vec<_> = f.iter().filter(|x| x.rule_id == "rust/unsafe-ffi-lifetime").collect();
    assert_eq!(c.len(), 1, "raw cudaMalloc should flag: {f:?}");
    assert_eq!(c[0].severity, Severity::Critical);
}

// ---- c/unsafe-libc --------------------------------------------------------

#[test]
fn flags_unbounded_libc_string_calls() {
    let src = r#"
void copy(char *dst, const char *src) {
    strcpy(dst, src);
    char buf[8];
    sprintf(buf, "%s", src);
}
"#;
    let f = analyze("main.c", src);
    let c: Vec<_> = f.iter().filter(|x| x.rule_id == "c/unsafe-libc").collect();
    assert_eq!(c.len(), 2, "strcpy + sprintf should flag: {f:?}");
}

#[test]
fn unsafe_libc_applies_to_cpp_too() {
    let f = analyze("main.cpp", "void f(){ char b[4]; strcat(b, \"x\"); }");
    assert!(f.iter().any(|x| x.rule_id == "c/unsafe-libc"), "{f:?}");
}

// ---- config.toml toggle ---------------------------------------------------

#[test]
fn config_disables_listed_detectors() {
    use aircore::detector::DetectorConfig;
    let cfg = DetectorConfig::from_toml_str(
        "[detectors]\ndisabled = [\"c/unsafe-libc\", \"ml/no-grad-eval\"]\n",
    )
    .unwrap();
    let reg = DetectorRegistry::with_config(cfg);
    let f = reg
        .analyze("main.c", b"void f(){ char b[4]; strcpy(b, \"x\"); }".to_vec())
        .unwrap();
    assert!(
        f.iter().all(|x| x.rule_id != "c/unsafe-libc"),
        "disabled-by-config rule must not fire: {f:?}"
    );
}

#[test]
fn config_without_detectors_section_disables_nothing() {
    use aircore::detector::DetectorConfig;
    let cfg = DetectorConfig::from_toml_str("[other]\nkey = 1\n").unwrap();
    assert!(cfg.disabled.is_empty());
}
