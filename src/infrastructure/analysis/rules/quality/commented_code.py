"""Commented-out code detection rule."""

from dataclasses import dataclass
from typing import Optional
import re

from src.shared.enums.severity import Severity


@dataclass
class CommentedCodeRule:
    """Detect commented-out code.

    Commented code adds clutter and indicates code that should be deleted.
    """

    rule_id: str = "QUAL005"
    severity: Severity = Severity.INFO

    def detect(self, content: str, file_path: str) -> list[dict]:
        """Detect commented-out code in source code.

        Args:
            content: Source code content
            file_path: Path to source file

        Returns:
            List of finding dictionaries
        """
        findings = []

        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            stripped = line.strip()

            code_patterns = [
                r'^#\s*def\s+\w+\(',
                r'^#\s*class\s+\w+',
                r'^#\s*if\s+\w+:',
                r'^#\s*for\s+\w+\s+in',
                r'^#\s*while\s+',
                r'^#\s*import\s+',
                r'^#\s*from\s+\w+\s+import',
            ]

            for pattern in code_patterns:
                if re.search(pattern, stripped):
                    findings.append({
                        "rule_id": self.rule_id,
                        "severity": self.severity.value,
                        "file": file_path,
                        "line": i,
                        "message": "Commented-out code detected",
                        "explanation": "Remove commented code - use git history instead.",
                        "fix": "# Delete the commented code",
                    })
                    break

        return findings
