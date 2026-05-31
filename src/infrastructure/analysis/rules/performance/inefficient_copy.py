"""Inefficient container copy detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class InefficientCopyRule:
    """Detect inefficient container copying patterns.

    Some copy operations are less efficient than alternatives.
    """

    rule_id: str = "PERF019"
    severity: Severity = Severity.LOW

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        inefficient_patterns = [
            (r'list\(\s*\w+\.copy\(\)\s*\)', "Unnecessary list() on copy()"),
            (r'dict\(\s*\w+\.copy\(\)\s*\)', "Unnecessary dict() on copy()"),
            (r'list\(.*\[:\]\s*\)', "list() on slice copy"),
            (r'list\(.*\.keys\(\)\s*\)', "list() on dict.keys() (use list(d.keys()))"),
            (r'\[\s*0\s*\]\s*\*\s*\d+', "List multiplication for initialization"),
            (r'\[\s*["\'].*["\']\s*\]\s*\*', "String multiplication pattern"),
        ]

        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//')):
                continue

            for pattern, desc in inefficient_patterns:
                if re.search(pattern, line):
                    findings.append({
                        "rule_id": self.rule_id,
                        "severity": self.severity.value,
                        "file": file_path,
                        "line": i,
                        "message": f"Inefficient copy: {desc}",
                        "explanation": "This copy operation can be optimized.",
                        "fix": "Use more efficient copying methods",
                    })
                    break

        return findings
