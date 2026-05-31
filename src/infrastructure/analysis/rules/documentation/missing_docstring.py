"""Missing docstring detection rule."""

from dataclasses import dataclass
import ast

from src.shared.enums.severity import Severity


@dataclass
class MissingDocstringRule:
    """Detect functions and classes without docstrings.

    Public functions and classes should have docstrings
    to document their purpose and usage.
    """

    rule_id: str = "DOC001"
    severity: Severity = Severity.INFO

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        try:
            tree = ast.parse(content)
        except SyntaxError:
            return findings

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if self._should_have_docstring(node):
                    if not ast.get_docstring(node):
                        findings.append({
                            "rule_id": self.rule_id,
                            "severity": self.severity.value,
                            "file": file_path,
                            "line": node.lineno,
                            "message": f"Missing docstring: {self._get_node_type(node)} {node.name}()",
                            "explanation": "Public functions and classes should have docstrings "
                                           "to document their purpose and usage.",
                            "fix": "Add a docstring explaining the function/class purpose",
                        })

        return findings

    def _should_have_docstring(self, node) -> bool:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith('_') and not node.name.startswith('__'):
                return False
            if len(node.body) == 0:
                return False
            return True

        if isinstance(node, ast.ClassDef):
            if node.name.startswith('_'):
                return False
            if len(node.body) == 0:
                return False
            return True

        return False

    def _get_node_type(self, node) -> str:
        if isinstance(node, ast.FunctionDef:
            return "Function"
        elif isinstance(node, ast.AsyncFunctionDef):
            return "Async function"
        elif isinstance(node, ast.ClassDef):
            return "Class"
        return "Code element"
