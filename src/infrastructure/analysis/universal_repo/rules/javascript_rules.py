"""JavaScript/TypeScript static analysis rules for the Universal Rule Engine.

Covers common JS/TS issues: type coercion, unused variables, security risks,
code quality, import patterns, error handling, and best practices.

Requirements: 3.2, 3.8
"""

from __future__ import annotations

from src.infrastructure.analysis.universal_repo.rule_engine import UniversalRule


def get_rules() -> list[UniversalRule]:
    """Return all JavaScript/TypeScript analysis rules (minimum 30 rules)."""
    return _JS_RULES[:]


_JS_RULES: list[UniversalRule] = [
    # ── Type Checking / Equality ──────────────────────────────────────────
    UniversalRule(
        id="JS001",
        language="javascript",
        severity="warning",
        name="loose-equality",
        description="Use === instead of == to avoid type coercion bugs",
        patterns=[r"[^!=]==[^=]"],
    ),
    UniversalRule(
        id="JS002",
        language="javascript",
        severity="warning",
        name="loose-inequality",
        description="Use !== instead of != to avoid type coercion bugs",
        patterns=[r"[^!]!=[^=]"],
    ),
    UniversalRule(
        id="JS003",
        language="javascript",
        severity="warning",
        name="any-type-usage",
        description="Explicit 'any' type defeats TypeScript type checking",
        patterns=[r":\s*any\b", r"<any>", r"as\s+any\b"],
    ),
    UniversalRule(
        id="JS004",
        language="javascript",
        severity="info",
        name="typeof-string-compare",
        description="typeof comparison with invalid type string is always false",
        patterns=[
            r"typeof\s+\w+\s*[!=]==?\s*['\"]"
            r"(?!undefined|object|boolean|number|string|function|symbol|bigint)['\"]"
        ],
    ),
    # ── Unused Variables ──────────────────────────────────────────────────
    UniversalRule(
        id="JS005",
        language="javascript",
        severity="warning",
        name="var-usage",
        description="Prefer let/const over var to avoid hoisting issues",
        patterns=[r"^\s*var\s+\w+"],
    ),
    UniversalRule(
        id="JS006",
        language="javascript",
        severity="info",
        name="unused-variable-pattern",
        description="Variable declared but potentially unused (declaration with no assignment body)",
        patterns=[r"^\s*(?:let|const|var)\s+\w+\s*;\s*$"],
    ),
    # ── Import Resolution ─────────────────────────────────────────────────
    UniversalRule(
        id="JS007",
        language="javascript",
        severity="info",
        name="wildcard-import",
        description="Wildcard imports can increase bundle size; prefer named imports",
        patterns=[r"import\s+\*\s+as\s+\w+\s+from"],
    ),
    UniversalRule(
        id="JS008",
        language="javascript",
        severity="warning",
        name="duplicate-import-path",
        description="Same module imported multiple times in one file",
        patterns=[
            r"(?:import|require)\s*\(?['\"]([^'\"]+)['\"]\)?.*\n"
            r"(?:.*\n)*?(?:import|require)\s*\(?['\"](\1)['\"]"
        ],
    ),
    UniversalRule(
        id="JS009",
        language="javascript",
        severity="info",
        name="require-in-esm",
        description="require() alongside ES module imports; use consistent module syntax",
        patterns=[r"(?=.*\bimport\s).*\brequire\s*\("],
    ),
    # ── Security ──────────────────────────────────────────────────────────
    UniversalRule(
        id="JS010",
        language="javascript",
        severity="error",
        name="eval-usage",
        description="eval() executes arbitrary code and is a security risk",
        patterns=[r"\beval\s*\("],
    ),
    UniversalRule(
        id="JS011",
        language="javascript",
        severity="error",
        name="document-write",
        description="document.write() can overwrite the page and enable XSS",
        patterns=[r"\bdocument\.write\s*\("],
    ),
    UniversalRule(
        id="JS012",
        language="javascript",
        severity="warning",
        name="innerhtml-assignment",
        description="innerHTML assignment can enable XSS attacks; use textContent or sanitize",
        patterns=[r"\.innerHTML\s*="],
    ),
    UniversalRule(
        id="JS013",
        language="javascript",
        severity="warning",
        name="new-function",
        description="new Function() is equivalent to eval() and poses security risk",
        patterns=[r"\bnew\s+Function\s*\("],
    ),
    # ── Best Practices ────────────────────────────────────────────────────
    UniversalRule(
        id="JS014",
        language="javascript",
        severity="warning",
        name="console-log",
        description="console.log left in code; remove before production",
        patterns=[r"\bconsole\.log\s*\("],
    ),
    UniversalRule(
        id="JS015",
        language="javascript",
        severity="warning",
        name="debugger-statement",
        description="debugger statement should be removed before production",
        patterns=[r"^\s*debugger\s*;?\s*$"],
    ),
    UniversalRule(
        id="JS016",
        language="javascript",
        severity="info",
        name="alert-usage",
        description="alert() should not be used in production code",
        patterns=[r"\balert\s*\("],
    ),
    UniversalRule(
        id="JS017",
        language="javascript",
        severity="info",
        name="console-debug",
        description="console.debug left in code; consider removing",
        patterns=[r"\bconsole\.debug\s*\("],
    ),
    # ── Error Handling ────────────────────────────────────────────────────
    UniversalRule(
        id="JS018",
        language="javascript",
        severity="warning",
        name="empty-catch",
        description="Empty catch block silently swallows errors",
        patterns=[r"catch\s*\([^)]*\)\s*\{\s*\}"],
    ),
    UniversalRule(
        id="JS019",
        language="javascript",
        severity="warning",
        name="promise-no-catch",
        description="Promise chain without .catch() may lose rejected errors",
        patterns=[r"\.then\s*\([^)]*\)\s*(?:;|\n)"],
    ),
    UniversalRule(
        id="JS020",
        language="javascript",
        severity="warning",
        name="throw-string-literal",
        description="Throw an Error object instead of a string literal",
        patterns=[r"\bthrow\s+['\"]"],
    ),
    UniversalRule(
        id="JS021",
        language="javascript",
        severity="warning",
        name="floating-promise",
        description="Async function called without await; result is a floating promise",
        patterns=[r"^\s*(?!return|await|yield)\w+\s*\.\s*\w+Async\s*\("],
    ),
    # ── Code Quality ──────────────────────────────────────────────────────
    UniversalRule(
        id="JS022",
        language="javascript",
        severity="info",
        name="magic-number",
        description="Magic number in code; consider extracting to a named constant",
        patterns=[r"(?<!=)\s+(?:(?<!\w)\d{4,}(?!\w))(?!\s*[;,\]\})])"],
    ),
    UniversalRule(
        id="JS023",
        language="javascript",
        severity="info",
        name="nested-ternary",
        description="Nested ternary operators reduce readability",
        patterns=[r"\?[^:]*\?"],
    ),
    UniversalRule(
        id="JS024",
        language="javascript",
        severity="warning",
        name="no-return-assign",
        description="Assignment inside return statement may be unintentional",
        patterns=[r"\breturn\s+\w+\s*=[^=]"],
    ),
    UniversalRule(
        id="JS025",
        language="javascript",
        severity="warning",
        name="await-in-loop",
        description="await inside loop runs sequentially; consider Promise.all",
        patterns=[r"(?:for|while)\s*\([^)]*\)\s*\{[^}]*\bawait\b"],
    ),
    UniversalRule(
        id="JS026",
        language="javascript",
        severity="warning",
        name="implicit-global",
        description="Assignment without declaration creates implicit global variable",
        patterns=[r"^\s*(?!(?:var|let|const|this\.|self\.|export)\b)\w+\s*=\s*[^=]"],
    ),
    # ── Miscellaneous Quality ─────────────────────────────────────────────
    UniversalRule(
        id="JS027",
        language="javascript",
        severity="warning",
        name="no-prototype-builtins",
        description="Call hasOwnProperty via Object.prototype to avoid shadowing",
        patterns=[r"\w+\.hasOwnProperty\s*\("],
    ),
    UniversalRule(
        id="JS028",
        language="javascript",
        severity="warning",
        name="no-self-compare",
        description="Comparing a variable to itself is likely a bug",
        patterns=[r"\b(\w+)\s*[!=<>]==?\s*\1\b"],
    ),
    UniversalRule(
        id="JS029",
        language="javascript",
        severity="warning",
        name="no-setter-return",
        description="Setter should not return a value",
        patterns=[r"set\s+\w+\s*\([^)]*\)\s*\{[^}]*\breturn\s+\w"],
    ),
    UniversalRule(
        id="JS030",
        language="javascript",
        severity="warning",
        name="no-unreachable-code",
        description="Code after return/throw/break is unreachable",
        patterns=[
            r"(?:return|throw|break|continue)\s+[^;]*;\s*\n"
            r"\s*(?!case\b|default\b|\})[a-zA-Z]"
        ],
    ),
]
