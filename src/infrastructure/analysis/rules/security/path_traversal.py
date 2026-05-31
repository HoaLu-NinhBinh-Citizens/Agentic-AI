"""Path traversal detection rule."""

from dataclasses import dataclass
from typing import Optional
import re

from src.shared.enums.severity import Severity


PATH_TRAVERSAL_PATTERNS = [
    r'open\([^)]*\+[^)]*request',
    r'open\([^)]*\%[^)]*request',
    r'os\.path\.join\([^)]*\+[^)]*request',
    r'send_file\([^)]*\+[^)]*request',
]


@dataclass
class PathTraversalRule:
    """Detect potential path traversal vulnerabilities.

    Path traversal occurs when user input is used in file paths without validation.
    """

    rule_id: str = "SEC005"
    severity: Severity = Severity.HIGH

    def detect(self, content: str, file_path: str) -> list[dict]:
        """Detect path traversal vulnerabilities in source code.

        Args:
            content: Source code content
            file_path: Path to source file

        Returns:
            List of finding dictionaries
        """
        findings = []

        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            for pattern in PATH_TRAVERSAL_PATTERNS:
                if re.search(pattern, line):
                    findings.append({
                        "rule_id": self.rule_id,
                        "severity": self.severity.value,
                        "file": file_path,
                        "line": i,
                        "message": "Potential path traversal vulnerability",
                        "explanation": "User input in file paths should be validated. "
                                       "Use os.path.basename() or whitelist allowed paths.",
                        "fix": "# Validate and sanitize path: os.path.basename(user_input)",
                    })
                    break

        return findings
