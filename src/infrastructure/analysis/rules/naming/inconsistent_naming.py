"""Inconsistent naming convention detection rule."""

from dataclasses import dataclass
from typing import Optional, List
import ast
import re

from src.shared.enums.severity import Severity


NAMING_PATTERNS = {
    'function': r'^[a-z_][a-z0-9_]*$',
    'class': r'^[A-Z][a-zA-Z0-9]*$',
    'constant': r'^[A-Z][A-Z0-9_]*$',
}


@dataclass
class InconsistentNamingRule:
    """Detect inconsistent naming conventions.

    Following PEP 8 naming conventions improves code readability.
    """

    rule_id: str = "NAME001"
    severity: Severity = Severity.INFO

    def detect(self, content: str, file_path: str) -> list[dict]:
        """Detect inconsistent naming conventions in source code.

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
            if isinstance(node, ast.FunctionDef):
                if not node.name.startswith('_'):
                    if not re.match(NAMING_PATTERNS['function'], node.name):
                        findings.append({
                            "rule_id": self.rule_id,
                            "severity": self.severity.value,
                            "file": file_path,
                            "line": node.lineno,
                            "message": f"Function '{node.name}' doesn't follow snake_case",
                            "explanation": "Function names should be snake_case (PEP 8).",
                            "fix": f"# Rename to: {self._to_snake_case(node.name)}",
                        })

            elif isinstance(node, ast.ClassDef):
                if not re.match(NAMING_PATTERNS['class'], node.name):
                    findings.append({
                        "rule_id": self.rule_id,
                        "severity": self.severity.value,
                        "file": file_path,
                        "line": node.lineno,
                        "message": f"Class '{node.name}' doesn't follow PascalCase",
                        "explanation": "Class names should be PascalCase (PEP 8).",
                        "fix": f"# Rename to: {self._to_pascal_case(node.name)}",
                    })

        return findings

    def _to_snake_case(self, name: str) -> str:
        """Convert to snake_case."""
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
        return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()

    def _to_pascal_case(self, name: str) -> str:
        """Convert to PascalCase."""
        return ''.join(word.title() for word in name.split('_'))
