"""Cognitive complexity detection rule."""

from dataclasses import dataclass
from typing import Optional, Set
import ast

from src.shared.enums.severity import Severity


@dataclass
class CognitiveComplexityRule:
    """Detect high cognitive complexity in functions.

    Cognitive complexity measures how hard code is to understand.
    Functions with complexity > 15 should be refactored.
    """

    rule_id: str = "QUAL001"
    severity: Severity = Severity.WARNING
    threshold: int = 15

    def detect(self, content: str, file_path: str) -> list[dict]:
        """Detect high cognitive complexity in source code.

        Args:
            content: Source code content
            file_path: Path to source file

        Returns:
            List of finding dictionaries
        """
        findings = []

        try:
            tree = ast.parse(content)
        except SyntaxError:
            return findings

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                complexity = self._calculate_complexity(node)

                if complexity > self.threshold:
                    findings.append({
                        "rule_id": self.rule_id,
                        "severity": self.severity.value,
                        "file": file_path,
                        "line": node.lineno,
                        "message": f"Cognitive complexity {complexity} exceeds threshold {self.threshold}",
                        "explanation": f"Function '{node.name}' is complex and hard to maintain. "
                                       "Consider extracting nested logic into separate functions.",
                        "fix": "# Extract nested conditions into helper functions",
                    })

        return findings

    def _calculate_complexity(self, node: ast.FunctionDef) -> int:
        """Calculate cognitive complexity of a function."""
        complexity = 0

        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.For, ast.While, ast.AsyncWith)):
                complexity += 1
            elif isinstance(child, ast.BoolOp):
                complexity += 1
            elif isinstance(child, ast.ExceptHandler):
                complexity += 1
            elif isinstance(child, ast.Call):
                if isinstance(child.func, ast.Name) and child.func.id == node.name:
                    complexity += 1

        return complexity
