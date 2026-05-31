"""Inefficient loop variable detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class InefficientLoopVarRule:
    """Detect inefficient loop variable usage.

    Using range(len()) instead of enumerate() or
    iterating directly over containers.
    """

    rule_id: str = "PERF017"
    severity: Severity = Severity.LOW

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        inefficient_patterns = [
            (r'for\s+\w+\s+in\s+range\s*\(\s*len\s*\(', "range(len()) pattern"),
            (r'for\s+\w+\s+in\s+range\s*\(\s*len\s*\([^)]+\)\s*\)\s*:\s*\n\s+.*\w+\[\w+\]', "Index-based loop"),
            (r'for\s+\w+\s+in\s+range\s*\(\s*len\s*\([^)]+\)\s*\)\s*:\s*\n\s+.*\.append', "Loop with append pattern"),
        ]

        efficient_patterns = [
            (r'for\s+\w+\s+in\s+enumerate\s*\(', "Using enumerate"),
            (r'for\s+\w+\s*,\s*\w+\s+in\s+enumerate\s*\(', "Using enumerate with index"),
            (r'for\s+\w+\s+in\s+\w+\.items\s*\(', "Using dict.items()"),
            (r'for\s+\w+\s+in\s+\w+\.values\s*\(', "Using dict.values()"),
            (r'for\s+\w+\s+in\s+\w+\.keys\s*\(', "Using dict.keys()"),
        ]

        lines = content.split('\n')
        has_efficient = any(re.search(p, content) for p in efficient_patterns)

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
                        "message": f"Inefficient loop: {desc}",
                        "explanation": "This loop pattern is less efficient than alternatives.",
                        "fix": "Use enumerate() for index access or iterate directly",
                    })
                    break

        return findings
