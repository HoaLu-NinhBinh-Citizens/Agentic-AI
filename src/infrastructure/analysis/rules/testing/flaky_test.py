"""Flaky test detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class FlakyTestRule:
    """Detect patterns that can cause flaky tests.

    Flaky tests fail non-deterministically and should be avoided.
    """

    rule_id: str = "TEST006"
    severity: Severity = Severity.HIGH

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        if not self._is_test_file(content):
            return findings

        flaky_patterns = [
            (r'time\.sleep\s*\(', "time.sleep() in test (can cause timeout issues)"),
            (r'\.mock\.patch\.object\s*\(.*time\.', "Mocking time can cause flakiness"),
            (r'request\.slee', "requests with sleep (async timing issue)"),
            (r'returncode\s*!=\s*0', "Checking exact return codes (race condition)"),
            (r'\.join\s*\(\s*\)', "Thread join without timeout (potential hang)"),
            (r'while\s+not\s+.*:\s*\n\s*time\.sleep', "Busy wait with sleep (flaky)"),
            (r'sleep\(0\.0', "Zero sleep to yield (unreliable)"),
            (r'random\.random\s*\(', "Random in test (non-deterministic)"),
            (r'mock\.return_value\s*=\s*\[.*random', "Mocking with random values"),
        ]

        flaky_allowlist = [
            (r'@pytest\.mark\.flaky', "Marked as flaky intentionally"),
            (r'retry', "Retry mechanism present"),
            (r'pytest-rerunfailures', "Rerun failures plugin"),
        ]

        lines = content.split('\n')
        has_allowlist = any(re.search(p, content) for p in flaky_allowlist)

        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//')):
                continue

            for pattern, desc in flaky_patterns:
                if re.search(pattern, line):
                    if not has_allowlist:
                        findings.append({
                            "rule_id": self.rule_id,
                            "severity": self.severity.value,
                            "file": file_path,
                            "line": i,
                            "message": f"Potential flaky test: {desc}",
                            "explanation": "This pattern can cause non-deterministic test failures.",
                            "fix": "Use deterministic values, proper waits, or retry mechanisms",
                        })
                    break

        return findings

    def _is_test_file(self, content: str) -> bool:
        return 'test_' in content or '_test.py' in content
