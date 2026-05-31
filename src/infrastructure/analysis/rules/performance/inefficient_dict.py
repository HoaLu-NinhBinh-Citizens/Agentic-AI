"""Inefficient dictionary operations detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class InefficientDictRule:
    """Detect inefficient dictionary operations.

    Some dictionary operations can be optimized for better performance.
    """

    rule_id: str = "PERF012"
    severity: Severity = Severity.LOW

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        inefficient_patterns = [
            (r'\.has_key\(', "dict.has_key() is deprecated"),
            (r'\.keys\(\)\.index\(', "Using index() on dict keys"),
            (r'\.values\(\)\.index\(', "Using index() on dict values"),
            (r'\.items\(\)\.index\(', "Using index() on dict items"),
            (r'\[\s*\w+\]\s*if\s+\w+\s+in\s+\w+\s+else\s+None', "Manual dict.get() pattern"),
            (r'if\s+\w+\s+in\s+\w+:\s*\n\s+\w+\[', "Check before dict access"),
            (r'dict\(kwargs\)\.get', "Redundant dict() call before get()"),
        ]

        efficient_patterns = [
            (r'\.get\(', "Using dict.get()"),
            (r'\.setdefault\(', "Using dict.setdefault()"),
            (r'\.defaultdict', "Using defaultdict"),
            (r'\.update\(', "Using dict.update()"),
        ]

        lines = content.split('\n')
        has_efficient = any(re.search(p, content) for p in efficient_patterns)

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
                        "message": f"Inefficient dict operation: {desc}",
                        "explanation": "This dictionary operation can be optimized.",
                        "fix": "Use dict.get() or defaultdict instead",
                    })
                    break

        return findings
