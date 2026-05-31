"""Cookie security issues detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class CookieSecurityRule:
    """Detect insecure cookie configuration.

    Cookies should have proper security flags set to prevent
    XSS, CSRF, and session hijacking attacks.
    """

    rule_id: str = "SEC016"
    severity: Severity = Severity.HIGH

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        cookie_patterns = [
            (r'set_cookie\s*\(', "Cookie being set"),
            (r'response\.set_cookie', "Response cookie being set"),
            (r'set_cookie\s*\([^)]*secure\s*=\s*False', "Cookie without secure flag"),
            (r'set_cookie\s*\([^)]*httponly\s*=\s*False', "Cookie without httponly flag"),
            (r'set_cookie\s*\([^)]*samesite\s*=', "SameSite cookie attribute"),
        ]

        lines = content.split('\n')
        has_cookie = False
        has_secure = False
        has_httponly = False
        has_samesite = False

        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//')):
                continue

            if re.search(r'set_cookie\s*\(', line):
                has_cookie = True

            if 'secure=True' in line or 'secure = True' in line:
                has_secure = True

            if 'httponly=True' in line or 'httponly = True' in line:
                has_httponly = True

            if 'samesite' in line.lower():
                has_samesite = True

        if has_cookie:
            if not has_secure:
                findings.append({
                    "rule_id": self.rule_id,
                    "severity": self.severity.value,
                    "file": file_path,
                    "line": 1,
                    "message": "Cookie without secure flag",
                    "explanation": "Cookies should have the Secure flag to ensure "
                                   "they are only sent over HTTPS.",
                    "fix": "Add secure=True to set_cookie()",
                })
            if not has_httponly:
                findings.append({
                    "rule_id": self.rule_id,
                    "severity": self.severity.value,
                    "file": file_path,
                    "line": 1,
                    "message": "Cookie without HttpOnly flag",
                    "explanation": "HttpOnly prevents JavaScript access to cookies, "
                                   "mitigating XSS attacks.",
                    "fix": "Add httponly=True to set_cookie()",
                })
            if not has_samesite:
                findings.append({
                    "rule_id": self.rule_id,
                    "severity": Severity.MEDIUM.value,
                    "file": file_path,
                    "line": 1,
                    "message": "Cookie without SameSite attribute",
                    "explanation": "SameSite prevents CSRF attacks by controlling "
                                   "when cookies are sent with cross-site requests.",
                    "fix": "Add samesite='Lax' or samesite='Strict' to set_cookie()",
                })

        return findings
