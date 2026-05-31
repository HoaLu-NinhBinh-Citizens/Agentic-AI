"""Yield vs return detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class YieldVsReturnRule:
    """Detect return in generator function that could use yield.

    Returning a list in a loop instead of yielding is memory-inefficient.
    """

    rule_id: str = "PERF014"
    severity: Severity = Severity.LOW

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        return_in_loop_patterns = [
            (r'def\s+\w+\([^)]*\):\s*\n\s*.*result\s*=\s*\[\s*\n\s*.*for\s+.*\n\s*.*return\s+result',
             "Return collected list pattern"),
            (r'for\s+.*:\s*\n\s*.*results\.append', "Collecting results to return"),
            (r'Results\s*=\s*\[\s*\n\s*.*for\s+.*\n\s*return\s+Results', "List comprehension then return"),
        ]

        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//')):
                continue

            if 'return' in line and '[' in line:
                findings.append({
                    "rule_id": self.rule_id,
                    "severity": self.severity.value,
                    "file": file_path,
                    "line": i,
                    "message": "Potential yield opportunity",
                    "explanation": "Collecting results in a list to return wastes memory. "
                                   "Yielding items creates a generator that's more memory-efficient.",
                    "fix": "Use yield instead of collecting results in a list",
                })

        return findings
