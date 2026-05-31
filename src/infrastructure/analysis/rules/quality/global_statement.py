"""Global variable mutation detection rule."""

from dataclasses import dataclass
from typing import Optional
import ast

from src.shared.enums.severity import Severity


@dataclass
class GlobalVariableRule:
    """Detect global variable mutations.

    Global variables make code hard to test and reason about.
    """

    rule_id: str = "QUAL004"
    severity: Severity = Severity.WARNING

    def detect(self, content: str, file_path: str) -> list[dict]:
        """Detect global variable mutations in source code.

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

        for node in ast.walk(tree):
            if isinstance(node, ast.Global):
                findings.append({
                    "rule_id": self.rule_id,
                    "severity": self.severity.value,
                    "file": file_path,
                    "line": node.lineno,
                    "message": f"Global statement for: {', '.join(node.names)}",
                    "explanation": "Global variables make code harder to test and reason about. "
                                   "Pass values as parameters or use a class/closure.",
                    "fix": "# Pass as parameter or use a class to encapsulate state",
                })

        return findings
