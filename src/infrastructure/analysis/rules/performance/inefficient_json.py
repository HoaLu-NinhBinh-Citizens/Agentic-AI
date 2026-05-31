"""Inefficient JSON parsing detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class InefficientJSONRule:
    """Detect inefficient JSON parsing patterns.

    Some JSON parsing patterns can be optimized.
    """

    rule_id: str = "PERF026"
    severity: Severity = Severity.LOW

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        inefficient_patterns = [
            (r'json\.loads\s*\(\s*open\([^)]+\)\.read\(\)', "json.loads(open().read()) pattern"),
            (r'json\.loads\s*\(\s*response\.text\s*\)', "Parsing from text when content exists"),
            (r'json\.load\s*\(\s*open\([^)]*,\s*["\']r["\']', "Explicit 'r' mode in open"),
        ]

        efficient_patterns = [
            (r'json\.load\s*\(', "Direct JSON file loading"),
            (r'json\.loads\s*\(', "Direct JSON string loading"),
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
                        "message": f"Inefficient JSON parsing: {desc}",
                        "explanation": "This JSON parsing pattern is inefficient.",
                        "fix": "Use json.load() directly for files",
                    })
                    break

        return findings
