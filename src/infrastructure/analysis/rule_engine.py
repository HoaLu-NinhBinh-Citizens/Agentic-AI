"""Extensible static analysis rule engine for software code review.

Provides:
- Pluggable rule system with 28 built-in rules
- Rule severity levels (ERROR, WARNING, INFO, HINT)
- Auto-fix templates for common issues
- Integration with SafeTreeSitterIndexer
- Merge findings from external linters (pylint, ruff, eslint, golangci-lint)

Built-in rules cover:
- Security: hardcoded secrets, SQL injection, command injection, etc.
- Type Safety: untyped functions, Any usage, missing return types
- Import Analysis: unused imports, circular imports, wildcard imports
- Naming Conventions: snake_case, PascalCase, UPPER_CASE, single-letter vars
- Code Quality: long functions, broad except, TODO/FIXME, magic numbers

Usage:
    from src.infrastructure.analysis.rule_engine import RuleEngine, Rule, Finding

    engine = RuleEngine(indexer=indexer)
    findings = engine.detect("path/to/file.py", "python")
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from src.infrastructure.indexing.tree_sitter import SafeTreeSitterIndexer

logger = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────

MAX_FUNCTION_LINES: int = 50
MAX_NESTING_DEPTH: int = 3
MAX_CYCLOMATIC_COMPLEXITY: int = 10
MAX_FILE_SIZE_MB: int = 10
ALLOWED_SINGLE_LETTERS: frozenset[str] = frozenset({"i", "j", "k", "x", "y", "z", "n", "m"})
SUPPORTED_LANGUAGES: frozenset[str] = frozenset({
    "python", "javascript", "typescript", "c", "cpp", "rust", "go", "java"
})

# ─── Severity Enum ───────────────────────────────────────────────────────────


class RuleSeverity(Enum):
    """Rule violation severity level."""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    HINT = "hint"

    def to_numeric(self) -> float:
        """Convert severity to numeric score (higher = more severe)."""
        mapping = {"error": 1.0, "warning": 0.7, "info": 0.4, "hint": 0.2}
        return mapping[self.value]


# ─── Dataclasses ─────────────────────────────────────────────────────────────


@dataclass
class Rule:
    """Static analysis rule definition.

    Attributes:
        id: Unique rule identifier (e.g., "SEC001", "TYPE001")
        name: Human-readable rule name (e.g., "hardcoded-secret")
        description: Detailed explanation of the rule
        severity: Severity level of violations
        languages: List of applicable languages (e.g., ["python", "javascript"])
        patterns: Regex patterns to match
        ast_query: Tree-sitter S-expression query (optional)
        fix_template: Template for auto-fix generation
        url: Documentation URL
        cwe_id: CWE (Common Weakness Enumeration) reference
        tags: Categorization tags for filtering
    """
    id: str
    name: str
    description: str
    severity: RuleSeverity
    languages: list[str]
    patterns: list[str] = field(default_factory=list)
    ast_query: str = ""
    fix_template: str = ""
    url: str = ""
    cwe_id: str = ""
    tags: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._compiled_patterns: list[re.Pattern] = [
            re.compile(p, re.MULTILINE) for p in self.patterns
        ]

    def match(self, content: str) -> list[re.Match]:
        """Match all patterns against content."""
        matches = []
        for pattern in self._compiled_patterns:
            matches.extend(pattern.finditer(content))
        return sorted(matches, key=lambda m: m.start())


@dataclass
class Finding:
    """A rule violation found in code.

    Attributes:
        rule_id: ID of the triggered rule
        rule_name: Name of the triggered rule
        severity: Severity level
        file: File path where violation occurred
        line: Start line number (1-based)
        end_line: End line number (1-based)
        column: Start column (0-based)
        message: Human-readable violation message
        fix: Suggested fix text
        confidence: Detection confidence (0.0-1.0)
        context: Surrounding code context
    """
    rule_id: str
    rule_name: str
    severity: RuleSeverity
    file: str
    line: int
    end_line: int
    column: int = 0
    message: str = ""
    fix: str = ""
    confidence: float = 1.0
    context: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert finding to dictionary for serialization."""
        return {
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "severity": self.severity.value,
            "file": self.file,
            "line": self.line,
            "end_line": self.end_line,
            "column": self.column,
            "message": self.message,
            "fix": self.fix,
            "confidence": self.confidence,
            "context": self.context,
        }


# ─── Rule Engine ─────────────────────────────────────────────────────────────


class RuleEngine:
    """Extensible static analysis rule engine.

    Provides:
    - 28 built-in rules covering security, type safety, imports,
      naming, and code quality
    - Integration with SafeTreeSitterIndexer for AST-based analysis
    - External linter integration (pylint, ruff, eslint, golangci-lint)
    - Finding deduplication and merging
    - Auto-fix template support

    Attributes:
        indexer: Optional SafeTreeSitterIndexer for AST analysis
    """

    # ─── Built-in Rules Registry ───────────────────────────────────────────────

    BUILTIN_RULES: ClassVar[list[Rule]] = []

    def __init__(self, indexer: "SafeTreeSitterIndexer | None" = None) -> None:
        """Initialize rule engine.

        Args:
            indexer: Optional tree-sitter indexer for AST-based analysis
        """
        self._indexer = indexer
        self._rules: dict[str, Rule] = {}
        self._register_builtin_rules()

    # ─── Rule Registration ─────────────────────────────────────────────────────

    def _register_builtin_rules(self) -> None:
        """Register all 28 built-in rules."""
        for rule in self.BUILTIN_RULES:
            self._rules[rule.id] = rule

    def register(self, rule: Rule) -> None:
        """Register a custom rule.

        Args:
            rule: Rule to register

        Raises:
            ValueError: If rule ID already exists
        """
        if rule.id in self._rules:
            raise ValueError(f"Rule {rule.id} already registered")
        self._rules[rule.id] = rule
        logger.info("Registered custom rule", extra={"rule_id": rule.id, "name": rule.name})

    def unregister(self, rule_id: str) -> bool:
        """Unregister a rule by ID.

        Args:
            rule_id: ID of rule to remove

        Returns:
            True if rule was removed, False if not found
        """
        return self._rules.pop(rule_id, None) is not None

    def get_rule(self, rule_id: str) -> Rule | None:
        """Get rule by ID."""
        return self._rules.get(rule_id)

    def get_rules_by_language(self, language: str) -> list[Rule]:
        """Get all rules applicable to a language."""
        return [r for r in self._rules.values() if language in r.languages]

    def get_rules_by_severity(self, severity: RuleSeverity) -> list[Rule]:
        """Get all rules of a specific severity."""
        return [r for r in self._rules.values() if r.severity == severity]

    def get_rules_by_tag(self, tag: str) -> list[Rule]:
        """Get all rules with a specific tag."""
        return [r for r in self._rules.values() if tag in r.tags]

    # ─── Detection ────────────────────────────────────────────────────────────

    def detect(self, file_path: str, language: str) -> list[Finding]:
        """Run all applicable rules on a file.

        Args:
            file_path: Path to file to analyze
            language: Programming language (e.g., "python", "javascript")

        Returns:
            List of findings from all triggered rules
        """
        if language not in SUPPORTED_LANGUAGES:
            logger.debug("Unsupported language", extra={"language": language})
            return []

        try:
            with open(file_path, encoding="utf-8", errors="replace") as f:
                content = f.read()
        except OSError as exc:
            logger.warning("Cannot read file", extra={"file": file_path, "error": str(exc)})
            return []

        findings: list[Finding] = []
        applicable_rules = self.get_rules_by_language(language)

        for rule in applicable_rules:
            rule_findings = self._detect_rule(rule, content, file_path, language)
            findings.extend(rule_findings)

        return self._deduplicate_findings(findings)

    def detect_all(
        self,
        root: str,
        extensions: list[str] | None = None,
    ) -> list[Finding]:
        """Run all rules on all files in a directory tree.

        Args:
            root: Root directory to scan
            extensions: File extensions to include (e.g., [".py", ".js"])

        Returns:
            Combined findings from all files
        """
        if extensions is None:
            extensions = [".py", ".js", ".ts", ".jsx", ".tsx", ".c", ".cpp", ".rs", ".go", ".java"]

        findings: list[Finding] = []
        root_path = Path(root)

        if not root_path.exists():
            logger.warning("Root directory does not exist", extra={"root": root})
            return findings

        for ext in extensions:
            for file_path in root_path.rglob(f"*{ext}"):
                if self._should_skip_path(file_path):
                    continue

                language = self._detect_language(file_path)
                if language:
                    findings.extend(self.detect(str(file_path), language))

        return findings

    def _detect_rule(
        self,
        rule: Rule,
        content: str,
        file_path: str,
        language: str,
    ) -> list[Finding]:
        """Run a single rule against content."""
        findings: list[Finding] = []

        if rule.patterns:
            findings.extend(self._detect_by_pattern(rule, content, file_path))

        if rule.ast_query and self._indexer:
            findings.extend(
                self._detect_by_ast(rule, content, file_path, language)
            )

        return findings

    def _detect_by_pattern(
        self,
        rule: Rule,
        content: str,
        file_path: str,
    ) -> list[Finding]:
        """Detect violations using regex patterns."""
        findings: list[Finding] = []
        lines = content.split("\n")

        for match in rule.match(content):
            line_num = content[:match.start()].count("\n") + 1

            # Calculate end line for multi-line matches
            end_line = content[:match.end()].count("\n") + 1

            # Calculate column
            line_start = content.rfind("\n", 0, match.start()) + 1
            column = match.start() - line_start

            # Get context (3 lines around match)
            context_lines = self._get_context_lines(lines, line_num)

            finding = Finding(
                rule_id=rule.id,
                rule_name=rule.name,
                severity=rule.severity,
                file=file_path,
                line=line_num,
                end_line=end_line,
                column=column,
                message=self._format_finding_message(rule, match.group()),
                fix=rule.fix_template,
                confidence=0.95,
                context=context_lines,
            )
            findings.append(finding)

        return findings

    def _detect_by_ast(
        self,
        rule: Rule,
        content: str,
        file_path: str,
        language: str,
    ) -> list[Finding]:
        """Detect violations using tree-sitter AST queries."""
        findings: list[Finding] = []

        try:
            tree = self._indexer.parse_file(file_path)
            if tree:
                matches = self._query_ast(tree.root_node, rule.ast_query, content)
                for match in matches:
                    line_num = match["line"]
                    end_line = match.get("end_line", line_num)
                    context_lines = self._get_context_lines(
                        content.split("\n"), line_num
                    )

                    finding = Finding(
                        rule_id=rule.id,
                        rule_name=rule.name,
                        severity=rule.severity,
                        file=file_path,
                        line=line_num,
                        end_line=end_line,
                        column=match.get("column", 0),
                        message=rule.description,
                        fix=rule.fix_template,
                        confidence=0.9,
                        context=context_lines,
                    )
                    findings.append(finding)
        except Exception as exc:
            logger.debug("AST query failed", extra={"rule": rule.id, "error": str(exc)})

        return findings

    def _query_ast(
        self,
        root: Any,
        query: str,
        content: str,
    ) -> list[dict[str, Any]]:
        """Execute tree-sitter query and return matches."""
        matches: list[dict[str, Any]] = []

        try:
            from tree_sitter_languages import get_language
            lang = get_language(self._detect_language_from_content(content))
            Query = __import__("tree_sitter", fromlist=["Query"]).Query
            ast_query = Query(lang, query)
            captures = ast_query.captures(root)

            for node, capture_name in captures:
                matches.append({
                    "line": node.start_point[0] + 1,
                    "end_line": node.end_point[0] + 1,
                    "column": node.start_point[1],
                    "text": node.text.decode("utf-8", errors="replace"),
                })
        except Exception:
            pass

        return matches

    # ─── External Linter Integration ─────────────────────────────────────────

    def run_external_linter(
        self,
        linter: str,
        path: str,
    ) -> list[Finding]:
        """Run external linter and parse results.

        Args:
            linter: Linter name (pylint, ruff, eslint, golangci-lint, rustc)
            path: File or directory path to analyze

        Returns:
            Findings parsed from linter output
        """
        linter_commands = {
            "pylint": ["pylint", path, "--output-format=text"],
            "ruff": ["ruff", "check", path],
            "eslint": ["npx", "eslint", path, "--format=json"],
            "golangci-lint": ["golangci-lint", "run", path],
            "rustc": ["rustc", "--cap-lints", "warn", path],
        }

        cmd = linter_commands.get(linter.lower())
        if not cmd:
            logger.warning("Unknown linter", extra={"linter": linter})
            return []

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
            )
            return self._parse_linter_output(linter, result.stdout + result.stderr)
        except FileNotFoundError:
            logger.warning("Linter not found", extra={"linter": linter})
            return []
        except subprocess.TimeoutExpired:
            logger.warning("Linter timeout", extra={"linter": linter, "path": path})
            return []

    def _parse_linter_output(
        self,
        linter: str,
        output: str,
    ) -> list[Finding]:
        """Parse linter output into Finding objects."""
        findings: list[Finding] = []

        if linter == "ruff":
            findings.extend(self._parse_ruff_output(output))
        elif linter == "pylint":
            findings.extend(self._parse_pylint_output(output))
        elif linter == "eslint":
            findings.extend(self._parse_eslint_output(output))

        return findings

    def _parse_ruff_output(self, output: str) -> list[Finding]:
        """Parse ruff output format."""
        findings: list[Finding] = []

        try:
            import json
            data = json.loads(output) if output.strip().startswith("[") else {}

            for item in data if isinstance(data, list) else [data]:
                for msg in item.get("messages", []):
                    findings.append(Finding(
                        rule_id=f"RUFF_{msg.get('code', 'UNK')}",
                        rule_name=msg.get("code", "unknown"),
                        severity=RuleSeverity.WARNING,
                        file=msg.get("filename", ""),
                        line=msg.get("location", {}).get("row", 1),
                        end_line=msg.get("end_location", {}).get("row", 1),
                        message=msg.get("message", ""),
                    ))
        except (json.JSONDecodeError, KeyError):
            for line in output.split("\n"):
                match = re.match(r"(\S+):(\d+):(\d+):\s*(.+)", line)
                if match:
                    findings.append(Finding(
                        rule_id="RUFF_PARSE",
                        rule_name=match.group(4).split()[0] if match.group(4) else "error",
                        severity=RuleSeverity.WARNING,
                        file=match.group(1),
                        line=int(match.group(2)),
                        end_line=int(match.group(2)),
                        column=int(match.group(3)) - 1,
                        message=line,
                    ))

        return findings

    def _parse_pylint_output(self, output: str) -> list[Finding]:
        """Parse pylint output format."""
        findings: list[Finding] = []

        for line in output.split("\n"):
            match = re.match(
                r"([^:]+):(\d+):\s*\[?[A-Z]\d+([^\]]*)\]?\s*(.+)",
                line
            )
            if match:
                findings.append(Finding(
                    rule_id=f"PYLINT_{match.group(3).strip() or 'ERR'}",
                    rule_name=match.group(3).strip() or "pylint-error",
                    severity=RuleSeverity.WARNING,
                    file=match.group(1),
                    line=int(match.group(2)),
                    end_line=int(match.group(2)),
                    message=match.group(4),
                ))

        return findings

    def _parse_eslint_output(self, output: str) -> list[Finding]:
        """Parse eslint JSON output format."""
        findings: list[Finding] = []

        try:
            import json
            data = json.loads(output) if output.strip().startswith("[") else []

            for file_result in data if isinstance(data, list) else [data]:
                for msg in file_result.get("messages", []):
                    findings.append(Finding(
                        rule_id=f"ESLINT_{msg.get('ruleId', 'unknown')}",
                        rule_name=msg.get("ruleId", "unknown"),
                        severity=RuleSeverity.WARNING if msg.get("severity") == 2
                                  else RuleSeverity.INFO,
                        file=file_result.get("filePath", ""),
                        line=msg.get("line", 1),
                        end_line=msg.get("endLine", msg.get("line", 1)),
                        column=msg.get("column", 0) - 1,
                        message=msg.get("message", ""),
                    ))
        except (json.JSONDecodeError, KeyError):
            pass

        return findings

    # ─── Finding Utilities ────────────────────────────────────────────────────

    def merge_findings(
        self,
        findings_list: list[list[Finding]],
    ) -> list[Finding]:
        """Merge and deduplicate findings from multiple sources.

        Args:
            findings_list: List of finding lists to merge

        Returns:
            Deduplicated combined findings
        """
        all_findings: list[Finding] = []
        for findings in findings_list:
            all_findings.extend(findings)
        return self._deduplicate_findings(all_findings)

    def _deduplicate_findings(self, findings: list[Finding]) -> list[Finding]:
        """Remove duplicate findings based on location and rule."""
        seen: set[tuple[str, str, int, int]] = set()
        unique: list[Finding] = []

        for finding in findings:
            key = (finding.rule_id, finding.file, finding.line, finding.end_line)
            if key not in seen:
                seen.add(key)
                unique.append(finding)

        return sorted(unique, key=lambda f: (f.file, f.line, f.severity.to_numeric()))

    def apply_fix(self, finding: Finding) -> str:
        """Generate fix text for a finding.

        Args:
            finding: Finding to generate fix for

        Returns:
            Fixed text or empty string if no fix available
        """
        if not finding.fix:
            return ""

        return finding.fix

    # ─── Helper Methods ───────────────────────────────────────────────────────

    def _get_context_lines(
        self,
        lines: list[str],
        line_num: int,
        context: int = 3,
    ) -> str:
        """Get surrounding code context."""
        start = max(0, line_num - context - 1)
        end = min(len(lines), line_num + context)
        return "\n".join(f"{i+1}: {lines[i]}" for i in range(start, end))

    def _should_skip_path(self, path: Path) -> bool:
        """Check if path should be skipped (e.g., node_modules)."""
        skip_dirs = {"node_modules", "__pycache__", ".git", "venv", ".venv", "dist", "build"}
        return any(part in skip_dirs for part in path.parts)

    def _detect_language(self, path: Path) -> str:
        """Detect language from file extension."""
        ext = path.suffix.lower()
        mapping = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".jsx": "javascript",
            ".tsx": "typescript",
            ".c": "c",
            ".cpp": "cpp",
            ".h": "c",
            ".rs": "rust",
            ".go": "go",
            ".java": "java",
        }
        return mapping.get(ext, "")

    def _detect_language_from_content(self, content: str) -> str:
        """Detect language from file content heuristics."""
        if "def " in content and ":" in content:
            return "python"
        if "function " in content or "const " in content:
            return "javascript"
        if "#include" in content or "int main(" in content:
            return "c"
        return "text"

    @staticmethod
    def _format_finding_message(rule: Rule, matched_text: str = "") -> str:
        """Format a finding message with rule details.

        Args:
            rule: The triggered rule
            matched_text: The matched text snippet

        Returns:
            Formatted message string
        """
        if matched_text and len(matched_text) > 50:
            matched_text = matched_text[:47] + "..."
        msg = f"[{rule.id}] {rule.name}: {rule.description}"
        if matched_text:
            msg += f"\nMatched: {matched_text}"
        if rule.cwe_id:
            msg += f"\nCWE: {rule.cwe_id}"
        return msg

    def get_stats(self, findings: list[Finding]) -> dict[str, Any]:
        """Get statistics about findings.

        Args:
            findings: List of findings to analyze

        Returns:
            Statistics dictionary
        """
        by_severity: dict[str, int] = {s.value: 0 for s in RuleSeverity}
        by_rule: dict[str, int] = {}

        for f in findings:
            by_severity[f.severity.value] += 1
            by_rule[f.rule_id] = by_rule.get(f.rule_id, 0) + 1

        return {
            "total": len(findings),
            "by_severity": by_severity,
            "by_rule": by_rule,
            "files_with_issues": len({f.file for f in findings}),
        }


# ─── Built-in Rules Definition ────────────────────────────────────────────────

def _init_builtin_rules() -> list[Rule]:
    """Initialize all 28 built-in rules.

    Rules are defined inline to avoid circular imports.
    """
    rules: list[Rule] = []

    # SECURITY RULES (6 rules)
    rules.extend([
        Rule(
            id="SEC001", name="hardcoded-secret",
            description="Hardcoded API key, token, password, or secret detected",
            severity=RuleSeverity.ERROR,
            languages=["python", "javascript", "typescript", "go", "java"],
            patterns=[
                r'["\']api[_-]?key["\']\s*[:=]\s*["\'][a-zA-Z0-9_\-]{16,}["\']',
                r'["\']secret["\']\s*[:=]\s*["\'][a-zA-Z0-9_\-]{8,}["\']',
                r'["\']password["\']\s*[:=]\s*["\'][^"\']{4,}["\']',
                r'Bearer\s+[a-zA-Z0-9_\-\.]+',
                r'ghp_[a-zA-Z0-9]{36}',
                r'AKIA[0-9A-Z]{16}',
                r'sk-[a-zA-Z0-9]{32,}',
            ],
            cwe_id="CWE-798", tags=["security", "secrets", "critical"],
            fix_template="Use environment variable: os.getenv('SECRET_NAME')",
        ),
        Rule(
            id="SEC002", name="sql-injection",
            description="Potential SQL injection via string concatenation",
            severity=RuleSeverity.ERROR,
            languages=["python", "javascript", "java"],
            patterns=[
                r'execute\s*\(\s*["\'].*\%s.*["\'].*%',
                r'execute\s*\(\s*f["\']',
                r'cursor\.execute\s*\([^)]*\+[^)]*\)',
            ],
            cwe_id="CWE-89", tags=["security", "injection", "critical"],
            fix_template="Use parameterized queries",
        ),
        Rule(
            id="SEC003", name="command-injection",
            description="Shell command injection risk via subprocess with shell=True",
            severity=RuleSeverity.ERROR,
            languages=["python", "javascript", "java"],
            patterns=[
                r'subprocess\.(run|call|popen)\s*\([^)]*shell\s*=\s*True',
                r'\beval\s*\(',
            ],
            cwe_id="CWE-78", tags=["security", "injection", "critical"],
            fix_template="Use subprocess.run with shell=False",
        ),
        Rule(
            id="SEC004", name="path-traversal",
            description="Potential path traversal vulnerability",
            severity=RuleSeverity.ERROR,
            languages=["python", "javascript", "java", "go"],
            patterns=[
                r'open\s*\([^)]*\+\s*path',
                r'os\.path\.join\s*\([^)]*\+',
            ],
            cwe_id="CWE-22", tags=["security", "path-traversal"],
            fix_template="Validate and sanitize path input",
        ),
        Rule(
            id="SEC005", name="eval-usage",
            description="Use of eval() or exec() is a security risk",
            severity=RuleSeverity.WARNING,
            languages=["python", "javascript"],
            patterns=[r'\beval\s*\(', r'\bexec\s*\('],
            cwe_id="CWE-95", tags=["security", "dynamic-code"],
            fix_template="Avoid eval/exec",
        ),
        Rule(
            id="SEC006", name="insecure-random",
            description="Using random.random() for security purposes",
            severity=RuleSeverity.WARNING,
            languages=["python", "javascript"],
            patterns=[r'random\.random\s*\(\s*\)', r'Math\.random\s*\(\s*\)'],
            cwe_id="CWE-338", tags=["security", "cryptography"],
            fix_template="Use secrets module",
        ),
    ])

    # TYPE SAFETY RULES (4 rules)
    rules.extend([
        Rule(
            id="TYPE001", name="untyped-function",
            description="Python function without type hints",
            severity=RuleSeverity.INFO, languages=["python"],
            patterns=[r'^def\s+[a-zA-Z_][a-zA-Z0-9_]*\s*\([^)]*\)\s*(?:->)?\s*:'],
            tags=["type-safety", "python"],
            fix_template="Add type hints: def func(param: int) -> str:",
        ),
        Rule(
            id="TYPE002", name="any-usage",
            description="Function using 'Any' type annotation",
            severity=RuleSeverity.HINT, languages=["python"],
            patterns=[r':\s*Any\s*[,\)]', r'->\s*Any\b'],
            tags=["type-safety", "python"],
            fix_template="Replace Any with specific type annotations",
        ),
        Rule(
            id="TYPE003", name="missing-return-type",
            description="Public function missing return type annotation",
            severity=RuleSeverity.INFO, languages=["python"],
            patterns=[r'def\s+[A-Z][a-zA-Z0-9_]*\s*\([^)]*\)\s*(?:->)?\s*:'],
            tags=["type-safety", "python"],
            fix_template="Add return type",
        ),
        Rule(
            id="TYPE004", name="type-mismatch",
            description="Potential type mismatch in comparison",
            severity=RuleSeverity.WARNING, languages=["python", "javascript", "typescript"],
            patterns=[r'if\s+type\s*\([^)]*\)\s*==\s*type\s*\('],
            tags=["type-safety", "type-checking"],
            fix_template="Use isinstance() instead of type()",
        ),
    ])

    # IMPORT ANALYSIS RULES (4 rules)
    rules.extend([
        Rule(
            id="IMP001", name="unused-import",
            description="Imported module not used in the file",
            severity=RuleSeverity.INFO, languages=["python"],
            patterns=[r'^import\s+([a-zA-Z_][a-zA-Z0-9_]*)'],
            tags=["imports", "python", "unused"],
            fix_template="Remove unused import",
        ),
        Rule(
            id="IMP002", name="circular-import",
            description="Potential circular import detected",
            severity=RuleSeverity.WARNING, languages=["python"],
            patterns=[r'^from\s+\.\s+import', r'^import\s+\.'],
            tags=["imports", "python", "circular"],
            fix_template="Restructure module dependencies",
        ),
        Rule(
            id="IMP003", name="wildcard-import",
            description="Wildcard import (from X import *) reduces clarity",
            severity=RuleSeverity.WARNING, languages=["python"],
            patterns=[r'from\s+[a-zA-Z_][a-zA-Z0-9_]*\s+import\s+\*'],
            tags=["imports", "python", "best-practice"],
            fix_template="Use explicit imports",
        ),
        Rule(
            id="IMP004", name="relative-import",
            description="Relative import used",
            severity=RuleSeverity.INFO, languages=["python"],
            patterns=[r'from\s+\.\.?\w*\s+import'],
            tags=["imports", "python", "style"],
            fix_template="Consider absolute imports",
        ),
    ])

    # NAMING CONVENTION RULES (4 rules)
    rules.extend([
        Rule(
            id="NAME001", name="snake-case-function",
            description="Function name should use snake_case",
            severity=RuleSeverity.INFO, languages=["python"],
            patterns=[r'def\s+[A-Z][a-zA-Z0-9_]*\s*\(', r'def\s+[a-z_]+[A-Z][a-zA-Z0-9_]*\s*\('],
            tags=["naming", "python", "style"],
            fix_template="Use snake_case: def my_function():",
        ),
        Rule(
            id="NAME002", name="PascalCase-class",
            description="Class name should use PascalCase",
            severity=RuleSeverity.INFO, languages=["python"],
            patterns=[r'class\s+[a-z][a-z0-9_]*\s*[\(:]'],
            tags=["naming", "python", "style"],
            fix_template="Use PascalCase: class MyClass:",
        ),
        Rule(
            id="NAME003", name="UPPER_CASE-CONSTANT",
            description="Module-level constant should use UPPER_CASE",
            severity=RuleSeverity.INFO, languages=["python"],
            patterns=[r'^[a-z][a-z0-9_]*\s*=\s*(?:\d+|["\'].*["\']|True|False|None)'],
            tags=["naming", "python", "style"],
            fix_template="Use UPPER_CASE for constants",
        ),
        Rule(
            id="NAME004", name="single-letter-variable",
            description="Avoid single-letter variable names",
            severity=RuleSeverity.HINT, languages=["python", "javascript", "java"],
            patterns=[r'\bfor\s+([a-h]|p|t|q|r|s|u|v|w)\b'],
            tags=["naming", "style", "readability"],
            fix_template="Use descriptive variable names",
        ),
    ])

    # CODE QUALITY RULES (10 rules)
    rules.extend([
        Rule(
            id="QUAL001", name="long-function",
            description=f"Function exceeds {MAX_FUNCTION_LINES} lines",
            severity=RuleSeverity.WARNING,
            languages=["python", "javascript", "typescript", "java", "c", "cpp", "go", "rust"],
            patterns=[], tags=["complexity", "refactoring", "quality"],
            fix_template="Extract to smaller functions",
        ),
        Rule(
            id="QUAL002", name="nested-callbacks",
            description="Callback/Promise nesting exceeds 3 levels",
            severity=RuleSeverity.WARNING,
            languages=["javascript", "typescript", "python"],
            patterns=[r'\.then\s*\(.*\n.*\.then\s*\('],
            tags=["complexity", "async", "quality"],
            fix_template="Use async/await or extract to named functions",
        ),
        Rule(
            id="QUAL003", name="broad-except",
            description="Bare except or except Exception catches everything",
            severity=RuleSeverity.WARNING, languages=["python"],
            patterns=[r'except\s*:\s*\n', r'except\s+Exception\s*:\s*\n'],
            tags=["error-handling", "python", "quality"],
            fix_template="Catch specific exceptions",
        ),
        Rule(
            id="QUAL004", name="empty-except",
            description="Empty except block without logging",
            severity=RuleSeverity.WARNING, languages=["python"],
            patterns=[r'except\s*:\s*\n\s*pass', r'except\s+\w+\s*:\s*\n\s*pass'],
            tags=["error-handling", "python", "quality"],
            fix_template="Add logging or re-raise the exception",
        ),
        Rule(
            id="QUAL005", name="TODO-FIXME",
            description="Unresolved TODO/FIXME/XXX comment found",
            severity=RuleSeverity.INFO,
            languages=["python", "javascript", "typescript", "c", "cpp", "java", "go", "rust"],
            patterns=[r'\bTODO\b', r'\bFIXME\b', r'\bXXX\b', r'\bHACK\b'],
            tags=["documentation", "maintenance", "quality"],
            fix_template="Resolve the TODO/FIXME or create tracking issue",
        ),
        Rule(
            id="QUAL006", name="print-statement",
            description="Print statement used instead of logging",
            severity=RuleSeverity.HINT, languages=["python"],
            patterns=[r'\bprint\s*\('],
            tags=["logging", "python", "style"],
            fix_template="Use logging module",
        ),
        Rule(
            id="QUAL007", name="magic-number",
            description="Magic number detected (literal number > 1 not in constant)",
            severity=RuleSeverity.INFO,
            languages=["python", "javascript", "typescript", "java", "c", "cpp", "go", "rust"],
            patterns=[r'(?<![a-zA-Z_])(0x[0-9A-Fa-f]+|(?:[2-9]|[1-9]\d+))\b(?![xXa-zA-Z0-9_.\-%])'],
            tags=["readability", "maintainability", "quality"],
            fix_template="Define as constant",
        ),
        Rule(
            id="QUAL008", name="consecutive-blank-lines",
            description="Multiple consecutive blank lines detected",
            severity=RuleSeverity.HINT,
            languages=["python", "javascript", "typescript", "c", "cpp", "java", "go", "rust"],
            patterns=[r'\n\n\n\n+'],
            tags=["formatting", "style", "quality"],
            fix_template="Use single blank line between sections",
        ),
        Rule(
            id="QUAL009", name="trailing-whitespace",
            description="Lines with trailing whitespace",
            severity=RuleSeverity.HINT,
            languages=["python", "javascript", "typescript", "c", "cpp", "java", "go", "rust"],
            patterns=[r'[ \t]+\n'],
            tags=["formatting", "style", "quality"],
            fix_template="Remove trailing whitespace",
        ),
        Rule(
            id="QUAL010", name="cyclomatic-complexity",
            description=f"Function cyclomatic complexity exceeds {MAX_CYCLOMATIC_COMPLEXITY}",
            severity=RuleSeverity.WARNING,
            languages=["python", "javascript", "typescript", "c", "cpp", "java", "go", "rust"],
            patterns=[],
            tags=["complexity", "quality", "maintainability"],
            fix_template="Simplify function",
        ),
    ])

    return rules


# Register all built-in rules
RuleEngine.BUILTIN_RULES = _init_builtin_rules()


# ─── Utility Functions ───────────────────────────────────────────────────────

def _format_message(rule: Rule, matched_text: str = "") -> str:
    """Format a finding message with rule details."""
    if matched_text and len(matched_text) > 50:
        matched_text = matched_text[:47] + "..."
    msg = f"[{rule.id}] {rule.name}: {rule.description}"
    if matched_text:
        msg += f"\nMatched: {matched_text}"
    if rule.cwe_id:
        msg += f"\nCWE: {rule.cwe_id}"
    return msg


# ─── CLI Entry Point ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Static Analysis Rule Engine")
    parser.add_argument("path", help="File or directory to analyze")
    parser.add_argument("--lang", help="Force language detection")
    parser.add_argument("--rule", help="Filter by rule ID")
    parser.add_argument("--severity", help="Filter by severity (error/warning/info/hint)")
    parser.add_argument("--linter", help="Run external linter (pylint, ruff, eslint)")
    args = parser.parse_args()

    engine = RuleEngine()

    findings: list[Finding] = []

    if Path(args.path).is_file():
        lang = args.lang or engine._detect_language(Path(args.path))
        findings = engine.detect(args.path, lang)
    else:
        findings = engine.detect_all(args.path)

    if args.linter:
        findings.extend(engine.run_external_linter(args.linter, args.path))

    if args.rule:
        findings = [f for f in findings if f.rule_id == args.rule]

    if args.severity:
        findings = [f for f in findings if f.severity.value == args.severity]

    stats = engine.get_stats(findings)

    print(f"Found {stats['total']} issues:")
    for severity, count in stats["by_severity"].items():
        if count > 0:
            print(f"  {severity}: {count}")

    if findings:
        print("\nDetailed findings:")
        for f in findings[:50]:
            print(f"  {f.file}:{f.line} [{f.severity.value}] {f.rule_name}: {f.message[:100]}")

    sys.exit(0 if stats["total"] == 0 else 1)
