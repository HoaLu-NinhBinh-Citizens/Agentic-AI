"""Inefficient list operations detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class InefficientListRule:
    """Detect inefficient list operations.

    Using lists where sets or other data structures would be more efficient,
    or using inefficient list operations.
    """

    rule_id: str = "PERF003"
    severity: Severity = Severity.LOW

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        inefficient_patterns = [
            (r'if\s+\w+\s+in\s+\[\s*.*\s*\]', "Membership test on list literal"),
            (r'if\s+\w+\s+not\s+in\s+\[\s*.*\s*\]', "Negative membership test on list"),
            (r'list\(.*\.keys\(\)\)', "Converting dict keys to list unnecessarily"),
            (r'list\(.*\.values\(\)\)', "Converting dict values to list unnecessarily"),
            (r'list\(.*\.items\(\)\)', "Converting dict items to list unnecessarily"),
            (r'\[\s*0\s*for\s+\w+\s+in\s+\w+\s+if\s+', "List comprehension when filter+map"),
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
                        "message": f"Inefficient list operation: {desc}",
                        "explanation": "This operation can be optimized for better performance.",
                        "fix": "Use set for membership tests, or generator expressions",
                    })
                    break

        return findings
