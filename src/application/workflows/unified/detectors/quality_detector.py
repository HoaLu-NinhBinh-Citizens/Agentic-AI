"""Quality Detector — code quality and style issue detection.

Detects code quality issues based on RuleEngine patterns:
- QUAL001: Long functions
- QUAL002: Nested callbacks
- QUAL003: Broad exception handling
- QUAL004: Empty except blocks
- QUAL005: Unresolved TODO/FIXME
- QUAL006: Print statements instead of logging
- QUAL007: Magic numbers
- QUAL008: Consecutive blank lines
- QUAL009: Trailing whitespace
- QUAL010: High cyclomatic complexity

These rules focus on maintainability and code readability.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from src.application.workflows.unified.code_context import CodeContext
from src.application.workflows.unified.detector_base import (
    Detector,
    DetectorConfig,
    Finding,
    FindingSeverity,
)

# ─── Constants ─────────────────────────────────────────────────────────────────


MAX_FUNCTION_LINES: int = 50
MAX_NESTING_DEPTH: int = 3
MAX_CYCLOMATIC_COMPLEXITY: int = 10
ALLOWED_SINGLE_LETTERS: frozenset[str] = frozenset({"i", "j", "k", "x", "y", "z", "n", "m"})


# ─── Quality Rule Definitions ──────────────────────────────────────────────────


@dataclass
class QualityRule:
    """Definition of a quality detection rule."""
    id: str
    name: str
    description: str
    severity: FindingSeverity
    patterns: list[str] | None = None
    languages: list[str] | None = None
    fix_template: str = ""

    def __post_init__(self) -> None:
        if self.languages is None:
            self.languages = ["python", "javascript", "typescript", "c", "cpp", "java", "go", "rust"]


# ─── Quality Detector ────────────────────────────────────────────────────────────


class QualityDetector(Detector):
    """Code quality detector.

    Detects code quality and style issues:
    - Function complexity and length
    - Error handling patterns
    - Code style violations
    - Documentation issues

    Supported languages: python, javascript, typescript, c, cpp, java, go, rust

    Usage:
        config = DetectorConfig(focus_areas=["quality"])
        detector = QualityDetector(config)
        findings = detector.detect(context)
    """

    RULES: list[QualityRule] = []

    def __init__(self, config: DetectorConfig | None = None) -> None:
        super().__init__(config)
        self._name = "quality"
        self._init_rules()

    def _init_rules(self) -> None:
        """Initialize quality rules."""
        self.RULES = [
            QualityRule(
                id="QUAL001",
                name="long-function",
                description=f"Function exceeds {MAX_FUNCTION_LINES} lines",
                severity=FindingSeverity.WARNING,
                fix_template=f"Extract to smaller functions (target: <{MAX_FUNCTION_LINES} lines)",
            ),
            QualityRule(
                id="QUAL002",
                name="nested-callbacks",
                description="Callback/Promise nesting exceeds 3 levels",
                severity=FindingSeverity.WARNING,
                languages=["javascript", "typescript", "python"],
                fix_template="Use async/await or extract to named functions",
            ),
            QualityRule(
                id="QUAL003",
                name="broad-except",
                description="Bare except or except Exception catches everything",
                severity=FindingSeverity.WARNING,
                languages=["python"],
                patterns=[
                    r"except\s*:\s*\n",
                    r"except\s+Exception\s*:\s*\n",
                ],
                fix_template="Catch specific exceptions: except ValueError as e:",
            ),
            QualityRule(
                id="QUAL004",
                name="empty-except",
                description="Empty except block without logging",
                severity=FindingSeverity.WARNING,
                languages=["python"],
                patterns=[
                    r"except\s*:\s*\n\s*pass",
                    r"except\s+\w+\s*:\s*\n\s*pass",
                    r"except\s+\w+\s+as\s+\w+:\s*\n\s*pass",
                ],
                fix_template="Add logging or re-raise the exception",
            ),
            QualityRule(
                id="QUAL005",
                name="todo-fixme",
                description="Unresolved TODO/FIXME/XXX comment found",
                severity=FindingSeverity.INFO,
                patterns=[
                    r"\bTODO\b",
                    r"\bFIXME\b",
                    r"\bXXX\b",
                    r"\bHACK\b",
                    r"\bBUG\b",
                    r"\bNOTE:.*(?:fix|todo|hack)",
                ],
                fix_template="Resolve the TODO/FIXME or create tracking issue",
            ),
            QualityRule(
                id="QUAL006",
                name="print-statement",
                description="Print statement used instead of logging",
                severity=FindingSeverity.INFO,
                languages=["python"],
                patterns=[r"\bprint\s*\("],
                fix_template="Use logging module: logging.info(), logging.debug()",
            ),
            QualityRule(
                id="QUAL007",
                name="magic-number",
                description="Magic number detected (literal number > 1 not in constant)",
                severity=FindingSeverity.INFO,
                patterns=[
                    r"(?<![a-zA-Z_])(0x[0-9A-Fa-f]+|(?:[2-9]|[1-9]\d+))\b(?![xXa-zA-Z0-9_.\-%])",
                ],
                fix_template="Define as constant: BUFFER_SIZE = 4096",
            ),
            QualityRule(
                id="QUAL008",
                name="consecutive-blank-lines",
                description="Multiple consecutive blank lines detected",
                severity=FindingSeverity.INFO,
                patterns=[r"\n\n\n\n+"],
                fix_template="Use single blank line between sections",
            ),
            QualityRule(
                id="QUAL009",
                name="trailing-whitespace",
                description="Lines with trailing whitespace",
                severity=FindingSeverity.INFO,
                patterns=[r"[ \t]+\n"],
                fix_template="Remove trailing whitespace",
            ),
            QualityRule(
                id="QUAL010",
                name="cyclomatic-complexity",
                description=f"Function cyclomatic complexity exceeds {MAX_CYCLOMATIC_COMPLEXITY}",
                severity=FindingSeverity.WARNING,
                fix_template=f"Simplify function (target complexity <{MAX_CYCLOMATIC_COMPLEXITY})",
            ),
            QualityRule(
                id="QUAL011",
                name="snake-case-function",
                description="Function name should use snake_case",
                severity=FindingSeverity.INFO,
                languages=["python"],
                patterns=[
                    r"def\s+[A-Z][a-zA-Z0-9_]*\s*\(",
                    r"def\s+[a-z_]+[A-Z][a-zA-Z0-9_]*\s*\(",
                ],
                fix_template="Use snake_case: def my_function():",
            ),
            QualityRule(
                id="QUAL012",
                name="pascal-case-class",
                description="Class name should use PascalCase",
                severity=FindingSeverity.INFO,
                languages=["python"],
                patterns=[
                    r"class\s+[a-z][a-z0-9_]*\s*[\(:]",
                    r"class\s+[a-z_]+_[a-z_]*\s*[\(:]",
                ],
                fix_template="Use PascalCase: class MyClass:",
            ),
            QualityRule(
                id="QUAL013",
                name="single-letter-variable",
                description="Avoid single-letter variable names (except common loop vars)",
                severity=FindingSeverity.HINT,
                patterns=[
                    r"\bfor\s+([a-h]|p|t|q|r|s|u|v|w)\b",
                    r"\b([a-h]|p|t|q|r|s|u|v|w)\s*=\s*",
                ],
                fix_template="Use descriptive variable names: count instead of c",
            ),
            QualityRule(
                id="QUAL014",
                name="redundant-comment",
                description="Comment that restates the obvious code",
                severity=FindingSeverity.HINT,
                patterns=[
                    r"#\s*(?:increment|incrementing)\s+\w+\s*by\s+1",
                    r"#\s*(?:decrement|decrementing)\s+\w+\s*by\s+1",
                    r"//\s*(?:increment|incrementing)\s+\w+\s*by\s+1",
                ],
                fix_template="Remove redundant comment",
            ),
            QualityRule(
                id="QUAL015",
                name="import-order",
                description="Imports not in recommended order",
                severity=FindingSeverity.INFO,
                languages=["python"],
                patterns=[
                    r"^import\s+[a-z]",  # standard lib should be before
                ],
                fix_template="Order imports: stdlib, third-party, local",
            ),
        ]

    def detect(self, context: CodeContext) -> list[Finding]:
        """Detect quality issues.

        Args:
            context: Unified code context

        Returns:
            List of quality findings
        """
        findings: list[Finding] = []

        # Run pattern-based rules
        for rule in self.RULES:
            if rule.patterns and context.language in (rule.languages or []):
                rule_findings = self._run_pattern_rule(rule, context)
                findings.extend(rule_findings)

        # Run structure-based rules
        findings.extend(self._detect_long_functions(context))
        findings.extend(self._detect_complex_functions(context))
        findings.extend(self._detect_nested_callbacks(context))

        return findings

    def _run_pattern_rule(self, rule: QualityRule, context: CodeContext) -> list[Finding]:
        """Run a pattern-based quality rule."""
        findings: list[Finding] = []

        if not rule.patterns:
            return findings

        for i, line in enumerate(context.lines, 1):
            for pattern in rule.patterns:
                if re.search(pattern, line, re.MULTILINE):
                    findings.append(Finding(
                        rule_id=rule.id,
                        rule_name=rule.name,
                        severity=rule.severity,
                        file=str(context.file_path),
                        line=i,
                        end_line=i,
                        message=rule.description,
                        fix=rule.fix_template,
                        confidence=0.9,
                        context=context.get_surrounding_code(i),
                        detector=self._name,
                        metadata={"tags": ["quality", "style"]},
                    ))

        return findings

    def _detect_long_functions(self, context: CodeContext) -> list[Finding]:
        """Detect functions exceeding line limit."""
        findings: list[Finding] = []

        for name, def_loc in context.symbol_defs.items():
            if def_loc.symbol_type == "function":
                line_count = def_loc.end_line - def_loc.line + 1
                if line_count > MAX_FUNCTION_LINES:
                    findings.append(Finding(
                        rule_id="QUAL001",
                        rule_name="long-function",
                        severity=FindingSeverity.WARNING,
                        file=str(context.file_path),
                        line=def_loc.line,
                        end_line=def_loc.end_line,
                        column=def_loc.column,
                        message=f"Function '{name}' has {line_count} lines (limit: {MAX_FUNCTION_LINES})",
                        fix=f"Extract to smaller functions (target: <{MAX_FUNCTION_LINES} lines)",
                        confidence=0.95,
                        detector=self._name,
                        metadata={"tags": ["complexity", "refactor"], "line_count": line_count},
                    ))

        return findings

    def _detect_complex_functions(self, context: CodeContext) -> list[Finding]:
        """Detect functions with high cyclomatic complexity."""
        findings: list[Finding] = []

        for name, def_loc in context.symbol_defs.items():
            if def_loc.symbol_type == "function":
                # Estimate complexity from chunks
                chunk = context.get_chunk_at(def_loc.line)
                if chunk:
                    complexity = self._estimate_complexity(chunk, context)
                    if complexity > MAX_CYCLOMATIC_COMPLEXITY:
                        findings.append(Finding(
                            rule_id="QUAL010",
                            rule_name="cyclomatic-complexity",
                            severity=FindingSeverity.WARNING,
                            file=str(context.file_path),
                            line=def_loc.line,
                            end_line=def_loc.end_line,
                            column=def_loc.column,
                            message=f"Function '{name}' has estimated complexity {complexity} (limit: {MAX_CYCLOMATIC_COMPLEXITY})",
                            fix=f"Simplify function (target complexity <{MAX_CYCLOMATIC_COMPLEXITY})",
                            confidence=0.8,
                            detector=self._name,
                            metadata={"tags": ["complexity", "maintainability"], "complexity": complexity},
                        ))

        return findings

    def _detect_nested_callbacks(self, context: CodeContext) -> list[Finding]:
        """Detect deeply nested callbacks/promises."""
        findings: list[Finding] = []

        nesting_level = 0
        max_nesting = 0
        start_line = 0

        for i, line in enumerate(context.lines, 1):
            # Count increase in nesting
            new_nesting = nesting_level
            new_nesting += line.count(".then(") + line.count("await ")
            new_nesting += line.count("async def ") + line.count("def ")

            if new_nesting > nesting_level and ".then(" in line:
                if max_nesting == 0:
                    start_line = i
                max_nesting += 1

            nesting_level = new_nesting

            if ".then(" in line and i > 0:
                # Check for deep nesting
                prev_lines = "\n".join(context.lines[max(0, i-10):i])
                nested_then_count = prev_lines.count(".then(")
                if nested_then_count >= 3:
                    findings.append(Finding(
                        rule_id="QUAL002",
                        rule_name="nested-callbacks",
                        severity=FindingSeverity.WARNING,
                        file=str(context.file_path),
                        line=i,
                        end_line=i,
                        message=f"Promise nesting exceeds 3 levels ({nested_then_count} .then calls)",
                        fix="Use async/await or extract to named functions",
                        confidence=0.85,
                        detector=self._name,
                        metadata={"tags": ["async", "complexity"]},
                    ))

        return findings

    def _estimate_complexity(self, chunk: CodeContext, context: Any) -> int:
        """Estimate cyclomatic complexity from code chunk.

        Complexity = 1 + (number of decision points)
        Decision points: if, elif, else, for, while, except, and, or
        """
        start = max(0, chunk.start_line - 1)
        end = min(len(context.lines), chunk.end_line)
        body = "\n".join(context.lines[start:end])

        # Count decision points
        decision_keywords = [
            r"\bif\b", r"\belif\b", r"\bfor\b", r"\bwhile\b",
            r"\bexcept\b", r"\band\b", r"\bor\b",
            r"\?\s*", r"case\s+",
        ]

        complexity = 1
        for keyword in decision_keywords:
            complexity += len(re.findall(keyword, body, re.MULTILINE))

        return complexity

    def integrate_with_rule_engine(self, rule_engine: Any) -> None:
        """Integrate with RuleEngine to share findings.

        Args:
            rule_engine: Existing RuleEngine instance
        """
        from src.infrastructure.analysis.rule_engine import Rule, RuleSeverity

        for quality_rule in self.RULES:
            rule = Rule(
                id=quality_rule.id,
                name=quality_rule.name,
                description=quality_rule.description,
                severity=RuleSeverity[quality_rule.severity.name.upper()],
                languages=quality_rule.languages or [],
                patterns=quality_rule.patterns or [],
                fix_template=quality_rule.fix_template,
                tags=["quality"],
            )
            try:
                rule_engine.register(rule)
            except ValueError:
                pass  # Rule already registered
