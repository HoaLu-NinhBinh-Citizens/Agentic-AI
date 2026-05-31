"""FastAPI SQL injection and ORM security rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class SQLInjectionORMRule:
    """Detect potential SQL injection and ORM anti-patterns in FastAPI.

    Detects raw SQL execution, unsafe string formatting in queries,
    and N+1 query patterns.
    """

    rule_id: str = "FASTAPI003"
    severity: Severity = Severity.HIGH

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        raw_sql_patterns = [
            (r'execute\s*\(\s*f["\']', "f-string in SQL execute"),
            (r'execute\s*\(\s*["\'].*%s.*["\']', "SQL with % formatting"),
            (r'execute\s*\(\s*["\'].*\.format\(', "SQL with .format()"),
            (r'cursor\.execute\s*\(\s*f', "f-string in cursor.execute"),
            (r'raw\s*\(\s*f["\']', "f-string in raw query"),
            (r'text\s*\(\s*f["\']', "f-string in text() SQL"),
        ]

        orm_n_plus_one = [
            (r'for\s+\w+\s+in\s+\w+\.all\(\)[\s\n]+.*\.filter|for\s+\w+\s+in\s+\w+\.all\(\)[\s\n]+.*\.query',
             "N+1 query pattern with .all() in loop"),
        ]

        lines = content.split('\n')
        
        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//')):
                continue

            for pattern, desc in raw_sql_patterns:
                if re.search(pattern, line):
                    findings.append({
                        "rule_id": self.rule_id,
                        "severity": self.severity.value,
                        "file": file_path,
                        "line": i,
                        "message": f"Potential SQL injection: {desc}",
                        "explanation": "Using string formatting (f-strings, %, .format) in SQL queries "
                                       "can lead to SQL injection attacks.",
                        "fix": "Use parameterized queries: execute('SELECT * FROM users WHERE id = ?', [id])",
                    })

            for pattern, desc in orm_n_plus_one:
                if re.search(pattern, line, re.DOTALL):
                    findings.append({
                        "rule_id": self.rule_id,
                        "severity": self.severity.value,
                        "file": file_path,
                        "line": i,
                        "message": f"ORM anti-pattern: {desc}",
                        "explanation": "N+1 queries occur when you fetch all records then filter/query each one.",
                        "fix": "Use database-level filtering: Model.query.filter_by(category=cat).first()",
                    })

        return findings
