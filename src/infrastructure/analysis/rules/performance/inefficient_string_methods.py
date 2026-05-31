"""Inefficient string methods detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class InefficientStringMethodsRule:
    """Detect inefficient string method usage.

    Some string operations are less efficient than alternatives.
    """

    rule_id: str = "PERF016"
    severity: Severity = Severity.LOW

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        inefficient_patterns = [
            (r'\.join\s*\(\s*list\(', "list() inside join() (unnecessary)"),
            (r'\.upper\(\)\s*==', "upper() before comparison (use casefold)"),
            (r'\.lower\(\)\s*==', "lower() before comparison (use casefold)"),
            (r'\+["\']["\']', "Empty string concatenation with +"),
            (r'["\']["\']\s*\+', "Empty string concatenation with +"),
            (r'\.replace\s*\([^,]+,\s*[^,]+,\s*\d+\s*\)', "replace with max parameter (inefficient)"),
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
                        "message": f"Inefficient string operation: {desc}",
                        "explanation": "This string operation can be optimized.",
                        "fix": "Use more efficient string methods",
                    })
                    break

        return findings
