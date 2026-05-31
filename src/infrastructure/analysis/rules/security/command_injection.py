"""Command injection detection rule."""

from dataclasses import dataclass
from typing import Optional
import re

from src.shared.enums.severity import Severity


COMMAND_INJECTION_PATTERNS = [
    r'os\.system\([^)]*\%',
    r'os\.popen\([^)]*\%',
    r'subprocess\.\w+\([^)]*shell\s*=\s*True',
    r'eval\([^)]*request',
    r'exec\([^)]*request',
]


@dataclass
class CommandInjectionRule:
    """Detect command injection vulnerabilities.

    Command injection occurs when user input is passed to shell commands
    without proper sanitization.
    """

    rule_id: str = "SEC003"
    severity: Severity = Severity.CRITICAL

    def detect(self, content: str, file_path: str) -> list[dict]:
        """Detect command injection vulnerabilities in source code.

        Args:
            content: Source code content
            file_path: Path to source file

        Returns:
            List of finding dictionaries
        """
        findings = []

        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            for pattern in COMMAND_INJECTION_PATTERNS:
                if re.search(pattern, line):
                    findings.append({
                        "rule_id": self.rule_id,
                        "severity": self.severity.value,
                        "file": file_path,
                        "line": i,
                        "message": "Potential command injection vulnerability",
                        "explanation": "User input may be passed to shell commands. "
                                       "Use subprocess with shell=False or sanitize input.",
                        "fix": "subprocess.run(args, shell=False)",
                    })
                    break

        return findings
