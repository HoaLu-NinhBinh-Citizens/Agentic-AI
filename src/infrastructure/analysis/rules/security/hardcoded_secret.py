"""Hardcoded secrets detection rule."""

from dataclasses import dataclass
from typing import Optional
import re

from src.shared.enums.severity import Severity


SECRET_PATTERNS = [
    (r'password\s*=\s*["\'](?!xxx|placeholder|CHANGEME)', "Hardcoded password"),
    (r'passwd\s*=\s*["\'][^(env|mock|test)]', "Hardcoded password"),
    (r'api[_-]?key\s*=\s*["\'][a-zA-Z0-9_\-]{20,}', "Hardcoded API key"),
    (r'apikey\s*=\s*["\'][a-zA-Z0-9_\-]{20,}', "Hardcoded API key"),
    (r'secret\s*=\s*["\'][a-zA-Z0-9_\-]{32,}', "Hardcoded secret"),
    (r'access[_-]?token\s*=\s*["\'][a-zA-Z0-9_\-\.]{20,}', "Hardcoded access token"),
    (r'-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----', "Hardcoded private key"),
    (r'AKIA[0-9A-Z]{16}', "AWS access key ID"),
    (r'eyJ[a-zA-Z0-9_-]*\.eyJ[a-zA-Z0-9_-]*\.[a-zA-Z0-9_-]*', "JWT token"),
]


@dataclass
class HardcodedSecretRule:
    """Detect hardcoded passwords, API keys, tokens, and secrets.

    Secrets should be loaded from environment variables or secure vaults,
    never hardcoded in source code.
    """

    rule_id: str = "SEC002"
    severity: Severity = Severity.HIGH

    def detect(self, content: str, file_path: str) -> list[dict]:
        """Detect hardcoded secrets in source code.

        Args:
            content: Source code content
            file_path: Path to source file

        Returns:
            List of finding dictionaries
        """
        findings = []

        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith('#') or stripped.startswith('//'):
                continue

            if self._is_allowed_context(line):
                continue

            for pattern, description in SECRET_PATTERNS:
                match = re.search(pattern, line)
                if match:
                    findings.append({
                        "rule_id": self.rule_id,
                        "severity": self.severity.value,
                        "file": file_path,
                        "line": i,
                        "message": f"Hardcoded {description.lower()}",
                        "explanation": f"Found {description} in source code. "
                                       "Secrets should be loaded from environment variables.",
                        "fix": f'os.getenv("SECRET_NAME")',
                    })
                    break

        return findings

    def _is_allowed_context(self, line: str) -> bool:
        """Check if the secret is in an allowed context."""
        allowed = ['test', 'mock', 'example', 'dummy', 'placeholder', 'xxx',
                   'TODO', 'CHANGEME', 'FIXME']
        line_lower = line.lower()
        return any(a in line_lower for a in allowed)
