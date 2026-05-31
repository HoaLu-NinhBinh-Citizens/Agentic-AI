"""Empty test function detection rule."""

from dataclasses import dataclass
import ast

from src.shared.enums.severity import Severity


@dataclass
class EmptyTestRule:
    """Detect empty test functions.

    Empty tests don't test anything and waste CI time.
    Either implement the test or remove it.
    """

    rule_id: str = "TEST004"
    severity: Severity = Severity.MEDIUM

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
                    if len(node.body) == 1:
                        stmt = node.body[0]
                        if isinstance(stmt, ast.Pass):
                            findings.append({
                                "rule_id": self.rule_id,
                                "severity": self.severity.value,
                                "file": file_path,
                                "line": node.lineno,
                                "message": f"Empty test function: {node.name}()",
                                "explanation": "Empty tests don't verify anything and "
                                               "waste test execution time.",
                                "fix": "Implement the test or remove it",
                            })

        return findings

    def _is_test_file(self, content: str) -> bool:
        return 'test_' in content or '_test.py' in content

    def _is_test_function(self, name: str) -> bool:
        return name.startswith('test_') or name.endswith('_test')
