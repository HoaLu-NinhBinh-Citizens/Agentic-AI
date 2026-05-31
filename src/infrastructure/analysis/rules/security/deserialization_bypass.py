"""Deserialization bypass detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class DeserializationBypassRule:
    """Detect insecure deserialization patterns.

    Insecure deserialization can lead to authentication bypass,
    privilege escalation, or remote code execution.
    """

    rule_id: str = "SEC013"
    severity: Severity = Severity.CRITICAL

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        bypass_patterns = [
            (r'__reduce__\s*\(', "__reduce__ can enable pickle exploitation"),
            (r'__setstate__', "Custom unpickling logic detected"),
            (r'__getstate__', "Custom pickling logic detected"),
            (r'object_hook\s*=', "Custom object hook in JSON (potential risk)"),
            (r'parse_object\s*=', "Custom parse object in JSON"),
            (r'object_pairs_hook\s*=', "Custom object pairs hook"),
        ]

        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//')):
                continue

            for pattern, desc in bypass_patterns:
                if re.search(pattern, line):
                    findings.append({
                        "rule_id": self.rule_id,
                        "severity": self.severity.value,
                        "file": file_path,
                        "line": i,
                        "message": f"Deserialization risk: {desc}",
                        "explanation": "Custom serialization hooks can be exploited "
                                       "to bypass security controls.",
                        "fix": "Validate all input, use digital signatures, "
                               "or restrict deserialization to trusted sources",
                    })
                    break

        return findings
