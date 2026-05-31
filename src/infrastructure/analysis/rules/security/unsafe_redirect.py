"""Unsafe redirect detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class UnsafeRedirectRule:
    """Detect unsafe URL redirects.

    Open redirects allow attackers to redirect users to malicious sites,
    enabling phishing and credential theft.
    """

    rule_id: str = "SEC020"
    severity: Severity = Severity.MEDIUM

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        redirect_patterns = [
            (r'redirect\s*\(\s*request\.args\.get', "Redirect from user input"),
            (r'redirect\s*\(\s*request\.form\.get', "Redirect from form data"),
            (r'redirect\s*\(\s*params\[["\']', "Redirect from parameters"),
            (r'return\s+redirect\s*\(\s*next', "Redirect with next parameter"),
            (r'response\.headers\[["\']Location["\']\]\s*=', "Direct Location header manipulation"),
            (r'Location:\s*\$', "Header injection in redirect"),
            (r'header\s*\(\s*["\']Location["\']', "Setting Location header"),
            (r'window\.location\s*=\s*\$', "JavaScript redirect from user input"),
        ]

        safe_redirect_patterns = [
            (r'url_for\s*\(', "Using url_for for safe redirect"),
            (r'is_safe_url', "URL safety check function"),
            (r'validate_redirect', "Redirect validation"),
            (r'redirect_to_valid_url', "URL validation before redirect"),
        ]

        lines = content.split('\n')
        has_safe_redirect = False

        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//')):
                continue

            for pattern, _ in safe_redirect_patterns:
                if re.search(pattern, line):
                    has_safe_redirect = True
                    break

        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//')):
                continue

            for pattern, desc in redirect_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    findings.append({
                        "rule_id": self.rule_id,
                        "severity": self.severity.value,
                        "file": file_path,
                        "line": i,
                        "message": f"Unsafe redirect: {desc}",
                        "explanation": "Redirecting based on user input without validation "
                                       "can lead to open redirect attacks.",
                        "fix": "Validate and whitelist redirect URLs",
                    })
                    break

        return findings
