"""Go language-specific analysis rules.

Detects common Go anti-patterns, error handling issues, goroutine leaks,
concurrency problems, and production code quality violations.

Requirements: 3.5
"""

from __future__ import annotations

from src.infrastructure.analysis.universal_repo.rule_engine import UniversalRule


def get_rules() -> list[UniversalRule]:
    """Return all Go-specific analysis rules (15-20 regex rules)."""
    return _GO_RULES[:]


_GO_RULES: list[UniversalRule] = [
    # ── Error Handling ────────────────────────────────────────────────────
    UniversalRule(
        id="GO001",
        language="go",
        severity="error",
        name="unchecked-error",
        description=(
            "Error return value is not checked. Always handle errors "
            "explicitly — use `if err != nil` after fallible calls."
        ),
        patterns=[
            r"^\s+\w+,\s*_\s*:?=\s*\w+",
            r"^\s+_,\s*_\s*:?=\s*\w+",
        ],
    ),
    # ── Goroutine Safety ──────────────────────────────────────────────────
    UniversalRule(
        id="GO002",
        language="go",
        severity="warning",
        name="goroutine-without-sync",
        description=(
            "Goroutine launched without WaitGroup, channel, or context. "
            "This risks goroutine leaks if the parent exits."
        ),
        patterns=[
            r"\bgo\s+func\s*\(",
        ],
    ),
    # ── Resource Management ───────────────────────────────────────────────
    UniversalRule(
        id="GO003",
        language="go",
        severity="error",
        name="defer-in-loop",
        description=(
            "defer inside a loop — deferred calls only execute when the "
            "function returns, causing resource accumulation in loops."
        ),
        patterns=[
            r"for\s+.*\{[^}]*\bdefer\b",
            r"for\s*\{[^}]*\bdefer\b",
        ],
    ),
    # ── Production Code Quality ───────────────────────────────────────────
    UniversalRule(
        id="GO004",
        language="go",
        severity="warning",
        name="fmt-println-in-production",
        description=(
            "fmt.Println or fmt.Printf left in production code. "
            "Use structured logging (log, slog, zerolog) instead."
        ),
        patterns=[
            r"\bfmt\.Print(?:ln|f)?\s*\(",
        ],
    ),
    UniversalRule(
        id="GO005",
        language="go",
        severity="error",
        name="panic-in-non-main",
        description=(
            "panic() in non-main code. Library and package functions "
            "should return errors instead of panicking."
        ),
        patterns=[
            r"\bpanic\s*\(",
        ],
    ),
    UniversalRule(
        id="GO006",
        language="go",
        severity="error",
        name="os-exit-in-non-main",
        description=(
            "os.Exit() in non-main package. Only main() should call "
            "os.Exit() — other packages should return errors."
        ),
        patterns=[
            r"\bos\.Exit\s*\(",
        ],
    ),
    # ── Map Safety ────────────────────────────────────────────────────────
    UniversalRule(
        id="GO007",
        language="go",
        severity="warning",
        name="map-access-without-ok-check",
        description=(
            "Map access without comma-ok check. Use `v, ok := m[key]` "
            "to safely handle missing keys."
        ),
        patterns=[
            r"^\s+\w+\s*:?=\s*\w+\[\w+\]\s*$",
        ],
    ),
    # ── Timing / Production ───────────────────────────────────────────────
    UniversalRule(
        id="GO008",
        language="go",
        severity="warning",
        name="time-sleep-in-production",
        description=(
            "time.Sleep in production code. Use timers, tickers, or "
            "context-based cancellation for proper scheduling."
        ),
        patterns=[
            r"\btime\.Sleep\s*\(",
        ],
    ),
    # ── Init Function ─────────────────────────────────────────────────────
    UniversalRule(
        id="GO009",
        language="go",
        severity="info",
        name="init-function-usage",
        description=(
            "init() function detected. init() runs implicitly and can "
            "make testing harder. Consider explicit initialization."
        ),
        patterns=[
            r"^func\s+init\s*\(\s*\)\s*\{",
        ],
    ),
    # ── Naked Goroutine ───────────────────────────────────────────────────
    UniversalRule(
        id="GO010",
        language="go",
        severity="warning",
        name="naked-goroutine-no-error-handling",
        description=(
            "Goroutine without error handling or recovery. Add "
            "defer/recover or pass errors via channel."
        ),
        patterns=[
            r"\bgo\s+\w+\s*\(",
        ],
    ),
    # ── Concurrency Patterns ──────────────────────────────────────────────
    UniversalRule(
        id="GO011",
        language="go",
        severity="warning",
        name="empty-select-statement",
        description=(
            "Empty select{} blocks forever. This is rarely intentional "
            "and may indicate missing channel cases or context cancellation."
        ),
        patterns=[
            r"\bselect\s*\{\s*\}",
        ],
    ),
    # ── Context Usage ─────────────────────────────────────────────────────
    UniversalRule(
        id="GO012",
        language="go",
        severity="warning",
        name="context-todo-left-in-code",
        description=(
            "context.TODO() left in code. Replace with a proper context "
            "(context.Background() or propagated parent context)."
        ),
        patterns=[
            r"\bcontext\.TODO\s*\(\s*\)",
        ],
    ),
    # ── Global State ──────────────────────────────────────────────────────
    UniversalRule(
        id="GO013",
        language="go",
        severity="warning",
        name="global-mutex-pattern",
        description=(
            "Global mutex detected. Global mutable state with mutexes "
            "makes testing difficult. Consider dependency injection."
        ),
        patterns=[
            r"^var\s+\w+\s+sync\.(?:Mutex|RWMutex)",
            r"^var\s+\w+\s*=\s*&?sync\.(?:Mutex|RWMutex)\{\}",
        ],
    ),
    # ── Channel Patterns ──────────────────────────────────────────────────
    UniversalRule(
        id="GO014",
        language="go",
        severity="info",
        name="channel-never-closed",
        description=(
            "Channel created but never closed in visible scope. "
            "Unclosed channels can cause goroutine leaks if receivers "
            "range over them."
        ),
        patterns=[
            r"\bmake\s*\(\s*chan\b",
        ],
    ),
    # ── Recover Patterns ──────────────────────────────────────────────────
    UniversalRule(
        id="GO015",
        language="go",
        severity="warning",
        name="recover-without-meaningful-handling",
        description=(
            "recover() without meaningful error handling. Log the panic "
            "value and stack trace, or propagate as an error."
        ),
        patterns=[
            r"\brecover\s*\(\s*\)",
        ],
    ),
]
