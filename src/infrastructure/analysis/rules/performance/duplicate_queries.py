"""Duplicate database queries detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class DuplicateQueriesRule:
    """Detect duplicate database query patterns.

    The same query executed multiple times wastes database resources.
    Cache results or use query batching.
    """

    rule_id: str = "PERF007"
    severity: Severity = Severity.MEDIUM

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        query_patterns = [
            (r'\.query\.filter\(', "ORM query"),
            (r'\.filter_by\(', "Django ORM filter"),
            (r'\.get\(', "Model get"),
            (r'\.all\(\)', "Query all"),
            (r'\.first\(\)', "Query first"),
            (r'execute\s*\(', "Raw SQL execute"),
            (r'cursor\.execute', "Database cursor execute"),
        ]

        lines = content.split('\n')
        query_lines = []

        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//')):
                continue

            for pattern, _ in query_patterns:
                if re.search(pattern, line):
                    query_lines.append((i, line.strip()))

        seen_queries = {}
        for lineno, query in query_lines:
            if query in seen_queries:
                prev_lineno = seen_queries[query]
                findings.append({
                    "rule_id": self.rule_id,
                    "severity": self.severity.value,
                    "file": file_path,
                    "line": lineno,
                    "message": f"Duplicate query (same as line {prev_lineno})",
                    "explanation": "The same query is executed multiple times. "
                                   "Cache the result or execute once.",
                    "fix": "Store query result in variable and reuse",
                })
            else:
                seen_queries[query] = lineno

        return findings
