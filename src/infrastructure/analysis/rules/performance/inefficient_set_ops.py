"""Inefficient set operations detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class InefficientSetOpsRule:
    """Detect inefficient set operations.

    Some set operations can be simplified or optimized.
    """

    rule_id: str = "PERF015"
    severity: Severity = Severity.LOW

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        inefficient_patterns = [
            (r'list\(\s*set\(', "Converting set to list unnecessarily"),
            (r'tuple\(\s*set\(', "Converting set to tuple unnecessarily"),
            (r'set\(list\(', "Converting list to set unnecessarily"),
            (r'set\(\[', "Creating set from list literal (use set literal)"),
            (r'\{\s*\}\s*\|\s*\{', "Empty set union (use set literal)"),
            (r'set_a\s*\+\s*set_b', "Set concatenation (use | or update)"),
            (r'\.union\(set\([', "Unnecessary set() in union()"),
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
                        "message": f"Inefficient set operation: {desc}",
                        "explanation": "This set operation can be simplified.",
                        "fix": "Use more efficient set operations",
                    })
                    break

        return findings
