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
fn default_registry_lists_three_builtins() {
    let ids = DetectorRegistry::with_defaults().ids();
    assert!(ids.contains(&"rust/unwrap"));
    assert!(ids.contains(&"rust/unsafe-block"));
    assert!(ids.contains(&"ml/hardcoded-hyperparam"));
}
