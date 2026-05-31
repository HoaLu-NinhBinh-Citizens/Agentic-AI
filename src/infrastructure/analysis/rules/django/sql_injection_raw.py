"""Django raw SQL injection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class RawSQLRule:
    """Detect raw SQL queries in Django that may be vulnerable to injection.

    Raw SQL with string formatting allows SQL injection attacks.
    Always use parameterized queries or the ORM.
    """

    rule_id: str = "DJANGO001"
    severity: Severity = Severity.HIGH

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        raw_sql_patterns = [
            (r'cursor\.execute\s*\(\s*f["\']', "f-string in cursor.execute"),
            (r'cursor\.execute\s*\(\s*["\'].*%s.*["\']', "SQL with % formatting"),
            (r'cursor\.execute\s*\(\s*["\'].*\.format\(', "SQL with .format()"),
            (r'\braw\s*\(\s*sql\s*=', "Django .raw() with interpolated SQL"),
            (r'connection\.cursor\(\)\.execute\s*\(\s*f', "f-string in connection.cursor execute"),
            (r'from django\.db import connection[\s\S]*?\.execute\s*\(\s*f', "f-string in raw SQL"),
            (r'\.extra\s*\(\s*where\s*=', "Django .extra() with raw where clause"),
        ]

        has_django = 'django' in content.lower() or 'from django' in content

        if not has_django:
            return findings

        lines = content.split('\n')

        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//', '#')):
                continue

            for pattern, desc in raw_sql_patterns:
                if re.search(pattern, line, re.DOTALL):
                    findings.append({
                        "rule_id": self.rule_id,
                        "severity": self.severity.value,
                        "file": file_path,
                        "line": i,
                        "message": f"Raw SQL detected: {desc}",
                        "explanation": "Raw SQL with string formatting is vulnerable to SQL injection. "
                                       "User input can manipulate the query structure.",
                        "fix": "Use parameterized queries: cursor.execute('SELECT * FROM x WHERE id=%s', [id]) "
                               "or use Django ORM: Model.objects.filter(id=id)",
                    })

        return findings
