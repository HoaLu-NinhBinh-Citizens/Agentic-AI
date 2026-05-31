"""Hardcoded initialization vector (IV) detection rule."""

from dataclasses import dataclass
import re

from src.shared.enums.severity import Severity


@dataclass
class HardcodedIVRule:
    """Detect hardcoded initialization vectors in encryption.

    Using a hardcoded IV weakens encryption and can lead to
    predictable ciphertext. IVs should be randomly generated.
    """

    rule_id: str = "SEC023"
    severity: Severity = Severity.MEDIUM

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        iv_patterns = [
            (r'IV\s*=\s*["\'][\da-fA-F]+["\']', "Hardcoded IV (hex string)"),
            (r'iv\s*=\s*["\'][\da-fA-F]+["\']', "Hardcoded IV (hex string)"),
            (r'initialization_vector\s*=\s*["\']', "Hardcoded initialization vector"),
            (r'crypto\.cipher\.pad', "IV should be random, not hardcoded"),
            (r'AES\.new\s*\([^)]*IV\s*=', "IV passed to AES"),
            (r'iv:\s*["\'][\da-fA-F]+["\']', "IV in config (hex)"),
        ]

        random_iv_patterns = [
            (r'os\.urandom', "Random bytes for IV"),
            (r'securesecret', "Secure random generation"),
            (r'Random\.new', "Random IV generation"),
            (r'getrandom', "System random for IV"),
        ]

        lines = content.split('\n')
        has_random_iv = False

        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//')):
                continue

            for pattern, _ in random_iv_patterns:
                if re.search(pattern, line):
                    has_random_iv = True
                    break

        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('#', '//')):
                continue

            for pattern, desc in iv_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    if not has_random_iv:
                        findings.append({
                            "rule_id": self.rule_id,
                            "severity": self.severity.value,
                            "file": file_path,
                            "line": i,
                            "message": f"Hardcoded IV: {desc}",
                            "explanation": "Using a fixed IV makes encryption predictable. "
                                           "IVs should be randomly generated for each encryption.",
                            "fix": "Generate IV with os.urandom() for each encryption operation",
                        })
                    break

        return findings
