"""Missing example in docstring detection rule."""

from dataclasses import dataclass
import ast

from src.shared.enums.severity import Severity


@dataclass
class MissingExampleRule:
    """Detect functions without examples in docstrings.

    Complex functions and public APIs should include
    usage examples in their docstrings.
    """

    rule_id: str = "DOC005"
    severity: Severity = Severity.INFO

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        try:
            tree = ast.parse(content)
        except SyntaxError:
            return findings

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if self._is_public_api(node):
                    docstring = ast.get_docstring(node)
                    if docstring:
                        if not self._has_example(docstring):
                            findings.append({
                                "rule_id": self.rule_id,
                                "severity": self.severity.value,
                                "file": file_path,
                                "line": node.lineno,
                                "message": f"Missing example in docstring: {node.name}",
                                "explanation": "Public functions and classes should include "
                                               "usage examples in their docstrings.",
                                "fix": "Add Examples section to docstring",
                            })

        return findings

    def _is_public_api(self, node) -> bool:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return not node.name.startswith('_')

        if isinstance(node, ast.ClassDef):
            return not node.name.startswith('_')

        return False

    def _has_example(self, docstring: str) -> bool:
        example_markers = [
            'Example',
            'Examples',
            '>>>',  # doctest format
            '.. code-block::',
            'Usage:',
            '```python',
            '```py',
        ]

        return any(marker in docstring for marker in example_markers)
