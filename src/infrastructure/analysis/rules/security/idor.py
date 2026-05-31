"""Insecure Direct Object Reference (IDOR) detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class IDORRule:
    """Detect Insecure Direct Object Reference (IDOR) vulnerabilities.

    IDOR occurs when an application exposes internal object references
    without proper authorization checks.
    """

    rule_id: str = "SEC018"
    severity: Severity = Severity.HIGH

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        idor_patterns = [
            (r'/user/\d+', "Direct user ID reference in URL"),
            (r'/order/\d+', "Direct order ID reference in URL"),
            (r'/product/\d+', "Direct product ID reference in URL"),
            (r'/api/v\d+/users/\d+', "Direct user ID in API endpoint"),
            (r'request\.args\.get\(["\']id["\']\)', "Unvalidated ID parameter"),
            (r'request\.form\.get\(["\']id["\']\)', "Unvalidated form ID parameter"),
            (r'User\.query\.get\([^)]+\)', "Direct database lookup by ID"),
            (r'\.get_by_id\([^)]+\)', "Direct object retrieval without auth check"),
        ]

        auth_check_patterns = [
            (r'@login_required', "Login required decorator"),
            (r'@requires_auth', "Authentication required decorator"),
            (r'check_permission', "Permission check function"),
            (r'verify_ownership', "Ownership verification"),
            (r'authorize', "Authorization check"),
            (r'is_authorized', "Authorization check"),
            (r'@permission_required', "Permission required decorator"),
        ]

        lines = content.split('\n')
        has_auth = False

        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//')):
                continue

            for pattern, _ in auth_check_patterns:
                if re.search(pattern, line):
                    has_auth = True
                    break

        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//')):
                continue

            for pattern, desc in idor_patterns:
                if re.search(pattern, line):
                    if not has_auth:
                        findings.append({
                            "rule_id": self.rule_id,
                            "severity": self.severity.value,
                            "file": file_path,
                            "line": i,
                            "message": f"IDOR risk: {desc}",
                            "explanation": "Direct object references without authorization "
                                           "checks can allow unauthorized access.",
                            "fix": "Add ownership verification or permission checks",
                        })
                    break

        return findings
