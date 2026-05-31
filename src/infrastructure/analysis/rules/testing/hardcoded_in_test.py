"""Hardcoded values in tests detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class HardcodedInTestRule:
    """Detect hardcoded values in tests that should be parametrized.

    Tests should use parameterized data or fixtures instead of
    hardcoded values to ensure comprehensive coverage.
    """

    rule_id: str = "TEST003"
    severity: Severity = Severity.LOW

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        if not self._is_test_file(content):
            return findings

        hardcoded_patterns = [
            (r'assert\s+\d+\s*==', "Hardcoded number in assertion"),
            (r'assert\s+["\'][^"\']{50,}["\']\s*==', "Hardcoded long string in assertion"),
            (r'assertEqual\s*\(\s*["\']', "Hardcoded string in assertEqual"),
            (r'assertEqual\s*\(\s*\d+\s*,', "Hardcoded number in assertEqual"),
        ]

        parametrized_patterns = [
            (r'@pytest\.mark\.parametrize', "Parametrized test"),
            (r'default_test_data', "Test data fixture"),
            (r'@pytest\.fixture', "Pytest fixture"),
            (r'setUpClass', "Class setup fixture"),
            (r'@classmethod', "Class method fixture"),
        ]

        lines = content.split('\n')
        has_parametrize = any(re.search(p, content) for p in parametrized_patterns)

        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//')):
                continue

            for pattern, desc in hardcoded_patterns:
                if re.search(pattern, line):
                    findings.append({
                        "rule_id": self.rule_id,
                        "severity": self.severity.value,
                        "file": file_path,
                        "line": i,
                        "message": f"Hardcoded value in test: {desc}",
                        "explanation": "Consider parametrizing tests for better coverage.",
                        "fix": "Use @pytest.mark.parametrize or fixtures for test data",
                    })
                    break

        return findings

    def _is_test_file(self, content: str) -> bool:
        return 'test_' in content or '_test.py' in content
