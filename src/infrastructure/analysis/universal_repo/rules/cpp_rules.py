"""C++ static analysis rules for the Universal Rule Engine.

Imports all C rules (which apply to C++ code) and adds C++-specific rules
for RAII, smart pointers, modern C++ idioms, and template safety.

Requirements: 3.3, 3.8
"""

from __future__ import annotations

from src.infrastructure.analysis.universal_repo.rule_engine import UniversalRule

from .c_rules import get_rules as get_c_rules


def get_rules() -> list[UniversalRule]:
    """Return all C++ rules (C base + C++-specific, minimum 30 combined)."""
    # Rebind C rules to 'cpp' language
    cpp_base = []
    for rule in get_c_rules():
        cpp_base.append(UniversalRule(
            id=rule.id,
            language="cpp",
            severity=rule.severity,
            name=rule.name,
            description=rule.description,
            patterns=rule.patterns[:],
            ast_query=rule.ast_query,
        ))
    return cpp_base + _CPP_SPECIFIC_RULES[:]


_CPP_SPECIFIC_RULES: list[UniversalRule] = [
    # ── Memory Management / RAII ──────────────────────────────────────────
    UniversalRule(
        id="CPP001",
        language="cpp",
        severity="warning",
        name="raw-new-delete",
        description="Raw new/delete; prefer std::unique_ptr or std::make_unique",
        patterns=[r"\bnew\s+\w+[\s\[({]", r"\bdelete\s+\w+"],
    ),
    UniversalRule(
        id="CPP002",
        language="cpp",
        severity="warning",
        name="new-array-delete-mismatch",
        description="Array allocated with new[] must be freed with delete[], not delete",
        patterns=[r"\bnew\s+\w+\s*\[.*\].*\n(?:.*\n)*?\bdelete\s+(?!\[\])"],
    ),
    UniversalRule(
        id="CPP003",
        language="cpp",
        severity="info",
        name="manual-memory-with-smart-ptr-available",
        description="Manual malloc/free in C++; use std::vector or smart pointers",
        patterns=[r"\b(?:malloc|calloc|free)\s*\("],
    ),
    # ── Modern C++ Idioms ─────────────────────────────────────────────────
    UniversalRule(
        id="CPP004",
        language="cpp",
        severity="info",
        name="c-style-cast",
        description="C-style cast; use static_cast, dynamic_cast, or reinterpret_cast",
        patterns=[r"\(\s*(?:int|float|double|char|long|unsigned|void)\s*\*?\s*\)\s*\w+"],
    ),
    UniversalRule(
        id="CPP005",
        language="cpp",
        severity="info",
        name="null-instead-of-nullptr",
        description="Use nullptr instead of NULL or 0 for null pointer in C++11+",
        patterns=[r"\b(?:NULL|= 0)\s*;.*//.*pointer", r"=\s*NULL\b"],
    ),
    UniversalRule(
        id="CPP006",
        language="cpp",
        severity="info",
        name="prefer-auto",
        description="Consider auto for complex iterator or template types",
        patterns=[r"std::\w+<[^>]+>::(?:iterator|const_iterator)\s+\w+"],
    ),
    UniversalRule(
        id="CPP007",
        language="cpp",
        severity="warning",
        name="missing-override",
        description="Virtual function override missing 'override' keyword",
        patterns=[r"virtual\s+\w+[^;{]*\{"],
    ),
    UniversalRule(
        id="CPP008",
        language="cpp",
        severity="warning",
        name="missing-virtual-destructor",
        description="Base class with virtual methods should have virtual destructor",
        patterns=[r"class\s+\w+[^;]*\{[^}]*virtual\s+\w+[^}]*~(?!.*virtual)"],
    ),
    # ── Exception Safety ──────────────────────────────────────────────────
    UniversalRule(
        id="CPP009",
        language="cpp",
        severity="warning",
        name="throw-in-destructor",
        description="Throwing exceptions in destructors can cause std::terminate",
        patterns=[r"~\w+\s*\([^)]*\)\s*\{[^}]*\bthrow\b"],
    ),
    UniversalRule(
        id="CPP010",
        language="cpp",
        severity="warning",
        name="catch-by-value",
        description="Catch exceptions by const reference to avoid slicing",
        patterns=[r"catch\s*\(\s*(?!const\s)(?!.*&)\w+\s+\w+\s*\)"],
    ),
    UniversalRule(
        id="CPP011",
        language="cpp",
        severity="info",
        name="catch-all-ellipsis",
        description="catch(...) hides error type; prefer catching specific exceptions",
        patterns=[r"catch\s*\(\s*\.\.\.\s*\)"],
    ),
    # ── STL & Container Safety ────────────────────────────────────────────
    UniversalRule(
        id="CPP012",
        language="cpp",
        severity="warning",
        name="vector-subscript-without-check",
        description="operator[] on vector without bounds check; consider .at() for safety",
        patterns=[r"\bvector\s*<[^>]+>\s+\w+[^;]*\[\s*\w+\s*\]"],
    ),
    UniversalRule(
        id="CPP013",
        language="cpp",
        severity="warning",
        name="iterator-invalidation",
        description="Modifying container while iterating may invalidate iterators",
        patterns=[r"for\s*\([^)]*(?:begin|end)\(\)[^)]*\)[^{]*\{[^}]*\.(?:push_back|erase|insert)"],
    ),
    # ── Resource / RAII ───────────────────────────────────────────────────
    UniversalRule(
        id="CPP014",
        language="cpp",
        severity="warning",
        name="fopen-without-fclose",
        description="fopen without corresponding fclose; use RAII wrapper or std::fstream",
        patterns=[r"\bfopen\s*\("],
    ),
    UniversalRule(
        id="CPP015",
        language="cpp",
        severity="warning",
        name="shared-ptr-cycle-risk",
        description="Two shared_ptr members may create reference cycle; use weak_ptr",
        patterns=[r"std::shared_ptr<\w+>\s+\w+.*\n(?:.*\n)*?std::shared_ptr<\w+>\s+\w+"],
    ),
]
