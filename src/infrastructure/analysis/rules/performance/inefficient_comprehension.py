"""Inefficient list comprehension detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class InefficientComprehensionRule:
    """Detect inefficient list comprehension patterns.

    Some comprehension patterns can be optimized, such as
    nested comprehensions or unnecessary intermediate lists.
    """

    rule_id: str = "PERF005"
    severity: Severity = Severity.LOW

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        inefficient_patterns = [
            (r'\[\s*\w+\s+for\s+\w+\s+in\s+\w+\s+for\s+\w+\s+in\s+\w+\]', 
             "Double nested list comprehension"),
            (r'list\(\s*\[\s*.*\s+for\s+.*\s*\]\s*\)', "Unnecessary list() wrapper"),
            (r'list\(\s*set\(\s*\[', "Unnecessary set() then list()"),
            (r'\[\s*.*\s+for\s+.*\s+if\s+.*\s+==\s*True\s*\]', "Redundant == True check"),
            (r'\[\s*.*\s+for\s+.*\s+if\s+.*\s+==\s*False\s*\]', "Redundant == False check (use 'not')"),
            (r'\[\s*x\s+for\s+x\s+in\s+.*\s+if\s+x\s+not\s+in\s+\[\]', "Membership test against empty list"),
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
                        "message": f"Inefficient comprehension: {desc}",
                        "explanation": "This comprehension pattern can be optimized for better performance.",
                        "fix": "Use generator expressions or more efficient patterns",
                    })
                    break

        return findings
