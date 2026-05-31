"""Inefficient file reading detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class InefficientFileReadRule:
    """Detect inefficient file reading patterns.

    Reading files line by line or all at once when not needed
    can be inefficient for large files.
    """

    rule_id: str = "PERF021"
    severity: Severity = Severity.LOW

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        inefficient_patterns = [
            (r'open\([^)]+\)\.readlines\s*\(\s*\)', "readlines() for entire file"),
            (r'\.readlines\s*\(\s*\)', "readlines() call"),
            (r'for\s+line\s+in\s+open.*:\s*\n\s+.*append', "Reading and appending lines"),
            (r'\.read\s*\(\s*\).*\.split\s*\(\s*["\']\\n["\']', "read().split() for line iteration"),
        ]

        efficient_patterns = [
            (r'for\s+line\s+in\s+file:', "Direct file iteration"),
            (r'with\s+open.*as\s+\w+:\s*\n\s+for', "Context manager with iteration"),
            (r'\.readline\s*\(\s*\)', "readline() for single line"),
        ]

        lines = content.split('\n')
        has_efficient = any(re.search(p, content) for p in efficient_patterns)

        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//')):
                continue

            for pattern, desc in inefficient_patterns:
                if re.search(pattern, line):
                    if not has_efficient:
                        findings.append({
                            "rule_id": self.rule_id,
                            "severity": self.severity.value,
                            "file": file_path,
                            "line": i,
                            "message": f"Inefficient file read: {desc}",
                            "explanation": "This file reading pattern can be inefficient for large files.",
                            "fix": "Use direct file iteration or readline() for memory efficiency",
                        })
                    break

        return findings
