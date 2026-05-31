"""Lazy vs eager evaluation detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class LazyVsEagerRule:
    """Detect eager evaluation where lazy evaluation would be better.

    Loading all data into memory when iterating would suffice
    wastes memory and time.
    """

    rule_id: str = "PERF010"
    severity: Severity = Severity.LOW

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        eager_patterns = [
            (r'\.readlines\s*\(\s*\)', "readlines() loads all lines into memory"),
            (r'\.read\s*\(\s*\)', "read() loads entire file into memory"),
            (r'\.decode\(\s*\)\.split\(\s*\)', "Full decode before split"),
            (r'list\(\s*open\(', "Eager file reading with list()"),
            (r'\.fetchall\s*\(\s*\)', "fetchall() loads all rows into memory"),
            (r'pd\.read_csv\(.*\)\.iterrows', "Reading entire CSV before iteration"),
            (r'\.items\(\)\.all\(\)', "Loading all items unnecessarily"),
        ]

        lazy_patterns = [
            (r'for\s+line\s+in\s+file:', "Iterating file directly"),
            (r'\.readline\s*\(\s*\)', "Lazy line reading"),
            (r'\.iter_rows\s*\(', "Lazy row iteration"),
            (r'yield', "Generator pattern"),
            (r'islice\s*\(', "Lazy slicing"),
        ]

        lines = content.split('\n')
        has_lazy = any(re.search(p, content) for p in lazy_patterns)

        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//')):
                continue

            for pattern, desc in eager_patterns:
                if re.search(pattern, line):
                    if not has_lazy:
                        findings.append({
                            "rule_id": self.rule_id,
                            "severity": self.severity.value,
                            "file": file_path,
                            "line": i,
                            "message": f"Eager evaluation: {desc}",
                            "explanation": "Loading all data into memory when iterating "
                                           "would suffice wastes resources.",
                            "fix": "Use lazy iteration patterns or generators",
                        })
                    break

        return findings
