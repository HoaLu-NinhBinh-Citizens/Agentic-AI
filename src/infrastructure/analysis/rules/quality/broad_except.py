"""Broad except detection rule."""

from dataclasses import dataclass
from typing import Optional
import ast

from src.shared.enums.severity import Severity


@dataclass
class BroadExceptRule:
    """Detect bare except or except Exception clauses.

    Catching all exceptions can hide bugs and make debugging difficult.
    """

    rule_id: str = "QUAL003"
    severity: Severity = Severity.WARNING

    def detect(self, content: str, file_path: str) -> list[dict]:
        """Detect broad except clauses in source code.

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
            if isinstance(node, ast.ExceptHandler):
                if node.type is None:
                    findings.append({
                        "rule_id": self.rule_id,
                        "severity": Severity.HIGH.value,
                        "file": file_path,
                        "line": node.lineno,
                        "message": "Bare except clause",
                        "explanation": "Bare except catches SystemExit, KeyboardInterrupt, etc. "
                                       "Catch specific exceptions instead.",
                        "fix": "except ValueError as e:\n    # Handle specific exception",
                    })
                elif isinstance(node.type, ast.Name) and node.type.id == 'Exception':
                    findings.append({
                        "rule_id": self.rule_id,
                        "severity": self.severity.value,
                        "file": file_path,
                        "line": node.lineno,
                        "message": "Broad except Exception clause",
                        "explanation": "Catching Exception is too broad. "
                                       "Catch specific exceptions.",
                        "fix": "except (ValueError, TypeError) as e:\n    # Handle specific exceptions",
                    })

        return findings
