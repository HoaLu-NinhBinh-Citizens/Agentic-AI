"""Unnecessary len() check detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class UnnecessaryLenCheckRule:
    """Detect unnecessary len() checks.

    Checking len() > 0 when truthiness would suffice,
    or len() == 0 when not X would suffice.
    """

    rule_id: str = "PERF022"
    severity: Severity = Severity.LOW

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        unnecessary_patterns = [
            (r'if\s+len\s*\([^)]+\)\s*>\s*0\s*:', "len() > 0 check (use truthiness)"),
            (r'if\s+len\s*\([^)]+\)\s*!=\s*0\s*:', "len() != 0 check (use truthiness)"),
            (r'if\s+not\s+len\s*\([^)]+\)\s*:\s*:', "not len() check"),
            (r'if\s+len\s*\([^)]+\)\s*==\s*0\s*:', "len() == 0 check (use 'not')"),
            (r'while\s+len\s*\([^)]+\)\s*>\s*0\s*:', "len() > 0 in while"),
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
                        "message": f"Unnecessary len() check: {desc}",
                        "explanation": "len() checks can be replaced with truthiness checks.",
                        "fix": "Use 'if items:' instead of 'if len(items) > 0:'",
                    })
                    break

        return findings
