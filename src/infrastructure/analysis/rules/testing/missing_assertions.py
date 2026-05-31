"""Missing assertions in tests detection rule."""

from dataclasses import dataclass
import re
import ast

from src.shared.enums.severity import Severity


@dataclass
class MissingAssertionsRule:
    """Detect test functions without assertions.

    Tests without assertions don't verify anything and are useless.
    Every test should have at least one assertion.
    """

    rule_id: str = "TEST001"
    severity: Severity = Severity.HIGH

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        if not self._is_test_file(content):
            return findings

        try:
            tree = ast.parse(content)
        except SyntaxError:
            return findings

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                if self._is_test_function(node.name):
                    has_assertion = self._function_has_assert(node)
                    if not has_assertion:
                        findings.append({
                            "rule_id": self.rule_id,
                            "severity": self.severity.value,
                            "file": file_path,
                            "line": node.lineno,
                            "message": f"Test without assertions: {node.name}()",
                            "explanation": "Test functions should contain assertions to verify "
                                           "expected behavior.",
                            "fix": "Add assertions like assert, pytest.raises, or unittest assertions",
                        })

        return findings

    def _is_test_file(self, content: str) -> bool:
        return 'test_' in content or '_test.py' in content or 'unittest' in content

    def _is_test_function(self, name: str) -> bool:
        return name.startswith('test_') or name.endswith('_test') or 'Test' in name

    def _function_has_assert(self, node: ast.FunctionDef) -> bool:
        for child in ast.walk(node):
            if isinstance(child, ast.Assert):
                return True
            if isinstance(child, ast.Call):
                if isinstance(child.func, ast.Attribute):
                    if 'assert' in child.func.attr.lower():
                        return True
        return False
