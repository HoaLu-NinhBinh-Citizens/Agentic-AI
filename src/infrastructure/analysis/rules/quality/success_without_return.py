"""Success path without return detection rule."""

from dataclasses import dataclass
import ast

from src.shared.enums.severity import Severity


@dataclass
class SuccessWithoutReturnRule:
    """Detect functions that sometimes return and sometimes don't.

    Functions with inconsistent return paths make code harder
    to understand and can lead to None being returned unexpectedly.
    """

    rule_id: str = "QUAL015"
    severity: Severity = Severity.LOW

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        try:
            tree = ast.parse(content)
        except SyntaxError:
            return findings

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if self._has_inconsistent_returns(node):
                    findings.append({
                        "rule_id": self.rule_id,
                        "severity": self.severity.value,
                        "file": file_path,
                        "line": node.lineno,
                        "message": f"Inconsistent returns: {node.name}()",
                        "explanation": "Some code paths return values while others don't. "
                                       "This can lead to unexpected None values.",
                        "fix": "Ensure all paths return a value, or none do",
                    })

        return findings

    def _has_inconsistent_returns(self, node) -> bool:
        has_return = False
        has_no_return = False

        for child in ast.walk(node):
            if isinstance(child, ast.Return):
                has_return = True
            elif isinstance(child, ast.If):
                for stmt in child.body:
                    if isinstance(stmt, ast.Return):
                        has_return = True
                if child.orelse:
                    for stmt in child.orelse:
                        if isinstance(stmt, ast.Return):
                            has_return = True
                        elif isinstance(stmt, ast.Raise):
                            pass
                        else:
                            has_no_return = True
            elif isinstance(child, ast.While):
                for stmt in child.body:
                    if isinstance(stmt, ast.Return):
                        has_return = True
                if child.orelse:
                    has_no_return = True

        return has_return and has_no_return
