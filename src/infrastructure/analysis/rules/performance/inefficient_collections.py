"""Inefficient collections usage detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class InefficientCollectionsRule:
    """Detect inefficient uses of collections module.

    Some operations can use collections.Counter or
    other optimized data structures.
    """

    rule_id: str = "PERF030"
    severity: Severity = Severity.LOW

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        inefficient_patterns = [
            (r'\{\}\s*for\s+\w+\s+in\s+\w+', "Manual dict from generator"),
            (r'count\s*=\s*\{\}\s*\n\s*for.*\[', "Manual counting pattern"),
            (r'max\s*\(\s*\w+\s+for\s+\w+\s+in\s+\w+\s+if\s+\w+\s*==', "Manual max-by-key pattern"),
        ]

        efficient_patterns = [
            (r'from\s+collections\s+import', "Using collections module"),
            (r'Counter\s*\(', "Using Counter"),
            (r'defaultdict\s*\(', "Using defaultdict"),
            (r'OrderedDict\s*\(', "Using OrderedDict"),
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
                        "message": f"Inefficient collections: {desc}",
                        "explanation": "This pattern can be optimized using collections module.",
                        "fix": "Use Counter, defaultdict, or other optimized structures",
                    })
                    break

        return findings
