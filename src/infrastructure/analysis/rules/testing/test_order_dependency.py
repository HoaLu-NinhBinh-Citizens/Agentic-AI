"""Test order dependency detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class TestOrderDependencyRule:
    """Detect test order dependencies.

    Tests that depend on execution order are brittle and
    can fail in isolation or in different test runners.
    """

    rule_id: str = "TEST008"
    severity: Severity = Severity.MEDIUM

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        if not self._is_test_file(content):
            return findings

        order_patterns = [
            (r'self\.\w+\s*=', "Setting instance state"),
            (r'cls\.\w+\s*=', "Setting class state"),
            (r'@\.*class.*\n.*setup_class', "Class-level setup"),
            (r'setUpClass\s*\(', "unittest class setup"),
            (r'classmethod\s*\n\s*def\s+setUp', "Class method setup"),
            (r'\.before\(\)', "Before hook usage"),
            (r'\.depends\s*\(', "Test dependency marker"),
            (r'@depends\s*\(', "pytest-depends marker"),
        ]

        isolation_patterns = [
            (r'setUp\s*\(', "Proper setUp method"),
            (r'def\s+setup\s*\(', "setup fixture"),
            (r'@pytest\.fixture.*autouse', "autouse fixture"),
            (r'@pytest\.mark\.isolation', "Isolation marker"),
        ]

        lines = content.split('\n')
        has_isolation = any(re.search(p, content) for p in isolation_patterns)

        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//')):
                continue

            for pattern, desc in order_patterns:
                if re.search(pattern, line):
                    if not has_isolation:
                        findings.append({
                            "rule_id": self.rule_id,
                            "severity": self.severity.value,
                            "file": file_path,
                            "line": i,
                            "message": f"Potential test order dependency: {desc}",
                            "explanation": "Tests should be independent and able to run in any order.",
                            "fix": "Use proper setUp/tearDown or fixtures for state isolation",
                        })
                    break

        return findings

    def _is_test_file(self, content: str) -> bool:
        return 'test_' in content or '_test.py' in content
