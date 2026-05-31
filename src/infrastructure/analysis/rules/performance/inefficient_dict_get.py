"""Inefficient dict.get() usage detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class InefficientDictGetRule:
    """Detect inefficient dict.get() usage patterns.

    Some dict.get() patterns can be simplified using
    defaultdict or setdefault.
    """

    rule_id: str = "PERF023"
    severity: Severity = Severity.LOW

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        inefficient_patterns = [
            (r'if\s+\w+\s+not\s+in\s+\w+:\s*\n\s+\w+\[\w+\]\s*=', "Check then set pattern"),
            (r'if\s+\w+\s+in\s+\w+:\s*\n\s+\w+\s*=\s+\w+\[\w+\]\s*\n\s+else:\s*\n\s+\w+\s*=', "Get or set pattern"),
            (r'\{[^}]+\}\.get\([^)]*None\)[^)]', "get() with None default (use setdefault)"),
            (r'\{\}.*\.setdefault', "setdefault without defaultdict"),
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
                        "message": f"Inefficient dict pattern: {desc}",
                        "explanation": "This dict pattern can be simplified using defaultdict or setdefault.",
                        "fix": "Use defaultdict for automatic initialization",
                    })
                    break

        return findings
