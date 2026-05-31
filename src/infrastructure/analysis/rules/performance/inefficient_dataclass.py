"""Inefficient dataclass fields detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class InefficientDataclassRule:
    """Detect inefficient dataclass usage.

    Some dataclass patterns can be optimized.
    """

    rule_id: str = "PERF024"
    severity: Severity = Severity.LOW

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        inefficient_patterns = [
            (r'@dataclass\s*\n\s*class\s+\w+\([^)]*\):', "Dataclass with __init__ override"),
            (r'def\s+__init__\s*\(self.*\):\s*\n\s+super\(\).__init__', "Init that just calls super"),
            (r'def\s+__repr__\s*\(self.*\):\s*\n\s+return', "Manual __repr__ in dataclass"),
            (r'field\s*\(\s*default_factory\s*=\s*list\s*\)', "field(default_factory=list) could use list field"),
        ]

        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//')):
                continue

            for pattern, desc in inefficient_patterns:
                if re.search(pattern, line, re.MULTILINE):
                    findings.append({
                        "rule_id": self.rule_id,
                        "severity": self.severity.value,
                        "file": file_path,
                        "line": i,
                        "message": f"Inefficient dataclass: {desc}",
                        "explanation": "This dataclass pattern can be simplified.",
                        "fix": "Use dataclass features properly",
                    })
                    break

        return findings
