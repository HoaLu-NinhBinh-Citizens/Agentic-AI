"""Missing authentication check detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class MissingAuthCheckRule:
    """Detect routes/endpoints without authentication checks.

    Protected endpoints should verify user authentication
    before processing requests.
    """

    rule_id: str = "SEC039"
    severity: Severity = Severity.HIGH

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        protected_patterns = [
            (r'/admin', "Admin endpoint"),
            (r'/api/v\d+/users', "User API endpoint"),
            (r'/dashboard', "Dashboard endpoint"),
            (r'/settings', "Settings endpoint"),
            (r'/profile', "Profile endpoint"),
            (r'/password', "Password endpoint"),
            (r'/account', "Account endpoint"),
            (r'/data/export', "Data export endpoint"),
        ]

        auth_patterns = [
            (r'@login_required', "Login required decorator"),
            (r'@requires_auth', "Authentication required"),
            (r'@auth\.required', "Auth required decorator"),
            (r'check_session', "Session check"),
            (r'if.*session.*get.*user', "Manual session check"),
            (r'current_user', "Current user access"),
            (r'@token_required', "Token required decorator"),
            (r'verify_token', "Token verification"),
        ]

        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//')):
                continue

            for pattern, desc in protected_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    has_auth = False
                    for auth_pattern in auth_patterns:
                        if re.search(auth_pattern, content, re.IGNORECASE):
                            has_auth = True
                            break

                    if not has_auth:
                        findings.append({
                            "rule_id": self.rule_id,
                            "severity": self.severity.value,
                            "file": file_path,
                            "line": i,
                            "message": f"Missing auth on protected route: {desc}",
                            "explanation": "This protected endpoint does not appear to have "
                                           "authentication checks.",
                            "fix": "Add @login_required or authentication decorator",
                        })
                    break

        return findings
