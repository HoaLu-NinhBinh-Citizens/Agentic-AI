"""Rust language-specific analysis rules.

Detects common Rust anti-patterns, ownership issues, unsafe code violations,
error handling misuse, and performance pitfalls.

Requirements: 3.4
"""

from __future__ import annotations

from src.infrastructure.analysis.universal_repo.rule_engine import UniversalRule


def get_rules() -> list[UniversalRule]:
    """Return all Rust-specific analysis rules (15-20 regex rules)."""
    return _RUST_RULES[:]


_RUST_RULES: list[UniversalRule] = [
    # ── Safety / Unsafe ───────────────────────────────────────────────────
    UniversalRule(
        id="RS001",
        language="rust",
        severity="warning",
        name="unsafe-without-safety-comment",
        description=(
            "Unsafe block without preceding SAFETY comment. "
            "Document invariants with `// SAFETY: ...` above unsafe blocks."
        ),
        patterns=[
            r"(?<!// SAFETY:.*\n)\s*unsafe\s*\{",
        ],
    ),
    # ── Error Handling ────────────────────────────────────────────────────
    UniversalRule(
        id="RS002",
        language="rust",
        severity="warning",
        name="unwrap-usage",
        description=(
            "Usage of .unwrap() — prefer .expect() with context message "
            "or proper error handling with match/? operator."
        ),
        patterns=[
            r"\.unwrap\(\)",
        ],
    ),
    # ── Performance ───────────────────────────────────────────────────────
    UniversalRule(
        id="RS003",
        language="rust",
        severity="info",
        name="clone-in-hot-path",
        description=(
            "Usage of .clone() may indicate unnecessary allocation in hot "
            "code paths. Consider borrowing or using references instead."
        ),
        patterns=[
            r"\.clone\(\)",
        ],
    ),
    # ── Library Code Quality ──────────────────────────────────────────────
    UniversalRule(
        id="RS004",
        language="rust",
        severity="error",
        name="panic-in-library-code",
        description=(
            "panic! macro in library code. Library functions should return "
            "Result or Option instead of panicking."
        ),
        patterns=[
            r"\bpanic!\s*\(",
        ],
    ),
    UniversalRule(
        id="RS005",
        language="rust",
        severity="warning",
        name="todo-unimplemented-left-in-code",
        description=(
            "todo! or unimplemented! macro left in code. "
            "These will panic at runtime if reached."
        ),
        patterns=[
            r"\btodo!\s*\(",
            r"\bunimplemented!\s*\(",
        ],
    ),
    # ── Concurrency ───────────────────────────────────────────────────────
    UniversalRule(
        id="RS006",
        language="rust",
        severity="error",
        name="lock-unwrap-pattern",
        description=(
            ".lock().unwrap() will panic on a poisoned mutex. "
            "Handle the PoisonError or use .lock().expect() with context."
        ),
        patterns=[
            r"\.lock\(\)\s*\.unwrap\(\)",
        ],
    ),
    # ── Ignored Results ───────────────────────────────────────────────────
    UniversalRule(
        id="RS007",
        language="rust",
        severity="warning",
        name="unused-result-discard",
        description=(
            "Discarding a Result with `let _ = ...` silently ignores errors. "
            "Handle the error or log it explicitly."
        ),
        patterns=[
            r"let\s+_\s*=\s*\w+.*\??\s*;",
        ],
    ),
    # ── String Patterns ───────────────────────────────────────────────────
    UniversalRule(
        id="RS008",
        language="rust",
        severity="info",
        name="string-new-push-str-pattern",
        description=(
            "String::new() followed by push_str — consider using "
            "format!() or String::from() for clarity and conciseness."
        ),
        patterns=[
            r"String::new\(\);\s*\n\s*\w+\.push_str\(",
        ],
    ),
    # ── Debug / Logging ───────────────────────────────────────────────────
    UniversalRule(
        id="RS009",
        language="rust",
        severity="warning",
        name="println-in-library-code",
        description=(
            "println! left in library code. Use the log crate or tracing "
            "crate for production logging instead."
        ),
        patterns=[
            r"\bprintln!\s*\(",
        ],
    ),
    # ── Unnecessary Allocation ────────────────────────────────────────────
    UniversalRule(
        id="RS010",
        language="rust",
        severity="info",
        name="unnecessary-box-new-return",
        description=(
            "Box::new() on return value may be unnecessary allocation. "
            "Consider returning the value directly unless trait objects require it."
        ),
        patterns=[
            r"return\s+Box::new\(",
            r"=>\s*Box::new\(",
        ],
    ),
    # ── Empty Expect ──────────────────────────────────────────────────────
    UniversalRule(
        id="RS011",
        language="rust",
        severity="warning",
        name="expect-empty-message",
        description=(
            '.expect("") called with empty message. Provide a meaningful '
            "context message explaining what failed and why it is a bug."
        ),
        patterns=[
            r'\.expect\(\s*""\s*\)',
        ],
    ),
    # ── Debug Macros ──────────────────────────────────────────────────────
    UniversalRule(
        id="RS012",
        language="rust",
        severity="warning",
        name="dbg-macro-left-in-code",
        description=(
            "dbg! macro left in code. Remove debug output before "
            "committing to production."
        ),
        patterns=[
            r"\bdbg!\s*\(",
        ],
    ),
    # ── Resource Leaks ────────────────────────────────────────────────────
    UniversalRule(
        id="RS013",
        language="rust",
        severity="error",
        name="mem-forget-usage",
        description=(
            "std::mem::forget() prevents destructors from running and can "
            "leak resources. Use ManuallyDrop if intentional."
        ),
        patterns=[
            r"\bmem::forget\s*\(",
            r"\bstd::mem::forget\s*\(",
        ],
    ),
    # ── Unsafe Pointer Deref ──────────────────────────────────────────────
    UniversalRule(
        id="RS014",
        language="rust",
        severity="error",
        name="unsafe-pointer-deref",
        description=(
            "Raw pointer dereference detected. Dereferencing *const T or "
            "*mut T requires unsafe and must be carefully validated."
        ),
        patterns=[
            r"\*\s*(?:const|mut)\s+\w+",
            r"(?<!\w)\*\w+\s*\.\w+",
        ],
    ),
    # ── Recursion ─────────────────────────────────────────────────────────
    UniversalRule(
        id="RS015",
        language="rust",
        severity="info",
        name="recursion-without-base-case-marker",
        description=(
            "Recursive function detected without clear base case annotation. "
            "Consider documenting recursion depth limits or base case."
        ),
        patterns=[
            r"fn\s+(\w+)\s*\([^)]*\)[^{]*\{[^}]*\1\s*\(",
        ],
    ),
]
