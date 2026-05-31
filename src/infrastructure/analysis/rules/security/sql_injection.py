"""SQL Injection detection rule."""

from dataclasses import dataclass
from typing import Optional
import re

from src.shared.enums.severity import Severity


SQL_INJECTION_PATTERNS = [
    r'f["\'].*?\{[^}]+\}.*?(SELECT|INSERT|UPDATE|DELETE|DROP|EXEC)',
    r'["\'].*?(SELECT|INSERT|UPDATE|DELETE).*?["\'].*\+',
    r'["\'].*?(SELECT|INSERT|UPDATE|DELETE).*?["\'].*\.format\(',
    r'cursor\.execute\(f["\']',
    r'r["\'].*?(SELECT|INSERT|UPDATE|DELETE).*?["\'].*\%',
]

SQL_SAFE_PATTERNS = [
    r'cursor\.execute\([^,]+\s*,\s*\([^)]+\)',
    r'\$\d+',
    r'%s',
    r'\?',
    r'["\']params["\']\s*:',
]


@dataclass
class SQLInjectionRule:
    """Detect SQL injection vulnerabilities.
    
    SQL injection occurs when user input is directly concatenated into SQL queries
    without proper parameterization.
    """

    rule_id: str = "SEC001"
    severity: Severity = Severity.CRITICAL

    def detect(self, content: str, file_path: str) -> list[dict]:
        """Detect SQL injection vulnerabilities in source code.

        Args:
            content: Source code content
            file_path: Path to source file

        Returns:
            List of finding dictionaries
        """
        findings = []

        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            if self._is_safe_line(line):
                continue

            for pattern in SQL_INJECTION_PATTERNS:
                if re.search(pattern, line, re.IGNORECASE):
                    findings.append({
                        "rule_id": self.rule_id,
                        "severity": self.severity.value,
                        "file": file_path,
                        "line": i,
                        "message": "Potential SQL injection vulnerability",
                        "explanation": "User input appears to be directly concatenated "
                                       "into SQL query. Use parameterized queries instead.",
                        "fix": "cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))",
                    })
                    break

        return findings

    def _is_safe_line(self, line: str) -> bool:
        """Check if line contains safe SQL patterns."""
        return any(re.search(p, line) for p in SQL_SAFE_PATTERNS)
