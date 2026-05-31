"""CSRF vulnerability detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class CSRFRule:
    """Detect missing CSRF protection.

    Cross-Site Request Forgery (CSRF) allows attackers to perform
    actions on behalf of authenticated users.
    """

    rule_id: str = "SEC017"
    severity: Severity = Severity.HIGH

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        csrf_protection_patterns = [
            (r'@csrf_exempt', "CSRF exemption detected"),
            (r'csrf_exempt\s*=', "CSRF exemption in class-based view"),
            (r'django.views.decorators.csrf', "Django CSRF decorators"),
            (r'ensure_csrf_cookie', "CSRF cookie enforcement"),
            (r'@app.route.*methods.*POST', "POST route without CSRF protection"),
            (r'requestVerificationToken', "Anti-CSRF token pattern"),
            (r'_csrf_token', "CSRF token field pattern"),
            (r'csrf_token', "CSRF token reference"),
        ]

        post_forms = []
        has_csrf_protection = False
        lines = content.split('\n')

        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//')):
                continue

            if re.search(r'@(csrf_exempt|csrf_protect)', line):
                has_csrf_protection = True

            if re.search(r'@(app|Blueprint)\.route.*methods.*POST', line):
                post_forms.append(i)

            for pattern, _ in csrf_protection_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    has_csrf_protection = True
                    break

        if post_forms and not has_csrf_protection:
            findings.append({
                "rule_id": self.rule_id,
                "severity": self.severity.value,
                "file": file_path,
                "line": post_forms[0],
                "message": "POST endpoint without CSRF protection",
                "explanation": "State-changing POST requests should include CSRF tokens "
                               "to prevent cross-site request forgery attacks.",
                "fix": "Add CSRF protection middleware or decorators",
            })

        return findings
