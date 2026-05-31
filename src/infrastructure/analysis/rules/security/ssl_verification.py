"""SSL/TLS verification disabled detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class SSLVerificationRule:
    """Detect disabled SSL/TLS certificate verification.

    Disabling SSL verification exposes connections to man-in-the-middle attacks.
    """

    rule_id: str = "SEC015"
    severity: Severity = Severity.HIGH

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        verify_patterns = [
            (r'verify\s*=\s*False', "SSL verification disabled"),
            (r'verify\s*=\s*0', "SSL verification disabled"),
            (r'\.verify\s*=\s*False', "SSL verification disabled"),
            (r'REQUEST_VERIFY_SSL\s*=\s*False', "SSL verification disabled via env"),
            (r'SSL_VERIFY\s*=\s*False', "SSL verification disabled via env"),
            (r'check_hostname\s*=\s*False', "Hostname check disabled"),
            (r'CURLOPT_SSL_VERIFYPEER\s*=\s*0', "cURL SSL verification disabled"),
            (r'CURLOPT_SSL_VERIFYHOST\s*=\s*0', "cURL host verification disabled"),
        ]

        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//')):
                continue

            for pattern, desc in verify_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    findings.append({
                        "rule_id": self.rule_id,
                        "severity": self.severity.value,
                        "file": file_path,
                        "line": i,
                        "message": f"SSL/TLS security issue: {desc}",
                        "explanation": "Disabling SSL verification allows man-in-the-middle attacks. "
                                       "Always verify certificates in production.",
                        "fix": "Set verify=True or provide proper CA bundle path",
                    })
                    break

        return findings
