"""Shared state in tests detection rule."""

from dataclasses import dataclass
import ast

from src.shared.enums.severity import Severity


@dataclass
class SharedStateRule:
    """Detect shared state between tests.

    Tests that share state can cause flaky tests and
    order-dependent failures.
    """

    rule_id: str = "TEST005"
    severity: Severity = Severity.MEDIUM

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        if not self._is_test_file(content):
            return findings

        try:
            tree = ast.parse(content)
        except SyntaxError:
            return findings

        module_vars = []
        class_vars = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Module):
                for child in node.body:
                    if isinstance(child, ast.Assign):
                        for target in child.targets:
                            if isinstance(target, ast.Name):
                                module_vars.append(target.id)
                    elif isinstance(child, ast.ClassDef):
                        for inner in child.body:
                            if isinstance(inner, ast.Assign):
                                for target in inner.targets:
                                    if isinstance(target, ast.Name):
                                        class_vars.append((child.name, target.id))

        global_vars = [v for v in module_vars if not v.startswith('_')]

        if len(global_vars) > 3:
            findings.append({
                "rule_id": self.rule_id,
                "severity": self.severity.value,
                "file": file_path,
                "line": 1,
                "message": f"Multiple module-level variables: {global_vars[:5]}",
                "explanation": "Module-level variables can cause state leakage between tests.",
                "fix": "Use fixtures or setUp/tearDown methods for test state",
            })

        for class_name, var_name in class_vars:
            findings.append({
                "rule_id": self.rule_id,
                "severity": self.severity.value,
                "file": file_path,
                "line": 1,
                "message": f"Class-level variable may cause shared state: {class_name}.{var_name}",
                "explanation": "Class variables are shared across test instances and can "
                               "cause flaky tests.",
                "fix": "Use instance variables in setUp or fixtures",
            })

        return findings

    def _is_test_file(self, content: str) -> bool:
        return 'test_' in content or '_test.py' in content
