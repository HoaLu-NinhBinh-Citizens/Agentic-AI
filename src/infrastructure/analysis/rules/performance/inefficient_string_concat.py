"""Inefficient string concatenation detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class InefficientStringConcatRule:
    """Detect inefficient string concatenation in loops.

    Using += in loops creates many intermediate string objects.
    Use list and join() or io.StringIO instead.
    """

    rule_id: str = "PERF001"
    severity: Severity = Severity.MEDIUM

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        try:
            import ast
            tree = ast.parse(content)
        except SyntaxError:
            return findings

        for node in ast.walk(tree):
            if isinstance(node, (ast.For, ast.While, ast.AsyncFor)):
                findings.extend(self._check_loop_for_concat(node, content, file_path))

        return findings

    def _check_loop_for_concat(self, node, content: str, file_path: str) -> list[dict]:
        findings = []

        for child in ast.walk(node):
            if isinstance(child, ast.AugAssign):
                if isinstance(child.op, ast.Add):
                    if isinstance(child.target, ast.Name):
                        var_name = child.target.id
                        if var_name and not var_name.startswith('_'):
                            line_content = content.split('\n')[node.lineno - 1]
                            if '+=' in line_content and '"' in line_content or "'" in line_content:
                                findings.append({
                                    "rule_id": self.rule_id,
                                    "severity": self.severity.value,
                                    "file": file_path,
                                    "line": child.lineno,
                                    "message": f"Inefficient string concatenation: {var_name} += ...",
                                    "explanation": "String concatenation with += in loops is O(n^2) "
                                                   "because strings are immutable in Python.",
                                    "fix": "Use list.append() and ''.join(list) or io.StringIO",
                                })

        return findings
