"""Django N+1 query and missing select_related rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class SelectRelatedRule:
    """Detect N+1 query patterns in Django due to missing select_related.

    N+1 queries occur when accessing foreign keys in loops, causing
    one query per iteration instead of efficient joins.
    """

    rule_id: str = "DJANGO008"
    severity: Severity = Severity.MEDIUM

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        n_plus_one_patterns = [
            (r'for\s+\w+\s+in\s+\w+\.objects\.all\(\)[\s\n]+.*\.', "QuerySet.all() in loop with access"),
            (r'for\s+\w+\s+in\s+\w+\.filter\([^)]+\)\s*:[\s\n]+.*\.', "QuerySet.filter() in loop"),
            (r'for\s+\w+\s+in\s+\w+\.all\(\)\.filter', "Chained filter on all()"),
            (r'QuerySet\.all\(\)[\s\n]+for', "QuerySet iteration without prefetch"),
        ]

        select_related_patterns = [
            (r'\.select_related\s*\(', "select_related() used"),
            (r'\.prefetch_related\s*\(', "prefetch_related() used"),
            (r'Prefetch\s*\(', "Prefetch() object used"),
        ]

        foreign_key_access = [
            (r'\.\w+\.objects\.', "Accessing related object's manager"),
            (r'\.\w+\.filter', "Filtering on foreign key"),
            (r'\.\w+\.all\(\)', "Accessing all related objects"),
        ]

        has_django = 'django' in content.lower() or 'from django' in content

        if not has_django:
            return findings

        lines = content.split('\n')

        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//')):
                continue

            for pattern, desc in n_plus_one_patterns:
                if re.search(pattern, line, re.DOTALL):
                    next_lines = '\n'.join(lines[i:min(i+20, len(lines))])

                    has_prefetch = any(re.search(p, next_lines) for p in select_related_patterns)
                    has_fk_access = any(re.search(p, next_lines) for p in foreign_key_access)

                    if has_fk_access and not has_prefetch:
                        findings.append({
                            "rule_id": self.rule_id,
                            "severity": self.severity.value,
                            "file": file_path,
                            "line": i,
                            "message": f"N+1 query pattern: {desc}",
                            "explanation": "Accessing foreign keys in loops without select_related/prefetch_related "
                                           "causes one database query per iteration.",
                            "fix": "Use: Model.objects.select_related('foreign_key').all() "
                                   "or .prefetch_related('related_set')",
                        })

        return findings
