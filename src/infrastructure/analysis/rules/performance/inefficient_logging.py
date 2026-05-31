"""Inefficient logging detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class InefficientLoggingRule:
    """Detect inefficient logging patterns.

    String formatting in logging calls happens even when
    the log level is disabled.
    """

    rule_id: str = "PERF027"
    severity: Severity = Severity.LOW

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        inefficient_patterns = [
            (r'logging\.\w+\s*\(\s*f["\']', "f-string in logging call"),
            (r'logging\.\w+\s*\(\s*["\'].*%s.*["\']', "Percent format in logging"),
            (r'logging\.\w+\s*\(\s*["\'].*\.format\(', ".format() in logging call"),
            (r'logger\.\w+\s*\(\s*f["\']', "f-string in logger call"),
        ]

        efficient_patterns = [
            (r'logger\.\w+\s*\(\s*["\']', "Simple string in logger"),
            (r'logger\.\w+\s*\([^)]*,\s*[^)]+', "Positional args in logger"),
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
                        "message": f"Inefficient logging: {desc}",
                        "explanation": "String formatting in logging happens before level check. "
                                       "Use lazy formatting.",
                        "fix": "Use '%s' % (var,) format or f-string with lazy evaluation",
                    })
                    break

        return findings
