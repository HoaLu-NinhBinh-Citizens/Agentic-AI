//! Integration tests for end-to-end detector configuration: auto-discovery of
//! `config.toml` under the workspace, fallback to defaults when absent, and the
//! three override axes (enable/disable, severity, rule-specific options). These
//! drive the real `IndexEngine` (the path `main.rs` uses), not just the registry.

use std::fs;

use aircore::detector::{DetectorConfig, DetectorRegistry, Severity};
use aircore::index::IndexEngine;

/// A workspace with a Rust file that trips several detectors. Returns the temp
/// dir (kept alive by the caller) so config files can be dropped in first.
fn workspace_with_file(name: &str, src: &str) -> tempfile::TempDir {
    let dir = tempfile::tempdir().unwrap();
    fs::write(dir.path().join(name), src).unwrap();
    dir
}

/// Source that fires `rust/unwrap` (High) — used across the config cases.
const UNWRAP_SRC: &str = r#"
fn load() {
    let f = std::fs::read("model.bin").unwrap();
}
"#;

fn diagnose(dir: &tempfile::TempDir, file: &str) -> Vec<aircore::detector::Finding> {
    let engine = IndexEngine::open(dir.path()).unwrap();
    engine.diagnose(file).unwrap()
}

// ---- fallback: no config.toml ---------------------------------------------

#[test]
fn missing_config_falls_back_to_defaults() {
    let dir = workspace_with_file("load.rs", UNWRAP_SRC);
    // No config.toml written -> all built-ins active.
    let f = diagnose(&dir, "load.rs");
    assert!(
        f.iter().any(|x| x.rule_id == "rust/unwrap" && x.severity == Severity::High),
        "default config must run rust/unwrap at its default severity: {f:?}"
    );
}

#[test]
fn discover_returns_default_when_no_file_present() {
    let dir = tempfile::tempdir().unwrap();
    let cfg = DetectorConfig::discover(dir.path()).unwrap();
    assert!(cfg.disabled.is_empty() && cfg.rules.is_empty());
}

// ---- auto-discovery + disable ---------------------------------------------

#[test]
fn config_toml_at_workspace_root_disables_rule() {
    let dir = workspace_with_file("load.rs", UNWRAP_SRC);
    fs::write(
        dir.path().join("config.toml"),
        "[detectors]\ndisabled = [\"rust/unwrap\"]\n",
    )
    .unwrap();
    let f = diagnose(&dir, "load.rs");
    assert!(
        f.iter().all(|x| x.rule_id != "rust/unwrap"),
        "disabled rule in config.toml must not run: {f:?}"
    );
}

#[test]
fn agentic_config_takes_precedence_and_per_rule_enabled_false_disables() {
    let dir = workspace_with_file("load.rs", UNWRAP_SRC);
    // `.agentic/config.toml` is searched before `config.toml`.
    fs::create_dir_all(dir.path().join(".agentic")).unwrap();
    fs::write(
        dir.path().join(".agentic/config.toml"),
        "[detectors.rules.\"rust/unwrap\"]\nenabled = false\n",
    )
    .unwrap();
    // A root config.toml that would *enable* it must be ignored (lower priority).
    fs::write(dir.path().join("config.toml"), "[detectors]\n").unwrap();
    let f = diagnose(&dir, "load.rs");
    assert!(
        f.iter().all(|x| x.rule_id != "rust/unwrap"),
        "per-rule enabled=false (from the higher-priority .agentic file) must disable: {f:?}"
    );
}

// ---- severity override -----------------------------------------------------

#[test]
fn config_overrides_severity() {
    let dir = workspace_with_file("load.rs", UNWRAP_SRC);
    fs::write(
        dir.path().join("config.toml"),
        "[detectors.rules.\"rust/unwrap\"]\nseverity = \"low\"\n",
    )
    .unwrap();
    let f = diagnose(&dir, "load.rs");
    let unwrap: Vec<_> = f.iter().filter(|x| x.rule_id == "rust/unwrap").collect();
    assert!(!unwrap.is_empty(), "rule still runs: {f:?}");
    assert!(
        unwrap.iter().all(|x| x.severity == Severity::Low),
        "severity must be overridden to low (default is high): {f:?}"
    );
}

// ---- rule-specific options ------------------------------------------------

#[test]
fn config_passes_rule_options_extra_banned_libc() {
    let dir = workspace_with_file("main.c", "void f(){ char d[4]; memcpy(d, s, 9); }");
    // `memcpy` isn't in the built-in unbounded set; the `extra` option adds it.
    fs::write(
        dir.path().join("config.toml"),
        "[detectors.rules.\"c/unsafe-libc\"]\noptions = { extra = [\"memcpy\"] }\n",
    )
    .unwrap();
    let f = diagnose(&dir, "main.c");
    assert!(
        f.iter().any(|x| x.rule_id == "c/unsafe-libc" && x.message.contains("memcpy")),
        "extra-banned function from options must flag: {f:?}"
    );
}

#[test]
fn rule_options_default_when_unset() {
    // Without the `extra` option, memcpy is not flagged (only built-ins are).
    let dir = workspace_with_file("main.c", "void f(){ char d[4]; memcpy(d, s, 9); }");
    let f = diagnose(&dir, "main.c");
    assert!(
        f.iter().all(|x| x.rule_id != "c/unsafe-libc"),
        "memcpy must not flag without the extra option: {f:?}"
    );
}

#[test]
fn data_leakage_split_keyword_option_is_honored() {
    // Project names its split `learn_x`; with the override, fitting on it is OK.
    let src = "fn p(learn_x: &D){ scaler.fit(learn_x); }";
    let cfg = DetectorConfig::from_toml_str(
        "[detectors.rules.\"ml/data-leakage\"]\noptions = { split_keyword = \"learn\" }\n",
    )
    .unwrap();
    let reg = DetectorRegistry::with_config(cfg);
    let f = reg.analyze("p.rs", src.as_bytes().to_vec()).unwrap();
    assert!(
        f.iter().all(|x| x.rule_id != "ml/data-leakage"),
        "custom split_keyword must suppress the leakage finding: {f:?}"
    );
}

// ---- metadata --------------------------------------------------------------

#[test]
fn metadata_reflects_effective_config() {
    let cfg = DetectorConfig::from_toml_str(
        "[detectors]\ndisabled = [\"rust/unsafe-block\"]\n\
         [detectors.rules.\"rust/unwrap\"]\nseverity = \"critical\"\n",
    )
    .unwrap();
    let reg = DetectorRegistry::with_config(cfg);
    let meta = reg.metadata();

    let unwrap = meta.iter().find(|m| m.id == "rust/unwrap").unwrap();
    assert!(unwrap.enabled);
    assert_eq!(unwrap.default_severity, Severity::High);
    assert_eq!(unwrap.effective_severity, Severity::Critical);
    assert!(unwrap.languages.contains(&"rust"));

    let unsafe_block = meta.iter().find(|m| m.id == "rust/unsafe-block").unwrap();
    assert!(!unsafe_block.enabled, "disabled rule must report enabled=false");

    let libc = meta.iter().find(|m| m.id == "c/unsafe-libc").unwrap();
    assert!(libc.languages.contains(&"c") && libc.languages.contains(&"cpp"));
}

// ---- malformed config is an error, not a silent default --------------------

#[test]
fn malformed_config_errors() {
    let dir = workspace_with_file("load.rs", UNWRAP_SRC);
    fs::write(dir.path().join("config.toml"), "[detectors]\ndisabled = \"not-a-list\"\n").unwrap();
    let err = IndexEngine::open(dir.path());
    assert!(err.is_err(), "a malformed config.toml must surface an error, not be ignored");
}
