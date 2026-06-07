"""C/C++ static analysis rules for the Universal Rule Engine.

Covers memory safety, unsafe functions, uninitialized variables, null pointer
handling, header guards, resource management, and common C/C++ pitfalls.

Requirements: 3.3, 3.8
"""

from __future__ import annotations

from src.infrastructure.analysis.universal_repo.rule_engine import UniversalRule


def get_rules() -> list[UniversalRule]:
    """Return all C/C++ analysis rules (minimum 30 rules)."""
    return _C_RULES[:]


_C_RULES: list[UniversalRule] = [
    # ── Memory Safety ─────────────────────────────────────────────────────
    UniversalRule(
        id="CC001",
        language="c",
        severity="error",
        name="malloc-without-null-check",
        description="malloc/calloc result used without NULL check; may dereference NULL",
        patterns=[r"\b(?:malloc|calloc|realloc)\s*\([^)]*\)\s*;"],
    ),
    UniversalRule(
        id="CC002",
        language="c",
        severity="error",
        name="use-after-free-pattern",
        description="Pointer used after free(); potential use-after-free vulnerability",
        patterns=[r"\bfree\s*\(\s*(\w+)\s*\);\s*\n\s*(?!.*\1\s*=\s*NULL).*\1"],
    ),
    UniversalRule(
        id="CC003",
        language="c",
        severity="error",
        name="double-free-risk",
        description="free() called on pointer that may already be freed",
        patterns=[r"\bfree\s*\(\s*(\w+)\s*\);\s*(?:.*\n){0,5}.*\bfree\s*\(\s*\1\s*\)"],
    ),
    UniversalRule(
        id="CC004",
        language="c",
        severity="warning",
        name="malloc-cast",
        description="Casting malloc result is unnecessary in C and may hide missing includes",
        patterns=[r"\(\s*\w+\s*\*\s*\)\s*malloc\s*\("],
    ),
    # ── Buffer Overflow Functions ─────────────────────────────────────────
    UniversalRule(
        id="CC005",
        language="c",
        severity="error",
        name="gets-usage",
        description="gets() has no bounds checking; use fgets() instead",
        patterns=[r"\bgets\s*\("],
    ),
    UniversalRule(
        id="CC006",
        language="c",
        severity="error",
        name="strcpy-usage",
        description="strcpy() has no bounds checking; use strncpy() or strlcpy()",
        patterns=[r"\bstrcpy\s*\("],
    ),
    UniversalRule(
        id="CC007",
        language="c",
        severity="error",
        name="sprintf-usage",
        description="sprintf() has no bounds checking; use snprintf() instead",
        patterns=[r"\bsprintf\s*\("],
    ),
    UniversalRule(
        id="CC008",
        language="c",
        severity="error",
        name="strcat-usage",
        description="strcat() has no bounds checking; use strncat() or strlcat()",
        patterns=[r"\bstrcat\s*\("],
    ),
    # ── Uninitialized Variables ───────────────────────────────────────────
    UniversalRule(
        id="CC009",
        language="c",
        severity="warning",
        name="uninitialized-pointer",
        description="Pointer declared without initialization; may contain garbage address",
        patterns=[r"^\s*\w+\s*\*\s*\w+\s*;\s*$"],
    ),
    UniversalRule(
        id="CC010",
        language="c",
        severity="warning",
        name="uninitialized-local-var",
        description="Local variable declared without initialization",
        patterns=[r"^\s+(?:int|float|double|char|long|short|unsigned)\s+\w+\s*;\s*$"],
    ),
    # ── Null Pointer ──────────────────────────────────────────────────────
    UniversalRule(
        id="CC011",
        language="c",
        severity="error",
        name="null-deref-after-alloc",
        description="Pointer from malloc/calloc used without NULL check",
        patterns=[
            r"\w+\s*=\s*(?:malloc|calloc|realloc)\s*\([^)]*\)\s*;"
            r"\s*\n\s*(?!\s*if\s*\(\s*\w+\s*[!=]=\s*NULL)"
        ],
    ),
    UniversalRule(
        id="CC012",
        language="c",
        severity="warning",
        name="null-ptr-arithmetic",
        description="Arithmetic on potentially NULL pointer without prior check",
        patterns=[r"\b(?:malloc|calloc)\s*\([^)]*\);\s*\n[^{]*\+\s*\d+"],
    ),
    # ── Security (Format String / Unsafe) ─────────────────────────────────
    UniversalRule(
        id="CC013",
        language="c",
        severity="error",
        name="printf-format-string-var",
        description="printf with non-literal format string is a format string vulnerability",
        patterns=[r"\bprintf\s*\(\s*\w+\s*[,)]"],
    ),
    UniversalRule(
        id="CC014",
        language="c",
        severity="warning",
        name="scanf-no-width",
        description="scanf %s without width limit risks buffer overflow",
        patterns=[r"\bscanf\s*\([^)]*%[^0-9*]*s"],
    ),
    UniversalRule(
        id="CC015",
        language="c",
        severity="warning",
        name="system-call",
        description="system() executes shell commands; potential command injection risk",
        patterns=[r"\bsystem\s*\("],
    ),
    UniversalRule(
        id="CC016",
        language="c",
        severity="warning",
        name="atoi-no-validation",
        description="atoi() does not report errors; use strtol() with validation",
        patterns=[r"\batoi\s*\("],
    ),
    # ── Best Practices ────────────────────────────────────────────────────
    UniversalRule(
        id="CC017",
        language="c",
        severity="warning",
        name="goto-usage",
        description="goto usage; consider structured control flow alternatives",
        patterns=[r"\bgoto\s+\w+\s*;"],
    ),
    UniversalRule(
        id="CC018",
        language="c",
        severity="info",
        name="magic-number",
        description="Magic number in code; use #define or const for named constants",
        patterns=[r"(?<!=\s)(?<!\w)\d{4,}(?!\w)(?!.*#define)"],
    ),
    UniversalRule(
        id="CC019",
        language="c",
        severity="warning",
        name="missing-braces",
        description="Single-statement if/for/while without braces; may cause maintenance bugs",
        patterns=[r"\b(?:if|for|while)\s*\([^)]*\)\s*\n\s*[^{\s]"],
    ),
    UniversalRule(
        id="CC020",
        language="c",
        severity="warning",
        name="implicit-fallthrough",
        description="Switch case without break may fall through unintentionally",
        patterns=[r"case\s+[^:]+:(?:\s*\n\s*[^}b])*\n\s*case\s"],
    ),
    # ── Header Issues ─────────────────────────────────────────────────────
    UniversalRule(
        id="CC021",
        language="c",
        severity="warning",
        name="missing-include-guard",
        description="Header file without include guard or #pragma once",
        patterns=[r"^(?!.*#(?:ifndef|pragma\s+once)).*\.h"],
    ),
    UniversalRule(
        id="CC022",
        language="c",
        severity="info",
        name="include-after-code",
        description="#include after non-preprocessor code; includes should be at file top",
        patterns=[r"(?:^\s*\w+.*;\s*\n)(?:.*\n)*?^\s*#include\s"],
    ),
    # ── Resource Management ───────────────────────────────────────────────
    UniversalRule(
        id="CC023",
        language="c",
        severity="warning",
        name="fopen-without-fclose",
        description="fopen() without corresponding fclose(); potential resource leak",
        patterns=[r"\bfopen\s*\([^)]*\)\s*;(?:(?!fclose).)*$"],
    ),
    UniversalRule(
        id="CC024",
        language="c",
        severity="warning",
        name="memory-leak-no-free",
        description="malloc/calloc in function without corresponding free(); possible leak",
        patterns=[
            r"\b(?:malloc|calloc)\s*\([^)]*\)\s*;"
            r"(?:(?!\bfree\b).)*\breturn\b"
        ],
    ),
    UniversalRule(
        id="CC025",
        language="c",
        severity="warning",
        name="return-local-address",
        description="Returning address of local variable is undefined behavior",
        patterns=[r"\breturn\s+&\w+\s*;"],
    ),
    # ── Integer & Arithmetic ──────────────────────────────────────────────
    UniversalRule(
        id="CC026",
        language="c",
        severity="warning",
        name="integer-overflow-risk",
        description="Arithmetic on int without overflow check before allocation",
        patterns=[r"\b(?:malloc|calloc)\s*\(\s*\w+\s*\*\s*\w+"],
    ),
    UniversalRule(
        id="CC027",
        language="c",
        severity="warning",
        name="signed-unsigned-compare",
        description="Comparison between signed and unsigned may produce unexpected results",
        patterns=[r"(?:unsigned|size_t)\s+\w+.*[<>=]+.*(?:int|long)\s+\w+"],
    ),
    # ── Additional Safety ─────────────────────────────────────────────────
    UniversalRule(
        id="CC028",
        language="c",
        severity="warning",
        name="sizeof-pointer-misuse",
        description="sizeof on pointer returns pointer size, not array/buffer size",
        patterns=[r"\bsizeof\s*\(\s*\w+\s*\)\s*/\s*sizeof\s*\(\s*\*\w+"],
    ),
    UniversalRule(
        id="CC029",
        language="c",
        severity="info",
        name="assignment-in-condition",
        description="Assignment inside if/while condition; may be unintentional",
        patterns=[r"\b(?:if|while)\s*\([^)]*(?<![!=<>])=[^=][^)]*\)"],
    ),
    UniversalRule(
        id="CC030",
        language="c",
        severity="warning",
        name="void-pointer-arithmetic",
        description="Arithmetic on void pointer is undefined behavior in standard C",
        patterns=[r"\bvoid\s*\*\s*\w+.*[+\-]\s*\d+"],
    ),
]
