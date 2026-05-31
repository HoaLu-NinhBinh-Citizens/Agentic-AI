"""Multiple comparisons optimization detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class MultipleComparisonsRule:
    """Detect multiple comparisons that can be optimized.

    Using 'in' with tuple or set is faster than
    chained comparisons.
    """

    rule_id: str = "PERF018"
    severity: Severity = Severity.LOW

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        inefficient_patterns = [
            (r'\w+\s*==\s*\w+\s*or\s+\w+\s*==\s*\w+\s*or\s+\w+\s*==', "Chained equality comparisons"),
            (r'\w+\s*!=\s*\w+\s*and\s+\w+\s*!=\s*\w+\s*and', "Multiple inequality checks"),
            (r'if\s+\w+\s*==\s*\w+\s+or\s+\w+\s*==\s*\w+\s+or\s+\w+\s*==', "Chained comparisons in if"),
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
                        "message": f"Multiple comparisons: {desc}",
                        "explanation": "Chained comparisons can be optimized using 'in' with a tuple/set.",
                        "fix": "Use 'x in (a, b, c)' instead of 'x == a or x == b or x == c'",
                    })
                    break

        return findings
