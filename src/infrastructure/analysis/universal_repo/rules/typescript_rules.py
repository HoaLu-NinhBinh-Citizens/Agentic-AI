"""TypeScript static analysis rules for the Universal Rule Engine.

Imports all JavaScript rules (which apply equally to TypeScript) and adds
TypeScript-specific rules for type safety, generics, and TS-only patterns.

Requirements: 3.2, 3.8
"""

from __future__ import annotations

from src.infrastructure.analysis.universal_repo.rule_engine import UniversalRule

from .javascript_rules import get_rules as get_js_rules


def get_rules() -> list[UniversalRule]:
    """Return all TypeScript rules (JS base + TS-specific, minimum 30 combined)."""
    # Rebind JS rules to 'typescript' language
    ts_base = []
    for rule in get_js_rules():
        ts_base.append(UniversalRule(
            id=rule.id,
            language="typescript",
            severity=rule.severity,
            name=rule.name,
            description=rule.description,
            patterns=rule.patterns[:],
            ast_query=rule.ast_query,
        ))
    return ts_base + _TS_SPECIFIC_RULES[:]


_TS_SPECIFIC_RULES: list[UniversalRule] = [
    # ── Type Safety ───────────────────────────────────────────────────────
    UniversalRule(
        id="TS001",
        language="typescript",
        severity="warning",
        name="any-type-usage",
        description="Explicit 'any' type defeats TypeScript type checking",
        patterns=[r":\s*any\b", r"as\s+any\b", r"<any>"],
    ),
    UniversalRule(
        id="TS002",
        language="typescript",
        severity="info",
        name="unknown-type-without-narrowing",
        description="'unknown' type used without type narrowing may cause runtime errors",
        patterns=[r":\s*unknown\b"],
    ),
    UniversalRule(
        id="TS003",
        language="typescript",
        severity="warning",
        name="non-null-assertion",
        description="Non-null assertion (!) bypasses null checks; prefer explicit narrowing",
        patterns=[r"\w+!\.\w+", r"\w+!\["],
    ),
    UniversalRule(
        id="TS004",
        language="typescript",
        severity="warning",
        name="ts-ignore-comment",
        description="@ts-ignore suppresses type errors; prefer @ts-expect-error with reason",
        patterns=[r"//\s*@ts-ignore"],
    ),
    UniversalRule(
        id="TS005",
        language="typescript",
        severity="info",
        name="type-assertion-over-guard",
        description="Type assertion (as) is unsafe; prefer type guard function",
        patterns=[r"\bas\s+(?!const\b)\w+"],
    ),
    # ── Interface & Type Patterns ─────────────────────────────────────────
    UniversalRule(
        id="TS006",
        language="typescript",
        severity="info",
        name="empty-interface",
        description="Empty interface has no contract; consider removing or adding members",
        patterns=[r"interface\s+\w+\s*\{\s*\}"],
    ),
    UniversalRule(
        id="TS007",
        language="typescript",
        severity="info",
        name="interface-prefix-i",
        description="Hungarian notation (I-prefix) for interfaces is discouraged in modern TS",
        patterns=[r"\binterface\s+I[A-Z]\w+"],
    ),
    UniversalRule(
        id="TS008",
        language="typescript",
        severity="warning",
        name="enum-mismatch-risk",
        description="Numeric enum without explicit values may break on reordering",
        patterns=[r"\benum\s+\w+\s*\{[^}]*(?<!\s=\s\d)[,\n][^}]*\}"],
    ),
    # ── Generic & Advanced Types ──────────────────────────────────────────
    UniversalRule(
        id="TS009",
        language="typescript",
        severity="info",
        name="generic-object-type",
        description="Avoid generic Object type; use Record<string, unknown> or specific type",
        patterns=[r":\s*Object\b", r":\s*\{\}\s*[;,)]"],
    ),
    UniversalRule(
        id="TS010",
        language="typescript",
        severity="warning",
        name="return-type-missing-async",
        description="Async function missing explicit return type; add Promise<T> annotation",
        patterns=[r"async\s+\w+\s*\([^)]*\)\s*\{"],
    ),
    # ── Module & Import ───────────────────────────────────────────────────
    UniversalRule(
        id="TS011",
        language="typescript",
        severity="warning",
        name="import-type-missing",
        description="Type-only import should use 'import type' for build optimization",
        patterns=[r"import\s*\{\s*(?:type\s+)?\w+(?:Type|Interface|Props|State)\s*\}"],
    ),
    UniversalRule(
        id="TS012",
        language="typescript",
        severity="info",
        name="barrel-re-export",
        description="Barrel file re-exports everything; may impact tree-shaking",
        patterns=[r"export\s+\*\s+from\s+['\"]\."],
    ),
]
