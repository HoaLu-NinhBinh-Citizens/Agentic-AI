"""Nested try blocks detection rule."""

from dataclasses import dataclass
import ast

from src.shared.enums.severity import Severity


@dataclass
class NestedTryRule:
    """Detect deeply nested try blocks.

    Deeply nested try blocks indicate complex error handling
    that may be difficult to understand and maintain.
    """

    rule_id: str = "QUAL014"
    severity: Severity = Severity.LOW

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        try:
            tree = ast.parse(content)
        except SyntaxError:
            return findings

        for node in ast.walk(tree):
            max_depth = self._calculate_try_depth(node)
            if max_depth > 2:
                findings.append({
                    "rule_id": self.rule_id,
                    "severity": self.severity.value,
                    "file": file_path,
                    "line": node.lineno if hasattr(node, 'lineno') else 1,
                    "message": f"Nested try blocks: depth {max_depth}",
                    "explanation": "Deeply nested try blocks indicate complex error handling "
                                   "that may be hard to maintain.",
                    "fix": "Extract inner try blocks into separate functions",
                })

        return findings

    def _calculate_try_depth(self, node: ast.Try) -> int:
        max_depth = 1

        for child in ast.walk(node):
            if child is not node and isinstance(child, ast.Try):
                inner_depth = self._calculate_try_depth(child)
                max_depth = max(max_depth, 1 + inner_depth)

        return max_depth
