"""Slow test detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class SlowTestRule:
    """Detect potentially slow test patterns.

    Tests that use time.sleep() or make real network calls
    can slow down test suites significantly.
    """

    rule_id: str = "TEST002"
    severity: Severity = Severity.MEDIUM

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        slow_patterns = [
            (r'time\.sleep\s*\(\s*[1-9]', "time.sleep() with seconds >= 1"),
            (r'time\.sleep\s*\(\s*\d+\.?\d*', "time.sleep() call detected"),
            (r'requests\.get\s*\(', "Real HTTP GET request"),
            (r'requests\.post\s*\(', "Real HTTP POST request"),
            (r'httpx\.get\s*\(', "Real HTTPX GET request"),
            (r'urllib\.request\.urlopen', "Real HTTP request via urllib"),
            (r'\.connect\(.*:5432', "Real database connection"),
            (r'subprocess\.run\s*\(', "Subprocess call in test"),
            (r'os\.system\s*\(', "System call in test"),
        ]

        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//')):
                continue

            for pattern, desc in slow_patterns:
                if re.search(pattern, line):
                    findings.append({
                        "rule_id": self.rule_id,
                        "severity": self.severity.value,
                        "file": file_path,
                        "line": i,
                        "message": f"Potentially slow test: {desc}",
                        "explanation": "This pattern can slow down test execution. "
                                       "Consider mocking or using fixtures.",
                        "fix": "Use mocking, pytest.mark.slow, or test fixtures",
                    })
                    break

        return findings
