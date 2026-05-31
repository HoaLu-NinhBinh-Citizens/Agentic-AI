"""Cross-Site Scripting (XSS) detection rule."""

from dataclasses import dataclass
from typing import Optional
import re

from src.shared.enums.severity import Severity


XSS_PATTERNS = [
    r'render_template_string\([^)]*\}',
    r'Markup\([^)]*\+',
    r'\.html\([^)]*\%',
    r'render_string\([^)]*request',
]


@dataclass
class XSSRule:
    """Detect potential XSS vulnerabilities.

    XSS occurs when user input is rendered without proper escaping.
    """

    rule_id: str = "SEC004"
    severity: Severity = Severity.CRITICAL

    def detect(self, content: str, file_path: str) -> list[dict]:
        """Detect XSS vulnerabilities in source code.

        Args:
            content: Source code content
            file_path: Path to source file

        Returns:
            List of finding dictionaries
        """
        findings = []

        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            for pattern in XSS_PATTERNS:
                if re.search(pattern, line):
                    findings.append({
                        "rule_id": self.rule_id,
                        "severity": self.severity.value,
                        "file": file_path,
                        "line": i,
                        "message": "Potential XSS vulnerability",
                        "explanation": "User input may be rendered without escaping. "
                                       "Use template engines with auto-escaping or explicit escaping.",
                        "fix": "Use markupsafe or template engine auto-escaping",
                    })
                    break

        return findings
