"""Race condition detection rule."""

from dataclasses import dataclass
import re
import ast

from src.shared.enums.severity import Severity


@dataclass
class RaceConditionRule:
    """Detect potential race conditions.

    Race conditions occur when multiple threads/processes access
    shared resources in an order-dependent way.
    """

    rule_id: str = "SEC019"
    severity: Severity = Severity.MEDIUM

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        race_patterns = [
            (r'threading\.Lock\s*\(', "Threading lock usage"),
            (r'multiprocessing\.Lock\s*\(', "Multiprocessing lock usage"),
            (r'asyncio\.Lock\s*\(', "Async lock usage"),
            (r'with\s+.*lock', "Lock context manager"),
            (r'file\s*=.*open\s*\(', "File operations (potential race)"),
            (r'os\.rename\s*\(', "Atomic file operation"),
        ]

        check_then_act = []
        lines = content.split('\n')

        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.If):
                    check_then_act.append(node.lineno)
        except SyntaxError:
            pass

        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//')):
                continue

            if re.search(r'if\s+.*:\s*.*\n\s+.*\+\+', line):
                findings.append({
                    "rule_id": self.rule_id,
                    "severity": self.severity.value,
                    "file": file_path,
                    "line": i,
                    "message": "Potential race condition: check-then-act pattern",
                    "explanation": "Check-then-act patterns without synchronization "
                                   "can lead to race conditions.",
                    "fix": "Use atomic operations or proper locking",
                })
                break

        for pattern, desc in race_patterns:
            if re.search(pattern, content):
                findings.append({
                    "rule_id": self.rule_id,
                    "severity": Severity.INFO.value,
                    "file": file_path,
                    "line": 1,
                    "message": f"Concurrency pattern detected: {desc}",
                    "explanation": "Review synchronization patterns for correctness.",
                    "fix": "Ensure locks are acquired in consistent order",
                })
                break

        return findings
