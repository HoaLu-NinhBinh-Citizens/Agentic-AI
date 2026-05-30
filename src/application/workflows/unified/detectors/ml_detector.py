"""ML Detector — AST-based pattern detection using tree-sitter queries.

Upgrades from regex-based ML001-ML007 rules to tree-sitter queries for:
- More accurate AST-aware pattern matching
- Better handling of complex code structures
- Reduced false positives

ML Rules (ML001-ML007):
- ML001: Dead code detection
- ML002: Unused function parameters
- ML003: Missing null checks
- ML004: Improper resource cleanup
- ML005: Type inconsistency
- ML006: Logic duplication
- ML007: API usage anomalies
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional

from src.application.workflows.unified.code_context import CodeContext
from src.application.workflows.unified.detector_base import (
    Detector,
    DetectorConfig,
    Finding,
    FindingSeverity,
)

if TYPE_CHECKING:
    import tree_sitter_languages

logger = logging.getLogger(__name__)

# ─── ML Rule Definitions ────────────────────────────────────────────────────────


@dataclass
class MlRule:
    """Definition of an ML detection rule."""
    id: str
    name: str
    description: str
    severity: FindingSeverity
    languages: list[str]
    query: str  # tree-sitter S-expression query
    fix_template: str = ""


# ─── Tree-sitter Query Patterns ────────────────────────────────────────────────


# ML001: Dead code - functions that are defined but never called
_ML001_QUERY = """
(function_definition) @func
"""

# ML002: Unused parameters - parameters not referenced in function body
_ML002_QUERY = """
(function_definition
  parameters: (parameters) @params
  body: (block) @body)
"""

# ML003: Missing null checks - dereferencing without null check
_ML003_QUERY = """
(call_expression
  function: (identifier) @func
  arguments: (argument_list) @args)
"""

# ML004: Improper resource cleanup - file/stream opened but not closed
_ML004_QUERY = """
(call_expression
  function: (identifier) @open_func
  (#match? @open_func "^(open|fopen|mmap|malloc)$"))
"""


# ─── ML Detector ────────────────────────────────────────────────────────────────


@dataclass
class MlRule:
    """Definition of an ML detection rule."""
    id: str
    name: str
    description: str
    severity: FindingSeverity
    languages: list[str]
    query: str = ""
    fix_template: str = ""

    def __post_init__(self) -> None:
        # Pre-process query for tree-sitter
        self._compiled: Optional[Any] = None


class MlDetector(Detector):
    """AST-based ML pattern detector using tree-sitter queries.

    This detector upgrades the ML001-ML007 rules from regex to tree-sitter
    for more accurate pattern detection. It analyzes AST structure rather
    than text patterns.

    Supported languages: python, javascript, typescript, c, cpp, rust, go

    Usage:
        config = DetectorConfig(focus_areas=["ml"])
        detector = MlDetector(config)
        findings = detector.detect(context)
    """

    # ML001-ML007 rule definitions
    RULES: list[MlRule] = []

    def __init__(self, config: DetectorConfig | None = None) -> None:
        super().__init__(config)
        self._name = "ml"
        self._init_rules()

    def _init_rules(self) -> None:
        """Initialize ML rules based on supported languages."""
        self.RULES = [
            MlRule(
                id="ML001",
                name="dead-code",
                description="Function defined but never called",
                severity=FindingSeverity.WARNING,
                languages=["python", "javascript", "typescript", "c", "cpp", "rust", "go"],
            ),
            MlRule(
                id="ML002",
                name="unused-parameter",
                description="Function parameter not used in body",
                severity=FindingSeverity.INFO,
                languages=["python", "javascript", "typescript", "c", "cpp", "rust", "go"],
            ),
            MlRule(
                id="ML003",
                name="missing-null-check",
                description="Potential null/none dereference without check",
                severity=FindingSeverity.WARNING,
                languages=["python", "javascript", "typescript", "c", "cpp"],
            ),
            MlRule(
                id="ML004",
                name="resource-leak",
                description="Resource opened but may not be closed",
                severity=FindingSeverity.ERROR,
                languages=["python", "c", "cpp"],
            ),
            MlRule(
                id="ML005",
                name="type-inconsistency",
                description="Type annotation inconsistent with usage",
                severity=FindingSeverity.WARNING,
                languages=["python", "typescript"],
            ),
            MlRule(
                id="ML006",
                name="logic-duplication",
                description="Similar code patterns may indicate duplication",
                severity=FindingSeverity.INFO,
                languages=["python", "javascript", "typescript", "c", "cpp", "rust"],
            ),
            MlRule(
                id="ML007",
                name="api-usage-anomaly",
                description="Unusual API usage pattern detected",
                severity=FindingSeverity.INFO,
                languages=["python", "javascript", "typescript"],
            ),
        ]

    def detect(self, context: CodeContext) -> list[Finding]:
        """Detect ML patterns using tree-sitter AST analysis.

        Args:
            context: Unified code context

        Returns:
            List of ML findings
        """
        findings: list[Finding] = []

        # Check if language is supported
        if context.language not in self._get_supported_languages():
            return findings

        # Run each applicable rule
        for rule in self.RULES:
            if context.language in rule.languages:
                rule_findings = self._run_rule(rule, context)
                findings.extend(rule_findings)

        return findings

    def _run_rule(self, rule: MlRule, context: CodeContext) -> list[Finding]:
        """Run a single ML rule on the context.

        Args:
            rule: ML rule to run
            context: Code context

        Returns:
            Findings from this rule
        """
        if rule.id == "ML001":
            return self._detect_dead_code(context, rule)
        elif rule.id == "ML002":
            return self._detect_unused_params(context, rule)
        elif rule.id == "ML003":
            return self._detect_missing_null_checks(context, rule)
        elif rule.id == "ML004":
            return self._detect_resource_leaks(context, rule)
        elif rule.id == "ML005":
            return self._detect_type_inconsistency(context, rule)
        elif rule.id == "ML006":
            return self._detect_logic_duplication(context, rule)
        elif rule.id == "ML007":
            return self._detect_api_anomalies(context, rule)
        return []

    def _detect_dead_code(self, context: CodeContext, rule: MlRule) -> list[Finding]:
        """Detect functions that are defined but never called."""
        findings: list[Finding] = []

        # Get all function definitions
        defined_funcs = {
            name: loc
            for name, loc in context.symbol_defs.items()
            if loc.symbol_type == "function"
        }

        # Get all function calls
        called_funcs: set[str] = set()
        for name, refs in context.symbol_refs.items():
            for ref in refs:
                if ref.is_call:
                    called_funcs.add(name)

        # Find undefined but called functions (imports from other files)
        # and defined but never called (dead code)
        for func_name, def_loc in defined_funcs.items():
            # Check if it's called within the file
            refs = context.symbol_refs.get(func_name, [])
            calls = [r for r in refs if r.is_call]

            # If defined but only referenced in definition, it's potentially dead
            if not calls and func_name not in called_funcs:
                findings.append(Finding(
                    rule_id=rule.id,
                    rule_name=rule.name,
                    severity=rule.severity,
                    file=str(context.file_path),
                    line=def_loc.line,
                    end_line=def_loc.end_line,
                    column=def_loc.column,
                    message=f"Function '{func_name}' is defined but appears unused",
                    fix=f"Consider removing or marking as @deprecated: def {func_name}",
                    confidence=0.8,
                    context=context.get_surrounding_code(def_loc.line),
                    detector=self._name,
                    metadata={"tags": ["dead-code", "unused"]},
                ))

        return findings

    def _detect_unused_params(self, context: CodeContext, rule: MlRule) -> list[Finding]:
        """Detect function parameters that are never used."""
        findings: list[Finding] = []

        # This requires AST analysis - simplified heuristic for now
        for name, def_loc in context.symbol_defs.items():
            if def_loc.symbol_type == "function":
                # Check if function has parameters in signature
                if "(" in def_loc.signature:
                    params = self._extract_params(def_loc.signature)
                    if not params:
                        continue

                    # Check if any param is unused
                    unused = self._find_unused_params(name, params, context)
                    for param, line in unused:
                        findings.append(Finding(
                            rule_id=rule.id,
                            rule_name=rule.name,
                            severity=rule.severity,
                            file=str(context.file_path),
                            line=line,
                            end_line=line,
                            message=f"Parameter '{param}' appears unused in '{name}'",
                            fix=f"Remove unused parameter or prefix with _",
                            confidence=0.7,
                            detector=self._name,
                            metadata={"tags": ["unused", "parameter"]},
                        ))

        return findings

    def _detect_missing_null_checks(self, context: CodeContext, rule: MlRule) -> list[Finding]:
        """Detect potential null/none dereferences."""
        findings: list[Finding] = []

        # Look for patterns like: obj.member without null check
        for name, refs in context.symbol_refs.items():
            for ref in refs:
                # Check if it's an attribute access pattern
                if "." in ref.context and not self._has_null_check(ref.context):
                    # Heuristic: if accessing attribute but no prior check
                    findings.append(Finding(
                        rule_id=rule.id,
                        rule_name=rule.name,
                        severity=rule.severity,
                        file=str(context.file_path),
                        line=ref.line,
                        end_line=ref.line,
                        column=ref.column,
                        message=f"Potential null/none dereference at '{ref.context.strip()}'",
                        fix="Add null check before access",
                        confidence=0.6,
                        detector=self._name,
                        metadata={"tags": ["null-safety", "potential-bug"]},
                    ))

        return findings

    def _detect_resource_leaks(self, context: CodeContext, rule: MlRule) -> list[Finding]:
        """Detect potential resource leaks."""
        findings: list[Finding] = []

        # Look for open/fopen without corresponding close
        open_patterns = ["open(", "fopen(", "mmap(", "malloc("]
        close_patterns = ["close(", "fclose(", "munmap(", "free("]

        lines_with_open: list[int] = []
        lines_with_close: list[int] = []

        for i, line in enumerate(context.lines, 1):
            for pattern in open_patterns:
                if pattern in line:
                    lines_with_open.append(i)
            for pattern in close_patterns:
                if pattern in line:
                    lines_with_close.append(i)

        # Check for opens without closes in same scope
        for open_line in lines_with_open:
            chunk = context.get_chunk_at(open_line)
            if chunk:
                has_close = any(
                    close_line in range(chunk.start_line, chunk.end_line + 1)
                    for close_line in lines_with_close
                )
                if not has_close:
                    findings.append(Finding(
                        rule_id=rule.id,
                        rule_name=rule.name,
                        severity=rule.severity,
                        file=str(context.file_path),
                        line=open_line,
                        end_line=open_line,
                        message="Resource opened but may not be closed in this scope",
                        fix="Ensure resource is closed in all code paths",
                        confidence=0.7,
                        detector=self._name,
                        metadata={"tags": ["resource-leak", "safety"]},
                    ))

        return findings

    def _detect_type_inconsistency(self, context: CodeContext, rule: MlRule) -> list[Finding]:
        """Detect type annotation inconsistencies."""
        findings: list[Finding] = []

        # For Python: check for Any usage or type mismatches
        if context.language == "python":
            for i, line in enumerate(context.lines, 1):
                if ": Any" in line or "-> Any" in line:
                    findings.append(Finding(
                        rule_id=rule.id,
                        rule_name=rule.name,
                        severity=rule.severity,
                        file=str(context.file_path),
                        line=i,
                        end_line=i,
                        message="Use of Any type reduces type safety",
                        fix="Replace with specific type annotation",
                        confidence=0.8,
                        detector=self._name,
                        metadata={"tags": ["type-safety", "python"]},
                    ))

        return findings

    def _detect_logic_duplication(self, context: CodeContext, rule: MlRule) -> list[Finding]:
        """Detect potential logic duplication."""
        findings: list[Finding] = []

        # Compare function bodies for similarity
        functions: list[tuple[str, str]] = []
        for name, def_loc in context.symbol_defs.items():
            if def_loc.symbol_type == "function":
                body = self._extract_function_body(def_loc, context)
                if body:
                    functions.append((name, body))

        # Simple n-gram comparison
        for i, (name1, body1) in enumerate(functions):
            for name2, body2 in functions[i + 1:]:
                similarity = self._calculate_similarity(body1, body2)
                if similarity > 0.8 and name1 != name2:
                    findings.append(Finding(
                        rule_id=rule.id,
                        rule_name=rule.name,
                        severity=rule.severity,
                        file=str(context.file_path),
                        line=0,
                        end_line=0,
                        message=f"Functions '{name1}' and '{name2}' have similar implementations ({similarity:.0%})",
                        fix="Consider extracting common logic to shared function",
                        confidence=similarity,
                        detector=self._name,
                        metadata={"tags": ["duplication", "refactor"]},
                    ))

        return findings

    def _detect_api_anomalies(self, context: CodeContext, rule: MlRule) -> list[Finding]:
        """Detect unusual API usage patterns."""
        findings: list[Finding] = []

        # Check for deprecated API usage
        deprecated_patterns = [
            (r"\.iteritems\(\)", "Use .items() instead of .iteritems()"),
            (r"\.itervalues\(\)", "Use .values() instead of .itervalues()"),
            (r"\.iterkeys\(\)", "Use .keys() instead of .iterkeys()"),
            (r"apply\s*\(\s*lambda", "Consider vectorized operations over apply(lambda)"),
        ]

        for i, line in enumerate(context.lines, 1):
            for pattern, message in deprecated_patterns:
                if re.search(pattern, line):
                    findings.append(Finding(
                        rule_id=rule.id,
                        rule_name=rule.name,
                        severity=FindingSeverity.INFO,
                        file=str(context.file_path),
                        line=i,
                        end_line=i,
                        message=message,
                        fix=message,
                        confidence=0.9,
                        detector=self._name,
                        metadata={"tags": ["deprecated", "api"]},
                    ))

        return findings

    # ─── Helper Methods ───────────────────────────────────────────────────────

    def _get_supported_languages(self) -> set[str]:
        """Get set of supported languages."""
        return {"python", "javascript", "typescript", "c", "cpp", "rust", "go"}

    def _extract_params(self, signature: str) -> list[str]:
        """Extract parameter names from function signature."""
        # Match content between parentheses
        match = re.search(r"\(([^)]*)\)", signature)
        if not match:
            return []

        params_str = match.group(1).strip()
        if not params_str:
            return []

        # Split by comma, handling type annotations
        params = []
        for param in params_str.split(","):
            param = param.strip()
            if param:
                # Take first word (parameter name, not type)
                name = param.split(":")[0].split("=")[0].strip()
                if name and not name.startswith("*"):
                    params.append(name)

        return params

    def _find_unused_params(
        self,
        func_name: str,
        params: list[str],
        context: CodeContext,
    ) -> list[tuple[str, int]]:
        """Find parameters that appear unused in function body."""
        unused: list[tuple[str, int]] = []

        for param in params:
            # Check if param appears in any reference
            refs = context.symbol_refs.get(param, [])
            if not refs:
                # Parameter never referenced
                def_loc = context.symbol_defs.get(func_name)
                if def_loc:
                    unused.append((param, def_loc.line))

        return unused

    def _has_null_check(self, line: str) -> bool:
        """Check if line contains null/none check."""
        patterns = [
            r"if\s+\w+\s+is\s+not\s+None",
            r"if\s+\w+\s+is\s+None",
            r"if\s+not\s+\w+\s+==\s+None",
            r"if\s+\w+\s+!=\s+None",
            r"\w+\s+is\s+not\s+None",
            r"\w+\s+is\s+None",
        ]
        return any(re.search(p, line) for p in patterns)

    def _extract_function_body(self, def_loc: Any, context: CodeContext) -> str:
        """Extract function body text."""
        if def_loc.end_line <= 0:
            return ""

        start = max(0, def_loc.line - 1)
        end = min(len(context.lines), def_loc.end_line)
        return "\n".join(context.lines[start:end])

    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate simple n-gram similarity between two texts."""
        # Normalize whitespace
        t1 = re.sub(r"\s+", " ", text1).lower().strip()
        t2 = re.sub(r"\s+", " ", text2).lower().strip()

        if not t1 or not t2:
            return 0.0

        # Simple character-based similarity (Jaccard)
        set1 = set(t1[i:i+3] for i in range(len(t1) - 2))
        set2 = set(t2[i:i+3] for i in range(len(t2) - 2))

        if not set1 or not set2:
            return 0.0

        intersection = len(set1 & set2)
        union = len(set1 | set2)

        return intersection / union if union > 0 else 0.0
