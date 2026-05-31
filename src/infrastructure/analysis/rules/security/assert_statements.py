"""Assert statement detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class AssertStatementRule:
    """Detect assert statements that may be disabled in production.

    Python's -O flag disables assert statements, making them
    unreliable for security checks or input validation.
    """

    rule_id: str = "SEC026"
    severity: Severity = Severity.MEDIUM

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        assert_pattern = r'\bassert\s+'

        lines = content.split('\n')

        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//')):
                continue

            if re.search(assert_pattern, line):
                findings.append({
                    "rule_id": self.rule_id,
                    "severity": self.severity.value,
                    "file": file_path,
                    "line": i,
                    "message": "Assert statement detected",
                    "explanation": "Asserts are disabled when Python runs with -O flag. "
                                   "Do not use asserts for input validation or security checks.",
                    "fix": "Use proper if statements with raising exceptions",
                })

        return findings
