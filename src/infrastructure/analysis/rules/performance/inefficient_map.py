"""Inefficient map usage detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class InefficientMapRule:
    """Detect inefficient map() usage.

    map() with lambda is often slower than list
    comprehension.
    """

    rule_id: str = "PERF029"
    severity: Severity = Severity.LOW

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        inefficient_patterns = [
            (r'list\s*\(\s*map\s*\(\s*lambda\s+', "list(map(lambda)) pattern"),
            (r'map\s*\(\s*lambda\s+[^:]+:\s*\w+\s*\+\s*["\']["\']', "map with lambda for string concat"),
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
                        "message": f"Inefficient map: {desc}",
                        "explanation": "map() with lambda can often be replaced with "
                                       "more efficient list comprehension.",
                        "fix": "Use list comprehension instead",
                    })
                    break

        return findings
