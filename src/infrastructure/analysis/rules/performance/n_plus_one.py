"""N+1 query problem detection rule."""

from dataclasses import dataclass
import re
import ast

from src.shared.enums.severity import Severity


@dataclass
class NPlusOneRule:
    """Detect N+1 query patterns in database operations.

    N+1 queries occur when fetching a list of items, then making
    a database query for each item separately.
    """

    rule_id: str = "PERF002"
    severity: Severity = Severity.HIGH

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        n_plus_one_patterns = [
            (r'for\s+\w+\s+in\s+\w+:\s*\n\s+.*\.query\.', "Query in loop pattern"),
            (r'for\s+\w+\s+in\s+\w+:\s*\n\s+.*\.get\(', "Database get in loop"),
            (r'for\s+\w+\s+in\s+\w+:\s*\n\s+.*\.filter\(', "Filter in loop"),
            (r'for\s+\w+\s+in\s+\w+:\s*\n\s+.*\.all\(', "Query all in loop"),
        ]

        eager_loading_patterns = [
            (r'\.select_related', "Eager loading via select_related"),
            (r'\.prefetch_related', "Eager loading via prefetch_related"),
            (r'joinedload', "Eager loading in SQLAlchemy"),
            (r'subqueryload', "Subquery eager loading"),
            (r'\.include\([\'"]', "Eager loading include"),
            (r'JOIN\s+', "SQL JOIN statement"),
        ]

        lines = content.split('\n')
        has_eager_loading = False

        for line in lines:
            for pattern, _ in eager_loading_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    has_eager_loading = True
                    break

        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//')):
                continue

            for pattern, desc in n_plus_one_patterns:
                if re.search(pattern, line, re.MULTILINE):
                    if not has_eager_loading:
                        findings.append({
                            "rule_id": self.rule_id,
                            "severity": self.severity.value,
                            "file": file_path,
                            "line": i,
                            "message": f"N+1 query problem: {desc}",
                            "explanation": "Making database queries inside loops causes N+1 problem. "
                                           "Fetch all data in one query with JOIN or eager loading.",
                            "fix": "Use JOIN, select_related(), or prefetch_related()",
                        })
                    break

        return findings
