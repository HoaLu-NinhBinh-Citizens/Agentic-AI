"""Deprecated import detection rule."""

from dataclasses import dataclass
from typing import Optional
import re

from src.shared.enums.severity import Severity


DEPRECATED_IMPORTS = {
    'imp': 'imp module is deprecated since Python 3.4',
    'optparse': 'optparse is deprecated, use argparse',
    'tkMessageBox': 'tkMessageBox is deprecated, use tkinter.messagebox',
    'StringIO': 'Use io.StringIO instead',
}


@dataclass
class DeprecatedImportRule:
    """Detect deprecated module imports.

    Deprecated modules should be replaced with modern alternatives.
    """

    rule_id: str = "QUAL006"
    severity: Severity = Severity.WARNING

    def detect(self, content: str, file_path: str) -> list[dict]:
        """Detect deprecated imports in source code.

        Args:
            content: Source code content
            file_path: Path to source file

        Returns:
            List of finding dictionaries
        """
        findings = []

        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            for deprecated, message in DEPRECATED_IMPORTS.items():
                pattern = rf'^import\s+{deprecated}|^from\s+{deprecated}\s+import'
                if re.search(pattern, line):
                    findings.append({
                        "rule_id": self.rule_id,
                        "severity": self.severity.value,
                        "file": file_path,
                        "line": i,
                        "message": f"Deprecated import: {deprecated}",
                        "explanation": message,
                        "fix": "# Use the recommended replacement module",
                    })

        return findings
