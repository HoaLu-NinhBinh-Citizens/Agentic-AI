"""Server-side request forgery (SSRF) detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class SSRFRule:
    """Detect potential Server-Side Request Forgery (SSRF) vulnerabilities.

    SSRF allows attackers to make requests to internal resources
    by manipulating URLs or user input.
    """

    rule_id: str = "SEC027"
    severity: Severity = Severity.HIGH

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        ssrf_patterns = [
            (r'requests\.get\s*\(.*url\s*=', "HTTP GET with URL parameter"),
            (r'urllib\.request\.urlopen\s*\(', "URL fetch operation"),
            (r'httpx\.get\s*\(.*url\s*=', "HTTPX GET with URL"),
            (r'\.get\s*\(.*["\']url["\']', "URL from parameter"),
            (r'\.get\s*\(.*["\']uri["\']', "URI from parameter"),
            (r'\.get\s*\(.*["\']endpoint["\']', "Endpoint from parameter"),
            (r'requests\.(get|post|put|delete)\s*\(.*\+\s*', "URL concatenation detected"),
        ]

        safe_patterns = [
            (r'urlparse.*\.netloc', "URL parsed for validation"),
            (r'startswith\s*\(\s*["\']https', "HTTPS-only check"),
            (r'ALLOWED_HOSTS', "Host validation check"),
            (r'is_valid_url', "URL validation function"),
            (r'validate_url', "URL validation function"),
        ]

        lines = content.split('\n')
        has_validation = any(re.search(p, content) for p in safe_patterns)

        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//')):
                continue

            for pattern, desc in ssrf_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    if not has_validation:
                        findings.append({
                            "rule_id": self.rule_id,
                            "severity": self.severity.value,
                            "file": file_path,
                            "line": i,
                            "message": f"Potential SSRF: {desc}",
                            "explanation": "URLs from user input should be validated before fetching.",
                            "fix": "Validate URLs against allowlist, check netloc, and use urllib.parse.urlparse",
                        })
                    break

        return findings
