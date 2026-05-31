"""Insecure hash algorithm detection rule."""

from dataclasses import dataclass
from typing import Optional
import re

from src.shared.enums.severity import Severity


INSECURE_HASHES = ['md5', 'sha1']


@dataclass
class InsecureHashRule:
    """Detect use of insecure hash algorithms.

    MD5 and SHA1 are cryptographically broken. Use SHA-256 or better.
    """

    rule_id: str = "SEC006"
    severity: Severity = Severity.WARNING

    def detect(self, content: str, file_path: str) -> list[dict]:
        """Detect insecure hash usage in source code.

        Args:
            content: Source code content
            file_path: Path to source file

        Returns:
            List of finding dictionaries
        """
        findings = []

        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            for hash_name in INSECURE_HASHES:
                pattern = rf'hashlib\.{hash_name}\('
                if re.search(pattern, line):
                    findings.append({
                        "rule_id": self.rule_id,
                        "severity": self.severity.value,
                        "file": file_path,
                        "line": i,
                        "message": f"Use of insecure hash algorithm: {hash_name.upper()}",
                        "explanation": f"{hash_name.upper()} is cryptographically weak. "
                                       "Use hashlib.sha256() or hashlib.sha3_256() instead.",
                        "fix": "# Use hashlib.sha256() or hashlib.sha3_256()",
                    })

        return findings
