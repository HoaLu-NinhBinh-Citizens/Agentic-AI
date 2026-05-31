"""Weak session management detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class WeakSessionRule:
    """Detect weak session management practices.

    Sessions should be securely generated, expire properly,
    and be protected against hijacking.
    """

    rule_id: str = "SEC037"
    severity: Severity = Severity.MEDIUM

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        session_patterns = [
            (r'session\[', "Session access"),
            (r'request\.session', "Request session"),
            (r'flask\.session', "Flask session"),
            (r'django\.sessions', "Django sessions"),
        ]

        weak_patterns = [
            (r'session\.secret\s*=', "Session secret being set"),
            (r'SECRET_KEY\s*=', "SECRET_KEY assignment"),
            (r'session\.permanent\s*=\s*True', "Permanent session"),
            (r'session\.expires\s*=', "Session expires setting"),
        ]

        safe_patterns = [
            (r'SECRET_KEY\s*=\s*os\.environ', "SECRET_KEY from environment"),
            (r'SECRET_KEY\s*=\s*os\.getenv', "SECRET_KEY from environment"),
            (r'CookiePolicy', "Cookie policy setting"),
            (r'session\.httponly\s*=\s*True', "HttpOnly session cookie"),
            (r'session\.secure\s*=\s*True', "Secure session cookie"),
        ]

        lines = content.split('\n')
        has_session = any(re.search(p, content) for p in session_patterns)
        has_safe = any(re.search(p, content) for p in safe_patterns)

        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//')):
                continue

            for pattern, desc in weak_patterns:
                if re.search(pattern, line):
                    if not has_safe:
                        findings.append({
                            "rule_id": self.rule_id,
                            "severity": self.severity.value,
                            "file": file_path,
                            "line": i,
                            "message": f"Weak session: {desc}",
                            "explanation": "Sessions should be securely configured with "
                                           "HttpOnly, Secure flags and proper expiration.",
                            "fix": "Use secure session configuration with environment variables",
                        })
                    break

        return findings
