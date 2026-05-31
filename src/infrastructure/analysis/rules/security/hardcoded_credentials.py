"""Hardcoded credentials detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class HardcodedCredentialsRule:
    """Detect hardcoded credentials in source code.

    Credentials should never be stored in source code.
    Use environment variables, config files, or secret vaults.
    """

    rule_id: str = "SEC014"
    severity: Severity = Severity.CRITICAL

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        credential_patterns = [
            (r'username\s*=\s*["\'][^"\']{2,}', "Hardcoded username"),
            (r'user\s*=\s*["\'][^"\']{2,}', "Hardcoded username"),
            (r'login\s*=\s*["\'][^"\']{2,}', "Hardcoded login"),
            (r'connection_string\s*=\s*["\'][^"\']+', "Hardcoded connection string"),
            (r'conn_str\s*=\s*["\'][^"\']+', "Hardcoded connection string"),
            (r'db_pass\s*=\s*["\'][^"\']+', "Hardcoded database password"),
            (r'database_password\s*=\s*["\'][^"\']+', "Hardcoded database password"),
            (r'sqlite:///[^"\']+', "Hardcoded SQLite path with credentials"),
            (r'mysql://[^:]+:[^@]+@', "Hardcoded MySQL credentials"),
            (r'postgresql://[^:]+:[^@]+@', "Hardcoded PostgreSQL credentials"),
        ]

        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith(('#', '//')):
                continue

            if self._is_allowed_context(stripped):
                continue

            for pattern, desc in credential_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    findings.append({
                        "rule_id": self.rule_id,
                        "severity": self.severity.value,
                        "file": file_path,
                        "line": i,
                        "message": f"Hardcoded credential: {desc}",
                        "explanation": "Hardcoded credentials can be extracted from source code "
                                       "and used for unauthorized access.",
                        "fix": "Use os.getenv('CREDENTIAL_NAME') or a secret management service",
                    })
                    break

        return findings

    def _is_allowed_context(self, line: str) -> bool:
        allowed = ['test', 'mock', 'example', 'dummy', 'placeholder', 'xxx',
                   'TODO', 'CHANGEME', 'FIXME', 'stub', 'dummy']
        line_lower = line.lower()
        return any(a in line_lower for a in allowed)
