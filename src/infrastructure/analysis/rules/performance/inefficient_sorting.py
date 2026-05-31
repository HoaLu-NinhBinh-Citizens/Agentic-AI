"""Inefficient sorting detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class InefficientSortingRule:
    """Detect inefficient sorting patterns.

    Some sorting operations can be optimized or are
    performed on already-sorted data.
    """

    rule_id: str = "PERF020"
    severity: Severity = Severity.LOW

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        inefficient_patterns = [
            (r'sorted\s*\(\s*sorted\s*\(', "Nested sorted() calls"),
            (r'\.sort\s*\(\s*reverse\s*=\s*True\s*\)\s*\n\s*.*\.sort\s*\(\s*reverse', "Double sort for different orders"),
            (r'list\(set\(.*\)\)\.sort', "Converting set to list then sorting"),
            (r'\[.*\]\.sort\s*\(\s*key\s*=\s*lambda\s*x\s*:\s*x\s*\)', "Unnecessary sort key"),
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
                        "message": f"Inefficient sorting: {desc}",
                        "explanation": "This sorting pattern can be optimized.",
                        "fix": "Use more efficient sorting approach",
                    })
                    break

        return findings
