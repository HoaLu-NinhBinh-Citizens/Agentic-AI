"""Missing mock detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class MissingMockRule:
    """Detect missing mocks in tests.

    Tests that call real external services should mock them
    to ensure test isolation and speed.
    """

    rule_id: str = "TEST007"
    severity: Severity = Severity.MEDIUM

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        if not self._is_test_file(content):
            return findings

        real_call_patterns = [
            (r'requests\.get\s*\(', "Real HTTP GET request"),
            (r'requests\.post\s*\(', "Real HTTP POST request"),
            (r'requests\.put\s*\(', "Real HTTP PUT request"),
            (r'requests\.delete\s*\(', "Real HTTP DELETE request"),
            (r'redis\.Redis\s*\(', "Real Redis connection"),
            (r'pymongo\.MongoClient', "Real MongoDB connection"),
            (r'mysql\.connector\.connect', "Real MySQL connection"),
            (r'psycopg2\.connect', "Real PostgreSQL connection"),
            (r'boto3\.client', "Real AWS client"),
        ]

        mock_patterns = [
            (r'@mock\.patch', "mock.patch decorator"),
            (r'@patch\.object', "patch.object decorator"),
            (r'@pytest\.fixture.*mock', "Mock fixture"),
            (r'Mock\s*\(', "Mock object"),
            (r'MagicMock\s*\(', "MagicMock object"),
            (r'requests_mock', "requests-mock usage"),
        ]

        lines = content.split('\n')
        has_mock = any(re.search(p, content) for p in mock_patterns)

        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//')):
                continue

            for pattern, desc in real_call_patterns:
                if re.search(pattern, line):
                    if not has_mock:
                        findings.append({
                            "rule_id": self.rule_id,
                            "severity": self.severity.value,
                            "file": file_path,
                            "line": i,
                            "message": f"External call without mock: {desc}",
                            "explanation": "Real external calls can slow tests and cause "
                                           "flakiness. Consider mocking these calls.",
                            "fix": "Use @mock.patch or requests_mock fixture",
                        })
                    break

        return findings

    def _is_test_file(self, content: str) -> bool:
        return 'test_' in content or '_test.py' in content
