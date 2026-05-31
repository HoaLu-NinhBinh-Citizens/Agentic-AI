"""Insecure password handling detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class InsecurePasswordRule:
    """Detect insecure password handling.

    Passwords should be hashed, never stored in plaintext,
    and handled securely throughout their lifecycle.
    """

    rule_id: str = "SEC031"
    severity: Severity = Severity.HIGH

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        insecure_patterns = [
            (r'password\s*==\s*["\']', "Plaintext password comparison"),
            (r'if\s+password\s*==', "Password in comparison"),
            (r'User\(.*password\s*=', "Password being set on user object"),
            (r'INSERT\s+INTO.*password.*VALUES', "SQL insert with password"),
            (r'hash\s*=\s*["\']', "Hardcoded password hash"),
            (r'bcrypt\.hashpw.*verify', "Bcrypt password handling"),
            (r'werkzeug\.security\.generate_password_hash', "Werkzeug password hashing"),
        ]

        safe_patterns = [
            (r'werkzeug\.security\.check_password_hash', "Secure password check"),
            (r'bcrypt\.checkpw', "Secure password verification"),
            (r'argon2\.id', "Argon2 password hashing"),
            (r'pbkdf2', "PBKDF2 password hashing"),
        ]

        lines = content.split('\n')
        has_safe_handling = any(re.search(p, content) for p in safe_patterns)

        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//')):
                continue

            for pattern, desc in insecure_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    if not has_safe_handling:
                        findings.append({
                            "rule_id": self.rule_id,
                            "severity": self.severity.value,
                            "file": file_path,
                            "line": i,
                            "message": f"Insecure password: {desc}",
                            "explanation": "Passwords should be hashed using secure algorithms "
                                           "like bcrypt, Argon2, or PBKDF2.",
                            "fix": "Use werkzeug.security or bcrypt for password hashing",
                        })
                    break

        return findings
