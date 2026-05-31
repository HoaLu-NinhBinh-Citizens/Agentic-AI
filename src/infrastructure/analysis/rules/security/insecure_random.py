"""Insecure random number generation detection rule."""

from dataclasses import dataclass
from typing import Optional
import re

from src.shared.enums.severity import Severity


INSECURE_RANDOM = [
    r'random\.random\(',
    r'random\.randint\(',
    r'random\.choice\(',
    r'Math\.random\(',
]


@dataclass
class InsecureRandomRule:
    """Detect use of random module for security purposes.

    The random module is not cryptographically secure.
    Use secrets module for security-sensitive randomness.
    """

    rule_id: str = "SEC007"
    severity: Severity = Severity.HIGH

    def detect(self, content: str, file_path: str) -> list[dict]:
        """Detect insecure random usage in source code.

        Args:
            content: Source code content
            file_path: Path to source file

        Returns:
            List of finding dictionaries
        """
        findings = []

        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            for pattern in INSECURE_RANDOM:
                if re.search(pattern, line):
                    findings.append({
                        "rule_id": self.rule_id,
                        "severity": self.severity.value,
                        "file": file_path,
                        "line": i,
                        "message": "Use of insecure random for security purposes",
                        "explanation": "random module is not cryptographically secure. "
                                       "Use secrets.token_bytes() or secrets.choice() instead.",
                        "fix": "# Use secrets module: secrets.token_bytes(32)",
                    })

        return findings
