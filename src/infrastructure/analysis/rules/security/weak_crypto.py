"""Weak cryptographic algorithms detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class WeakCryptoRule:
    """Detect use of weak cryptographic algorithms.

    MD5, SHA1, DES, and other weak algorithms should not be used
    for security-sensitive operations.
    """

    rule_id: str = "SEC009"
    severity: Severity = Severity.HIGH

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        weak_patterns = [
            (r'hashlib\.md5', "MD5 is cryptographically broken"),
            (r'hashlib\.sha1', "SHA1 is deprecated for security use"),
            (r'hashlib\.sha256\(', "SHA256 is acceptable but use hashlib.sha256() directly"),
            (r'DES\.new\s*\(', "DES is insecure, use AES"),
            (r'RC4', "RC4 is insecure"),
            (r'cryptography\.hazmat\.primitives\.ciphers\.algorithms\.ARC4', "RC4 is insecure"),
            (r'Crypto\.Cipher\.DES', "DES is insecure"),
            (r'md5\s*\(', "MD5 is cryptographically broken"),
            (r'sha1\s*\(', "SHA1 is deprecated for security use"),
        ]

        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//')):
                continue

            for pattern, desc in weak_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    findings.append({
                        "rule_id": self.rule_id,
                        "severity": self.severity.value,
                        "file": file_path,
                        "line": i,
                        "message": f"Weak cryptography: {desc}",
                        "explanation": f"{desc} for cryptographic purposes. "
                                       "Use SHA-256, SHA-384, or SHA-512 instead.",
                        "fix": "Use hashlib.sha256() or hashlib.sha384() for hashing",
                    })
                    break

        return findings
