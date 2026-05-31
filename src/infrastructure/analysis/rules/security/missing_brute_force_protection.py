"""Brute force protection missing detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class MissingBruteForceProtectionRule:
    """Detect missing brute force protection.

    Login endpoints should have rate limiting or
    account lockout to prevent brute force attacks.
    """

    rule_id: str = "SEC036"
    severity: Severity = Severity.MEDIUM

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        login_patterns = [
            (r'login', "Login functionality"),
            (r'authenticate', "Authentication function"),
            (r'sign.?in', "Sign in functionality"),
            (r'/auth/login', "Login endpoint"),
            (r'/api/login', "API login endpoint"),
        ]

        protection_patterns = [
            (r'rate_limit', "Rate limiting"),
            (r'@limiter', "Rate limiter decorator"),
            (r'time.sleep', "Intentional delay"),
            (r'bcrypt\.checkpw', "Secure password check (with timing)"),
            (r'check_password_hash', "Secure password verification"),
            (r'Account.*lock', "Account lockout mechanism"),
            (r'max_attempts', "Max attempts check"),
            (r'failed_login', "Failed login tracking"),
        ]

        lines = content.split('\n')
        has_login = any(re.search(p, content, re.IGNORECASE) for p in login_patterns)
        has_protection = any(re.search(p, content, re.IGNORECASE) for p in protection_patterns)

        if has_login and not has_protection:
            findings.append({
                "rule_id": self.rule_id,
                "severity": self.severity.value,
                "file": file_path,
                "line": 1,
                "message": "Missing brute force protection",
                "explanation": "Login endpoints should have rate limiting, delays, or "
                               "account lockout to prevent brute force attacks.",
                "fix": "Add rate limiting, login attempt tracking, or account lockout",
            })

        return findings
