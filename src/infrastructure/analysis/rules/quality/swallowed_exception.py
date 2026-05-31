"""Swallowed exception detection rule."""

from dataclasses import dataclass
import ast

from src.shared.enums.severity import Severity


@dataclass
class SwallowedExceptionRule:
    """Detect exceptions that are caught but not handled.

    Empty except blocks or exceptions that are caught but not
    logged or re-raised can hide bugs.
    """

    rule_id: str = "QUAL012"
    severity: Severity = Severity.HIGH

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        try:
            tree = ast.parse(content)
        except SyntaxError:
            return findings

        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                if self._is_swallowed_exception(node):
                    handler_type = "Exception"
                    if node.type:
                        handler_type = ast.unparse(node.type) if hasattr(ast, 'unparse') else "Exception"

                    findings.append({
                        "rule_id": self.rule_id,
                        "severity": self.severity.value,
                        "file": file_path,
                        "line": node.lineno,
                        "message": f"Swallowed exception: except {handler_type}",
                        "explanation": "Exception caught but not logged or re-raised. "
                                       "This can hide bugs and make debugging difficult.",
                        "fix": "Log the exception, re-raise it, or handle it appropriately",
                    })

        return findings

    def _is_swallowed_exception(self, node: ast.ExceptHandler) -> bool:
        if len(node.body) == 0:
            return True

        if len(node.body) == 1:
            stmt = node.body[0]
            if isinstance(stmt, ast.Pass):
                return True

            if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
                return True

        return False
