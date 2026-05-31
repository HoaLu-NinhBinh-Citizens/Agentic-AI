"""Weak hashing algorithm detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class WeakHashRule:
    """Detect weak password hashing algorithms.

    MD5 and SHA1 are too fast for password hashing.
    Use bcrypt, scrypt, Argon2, or PBKDF2 with high iteration counts.
    """

    rule_id: str = "SEC021"
    severity: Severity = Severity.HIGH

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        weak_hash_patterns = [
            (r'hashlib\.md5\b', "MD5 is too fast for passwords"),
            (r'hashlib\.sha1\b', "SHA1 is too fast for passwords"),
            (r'hashlib\.sha256\b', "SHA256 alone is too fast for passwords"),
            (r'hashlib\.sha512\b', "SHA512 alone is too fast for passwords"),
            (r'\.hexdigest\s*\(\s*\)', "Hash used without salt"),
            (r'md5\s*\(', "MD5 hash function called"),
            (r'sha1\s*\(', "SHA1 hash function called"),
        ]

        safe_hash_patterns = [
            (r'bcrypt\.hashpw', "bcrypt is secure for passwords"),
            (r'bcrypt\.gensalt', "bcrypt salt generation"),
            (r'argon2', "Argon2 is secure for passwords"),
            (r'pbkdf2_hmac', "PBKDF2 is acceptable with high iterations"),
            (r'scrypt\.hash', "scrypt is secure for passwords"),
            (r'hashpw.*werkzeug\.security', "Werkzeug's secure hashing"),
        ]

        lines = content.split('\n')
        has_safe_hash = False

        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//')):
                continue

            for pattern, _ in safe_hash_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    has_safe_hash = True
                    break

        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//')):
                continue

            for pattern, desc in weak_hash_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    if not has_safe_hash:
                        findings.append({
                            "rule_id": self.rule_id,
                            "severity": self.severity.value,
                            "file": file_path,
                            "line": i,
                            "message": f"Weak password hashing: {desc}",
                            "explanation": "Fast hash functions are vulnerable to brute force. "
                                           "Use adaptive slow hashes for passwords.",
                            "fix": "Use bcrypt, argon2, or PBKDF2 with 100000+ iterations",
                        })
                    break

        return findings
