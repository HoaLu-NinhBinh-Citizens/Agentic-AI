"""Any type annotation detection rule."""

from dataclasses import dataclass
from typing import Optional
import ast

from src.shared.enums.severity import Severity


@dataclass
class AnyTypeRule:
    """Detect 'Any' type annotations.

    Using Any defeats the purpose of type checking.
    """

    rule_id: str = "TYPE001"
    severity: Severity = Severity.WARNING

    def detect(self, content: str, file_path: str) -> list[dict]:
        """Detect 'Any' type usage in source code.

        Args:
            content: Source code content
            file_path: Path to source file

        Returns:
            List of finding dictionaries
        """
        findings = []

        try:
            tree = ast.parse(content)
        except SyntaxError:
            return findings

        has_typing_import = 'from typing import' in content and 'Any' in content

        for i, line in enumerate(content.split('\n'), 1):
            stripped = line.strip()
            if stripped.startswith('#'):
                continue

            if 'Any' in line and has_typing_import:
                findings.append({
                    "rule_id": self.rule_id,
                    "severity": self.severity.value,
                    "file": file_path,
                    "line": i,
                    "message": "Use of 'Any' type annotation",
                    "explanation": "'Any' defeats type checking. "
                                   "Use more specific types or Union/Optional.",
                    "fix": "# Use Union[X, Y], Optional[X], or concrete types",
                })

        return findings
