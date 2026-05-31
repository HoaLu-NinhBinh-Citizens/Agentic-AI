"""Empty except block detection rule."""

from dataclasses import dataclass
from typing import Optional
import ast

from src.shared.enums.severity import Severity


@dataclass
class EmptyExceptRule:
    """Detect empty except blocks that swallow exceptions.

    Empty except blocks hide errors and make debugging difficult.
    """

    rule_id: str = "QUAL002"
    severity: Severity = Severity.WARNING

    def detect(self, content: str, file_path: str) -> list[dict]:
        """Detect empty except blocks in source code.

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
                if len(node.body) == 0:
                    findings.append({
                        "rule_id": self.rule_id,
                        "severity": self.severity.value,
                        "file": file_path,
                        "line": node.lineno,
                        "message": "Empty except block",
                        "explanation": "This except block does nothing, hiding errors. "
                                       "At minimum, log the exception.",
                        "fix": """except Exception as e:
    logger.error(f"Error occurred: {e}")
    raise""",
                    })
                elif len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                    findings.append({
                        "rule_id": self.rule_id,
                        "severity": self.severity.value,
                        "file": file_path,
                        "line": node.lineno,
                        "message": "Except block with only 'pass'",
                        "explanation": "Bare except with pass hides errors silently.",
                        "fix": """except Exception as e:
    logger.warning(f"Handled exception: {e}")""",
                    })

        return findings
