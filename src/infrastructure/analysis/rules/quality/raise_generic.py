"""Raising generic exception detection rule."""

from dataclasses import dataclass
import ast

from src.shared.enums.severity import Severity


@dataclass
class RaiseGenericRule:
    """Detect raising generic Exception instead of specific types.

    Raising generic exceptions makes error handling difficult
    and reduces the value of stack traces.
    """

    rule_id: str = "QUAL013"
    severity: Severity = Severity.MEDIUM

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        try:
            tree = ast.parse(content)
        except SyntaxError:
            return findings

        for node in ast.walk(tree):
            if isinstance(node, ast.Raise):
                if self._is_generic_raise(node):
                    findings.append({
                        "rule_id": self.rule_id,
                        "severity": self.severity.value,
                        "file": file_path,
                        "line": node.lineno,
                        "message": "Raising generic Exception",
                        "explanation": "Raising generic Exception makes error handling difficult. "
                                       "Raise specific exception types for better error handling.",
                        "fix": "Raise a specific exception type like ValueError, TypeError, or custom exception",
                    })

        return findings

    def _is_generic_raise(self, node: ast.Raise) -> bool:
        if node.exc is None:
            return False

        if isinstance(node.exc, ast.Name):
            if node.exc.id in ('Exception', 'BaseException', 'Error'):
                return True

        if isinstance(node.exc, ast.Call):
            if isinstance(node.exc.func, ast.Name):
                if node.exc.func.id in ('Exception', 'BaseException', 'Error'):
                    return True

        return False
