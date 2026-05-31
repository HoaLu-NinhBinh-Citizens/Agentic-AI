"""Regex compilation in loop detection rule."""

from dataclasses import dataclass
import re
import ast

from src.shared.enums.severity import Severity


@dataclass
class RegexInLoopRule:
    """Detect regex compilation inside loops.

    Compiling regex patterns inside loops is inefficient.
    Compile patterns once outside the loop.
    """

    rule_id: str = "PERF006"
    severity: Severity = Severity.MEDIUM

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        try:
            tree = ast.parse(content)
        except SyntaxError:
            return findings

        for node in ast.walk(tree):
            if isinstance(node, (ast.For, ast.While, ast.AsyncFor)):
                findings.extend(self._check_loop_for_regex(node, content, file_path))

        return findings

    def _check_loop_for_regex(self, node, content: str, file_path: str) -> list[dict]:
        findings = []

        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                if isinstance(child.func, ast.Attribute):
                    if child.func.attr == 'compile':
                        if isinstance(child.func.value, ast.Name):
                            if child.func.value.id == 're':
                                findings.append({
                                    "rule_id": self.rule_id,
                                    "severity": self.severity.value,
                                    "file": file_path,
                                    "line": child.lineno,
                                    "message": "Regex compiled inside loop",
                                    "explanation": "Compiling regex patterns inside loops wastes CPU cycles. "
                                                   "Compile patterns once before the loop.",
                                    "fix": "Move re.compile() outside the loop",
                                })

        return findings
