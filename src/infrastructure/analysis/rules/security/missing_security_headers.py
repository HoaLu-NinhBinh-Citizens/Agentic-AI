"""HTTP security headers missing detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class MissingSecurityHeadersRule:
    """Detect missing HTTP security headers.

    Security headers like CSP, X-Frame-Options, and HSTS
    help protect against common web vulnerabilities.
    """

    rule_id: str = "SEC033"
    severity: Severity = Severity.LOW

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        response_patterns = [
            (r'return\s+Response', "HTTP response being returned"),
            (r'return\s+render_template', "Template being rendered"),
            (r'response\s*=\s*', "Response object created"),
            (r'@app\.route', "Flask route detected"),
            (r'@app\.after_request', "Flask after_request hook"),
        ]

        header_patterns = [
            (r'X-Frame-Options', "X-Frame-Options header"),
            (r'Content-Security-Policy', "CSP header"),
            (r'Strict-Transport-Security', "HSTS header"),
            (r'X-Content-Type-Options', "X-Content-Type-Options header"),
            (r'X-XSS-Protection', "X-XSS-Protection header"),
            (r'referrer-policy', "Referrer-Policy header"),
        ]

        lines = content.split('\n')
        has_response = any(re.search(p, content) for p in response_patterns)
        has_headers = any(re.search(p, content) for p in header_patterns)

        if has_response and not has_headers:
            findings.append({
                "rule_id": self.rule_id,
                "severity": self.severity.value,
                "file": file_path,
                "line": 1,
                "message": "Missing HTTP security headers",
                "explanation": "Web responses should include security headers to protect "
                               "against common attacks.",
                "fix": "Add security headers: X-Frame-Options, CSP, HSTS, X-Content-Type-Options",
            })

        return findings
