"""Type confusion detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class TypeConfusionRule:
    """Detect potential type confusion vulnerabilities.

    Type confusion can occur when different types are
    interchangeably used or compared.
    """

    rule_id: str = "SEC041"
    severity: Severity = Severity.MEDIUM

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        confusion_patterns = [
            (r'==\s*None', "Comparing to None"),
            (r'!=\s*None', "Not-equal None comparison"),
            (r'type\([^)]*\)\s*==', "Type comparison (use isinstance)"),
            (r'is\s+["\']', "String identity comparison"),
            (r'is\s+\d+', "Number identity comparison"),
            (r'if\s+\w+:', "Truthy check on potentially mixed type"),
        ]

        safe_patterns = [
            (r'isinstance\s*\(', "Using isinstance for type checking"),
            (r'is\s+None', "Using 'is None' for None comparison"),
            (r'hasattr\s*\(', "Checking attribute existence"),
        ]

        lines = content.split('\n')
        has_safe = any(re.search(p, content) for p in safe_patterns)

        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//')):
                continue

            for pattern, desc in confusion_patterns:
                if re.search(pattern, line):
                    if 'isinstance' not in line:
                        findings.append({
                            "rule_id": self.rule_id,
                            "severity": self.severity.value,
                            "file": file_path,
                            "line": i,
                            "message": f"Type confusion risk: {desc}",
                            "explanation": "Type comparisons should use proper type checking.",
                            "fix": "Use isinstance() for type checking and 'is None' for None",
                        })
                    break

        return findings
