"""Django unnecessary QuerySet.all() usage rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class QuerySetAllRule:
    """Detect unnecessary .all() calls in Django queries.

    .all() is often redundant and can be simplified.
    Also detects inefficient patterns that load all objects unnecessarily.
    """

    rule_id: str = "DJANGO010"
    severity: Severity = Severity.LOW

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        unnecessary_all_patterns = [
            (r'\.all\(\)\.filter\s*\(', "Redundant .all() before .filter()"),
            (r'\.all\(\)\.exclude\s*\(', "Redundant .all() before .exclude()"),
            (r'\.all\(\)\.order_by\s*\(', "Redundant .all() before .order_by()"),
            (r'\.all\(\)\.values\s*\(', "Redundant .all() before .values()"),
            (r'\.all\(\)\.values_list\s*\(', "Redundant .all() before .values_list()"),
            (r'\.all\(\)\.first\s*\(', "Redundant .all() before .first()"),
            (r'\.all\(\)\.last\s*\(', "Redundant .all() before .last()"),
            (r'\.all\(\)\.count\s*\(', "Redundant .all() before .count()"),
            (r'\.all\(\)\.exists\s*\(', "Redundant .all() before .exists()"),
            (r'Model\.objects\.all\(\)\.filter\s*\(', "Full path with unnecessary .all()"),
        ]

        all_in_loop_patterns = [
            (r'for\s+.*\s+in\s+.*\.all\(\)\s*:', ".all() in for loop header"),
            (r'list\s*\(\s*.*\.all\(\)\s*\)', "list() wrapping .all() unnecessarily"),
        ]

        has_django = 'django' in content.lower() or 'from django' in content

        if not has_django:
            return findings

        lines = content.split('\n')

        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//')):
                continue

            for pattern, desc in unnecessary_all_patterns:
                if re.search(pattern, line):
                    findings.append({
                        "rule_id": self.rule_id,
                        "severity": self.severity.value,
                        "file": file_path,
                        "line": i,
                        "message": f"Unnecessary .all(): {desc}",
                        "explanation": ".all() is redundant before chaining other QuerySet methods. "
                                       "Django QuerySets are lazy.",
                        "fix": "Remove .all(): use .filter() directly instead of .all().filter()",
                    })

            for pattern, desc in all_in_loop_patterns:
                if re.search(pattern, line):
                    findings.append({
                        "rule_id": self.rule_id,
                        "severity": self.severity.value,
                        "file": file_path,
                        "line": i,
                        "message": f"Inefficient query: {desc}",
                        "explanation": "Using .all() in loops loads all objects into memory at once. "
                                       "Use the QuerySet directly for lazy evaluation.",
                        "fix": "Iterate directly: for obj in Model.objects.filter(...): "
                               "or use iterator(): for obj in qs.iterator():",
                    })

        return findings
