"""Inefficient filter usage detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class InefficientFilterRule:
    """Detect inefficient filter() usage.

    filter() with lambda is often slower than list
    comprehension. filter() without list() may be fine.
    """

    rule_id: str = "PERF028"
    severity: Severity = Severity.LOW

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        inefficient_patterns = [
            (r'list\s*\(\s*filter\s*\(\s*lambda\s+', "list(filter(lambda)) pattern"),
            (r'filter\s*\(\s*lambda\s+[^:]+:\s*True', "filter with lambda returning True"),
            (r'filter\s*\(\s*lambda\s+[^:]+:\s*False', "filter with lambda returning False"),
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
                        "message": f"Inefficient filter: {desc}",
                        "explanation": "filter() with lambda can often be replaced with "
                                       "more efficient comprehension.",
                        "fix": "Use list comprehension or generator expression",
                    })
                    break

        return findings
