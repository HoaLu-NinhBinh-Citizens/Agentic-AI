"""Overly broad mock detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class OverlyBroadMockRule:
    """Detect overly broad mock configurations.

    Using overly broad mocks can hide real bugs and make
    tests less valuable.
    """

    rule_id: str = "TEST009"
    severity: Severity = Severity.LOW

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        if not self._is_test_file(content):
            return findings

        broad_patterns = [
            (r'patch\s*\(\s*["\']__builtins__', "Mocking builtins (too broad)"),
            (r'patch\s*\(\s*["\']sys\.', "Mocking sys module (too broad)"),
            (r'patch\s*\(\s*["\']os\.', "Mocking os module (too broad)"),
            (r'Mock\s*\(\s*return_value\s*=\s*True\s*\)', "Mock returning True for everything"),
            (r'mock\.ANY', "mock.ANY usage (may be too loose)"),
            (r'patch\.dict\s*\([^,]+,\s*\{', "Patching entire dict (too broad)"),
            (r'autospec\s*=\s*True', "Autospec detected (verify it's needed)"),
        ]

        specific_patterns = [
            (r'patch\s*\(\s*["\']\w+\.\w+', "Specific module mock"),
            (r'patch\.object\s*\([^,]+,\s*["\']', "Specific object mock"),
        ]

        lines = content.split('\n')
        has_specific = any(re.search(p, content) for p in specific_patterns)

        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//')):
                continue

            for pattern, desc in broad_patterns:
                if re.search(pattern, line):
                    findings.append({
                        "rule_id": self.rule_id,
                        "severity": self.severity.value,
                        "file": file_path,
                        "line": i,
                        "message": f"Overly broad mock: {desc}",
                        "explanation": "Mocking too broadly can hide real bugs. "
                                       "Mock at the appropriate level of abstraction.",
                        "fix": "Mock specific functions or objects instead of entire modules",
                    })
                    break

        return findings

    def _is_test_file(self, content: str) -> bool:
        return 'test_' in content or '_test.py' in content
