"""Unnecessary all() call detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class UnnecessaryAllRule:
    """Detect unnecessary all() calls.

    Using all() on already-iterable data structures is redundant.
    Also detect inefficient all() with generator vs list.
    """

    rule_id: str = "PERF009"
    severity: Severity = Severity.LOW

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        unnecessary_patterns = [
            (r'all\(\s*list\(', "all() with unnecessary list() call"),
            (r'all\(\s*tuple\(', "all() with unnecessary tuple() call"),
            (r'all\(\s*set\(', "all() with unnecessary set() call"),
            (r'all\(\s*frozenset\(', "all() with unnecessary frozenset() call"),
            (r'all\(\[\s*\w+\s+for\s+', "all() with list comprehension (use generator)"),
            (r'all\(\s*\{\s*\w+\s+for\s+', "all() with set comprehension (use generator)"),
            (r'all\(\s*\[\s*.*\s+if\s+', "all() with filtered list comprehension"),
        ]

        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//')):
                continue

            for pattern, desc in unnecessary_patterns:
                if re.search(pattern, line):
                    findings.append({
                        "rule_id": self.rule_id,
                        "severity": self.severity.value,
                        "file": file_path,
                        "line": i,
                        "message": f"Unnecessary all() usage: {desc}",
                        "explanation": "all() can work directly with generators and iterables. "
                                       "Creating intermediate collections wastes memory.",
                        "fix": "Use generator expression: all(x for x in items)",
                    })
                    break

        return findings
