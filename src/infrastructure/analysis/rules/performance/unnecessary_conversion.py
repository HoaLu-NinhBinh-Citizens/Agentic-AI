"""Unnecessary type conversion detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class UnnecessaryConversionRule:
    """Detect unnecessary type conversions.

    Some conversions are redundant because the value
    is already of the target type.
    """

    rule_id: str = "PERF011"
    severity: Severity = Severity.LOW

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        redundant_patterns = [
            (r'str\(\s*["\'][\w]+["\']\s*\)', "str() on string literal"),
            (r'int\(\s*\d+\s*\)', "int() on integer literal"),
            (r'float\(\s*\d+\.?\d*\s*\)', "float() on float literal"),
            (r'list\(\s*\[[\s\S]*\]\s*\)', "list() on list literal"),
            (r'list\(\s*"\w+"\s*\)', "list() on single string"),
            (r'tuple\(\s*\([^)]+\)\s*\)', "tuple() on tuple literal"),
            (r'dict\(\s*\{[^}]+\}\s*\)', "dict() on dict literal"),
        ]

        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//')):
                continue

            for pattern, desc in redundant_patterns:
                if re.search(pattern, line):
                    findings.append({
                        "rule_id": self.rule_id,
                        "severity": self.severity.value,
                        "file": file_path,
                        "line": i,
                        "message": f"Unnecessary conversion: {desc}",
                        "explanation": "This type conversion is redundant.",
                        "fix": "Remove the unnecessary conversion",
                    })
                    break

        return findings
