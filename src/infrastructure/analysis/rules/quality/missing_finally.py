"""Missing finally block detection rule."""

from dataclasses import dataclass
import ast

from src.shared.enums.severity import Severity


@dataclass
class MissingFinallyRule:
    """Detect try blocks without finally for cleanup.

    Try blocks that allocate resources should have finally
    blocks to ensure cleanup even when exceptions occur.
    """

    rule_id: str = "QUAL011"
    severity: Severity = Severity.MEDIUM

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        try:
            tree = ast.parse(content)
        except SyntaxError:
            return findings

        for node in ast.walk(tree):
            if isinstance(node, ast.Try):
                has_finally = len(node.finalbody) > 0
                has_resource = self._try_block_has_resource(node)

                if has_resource and not has_finally:
                    findings.append({
                        "rule_id": self.rule_id,
                        "severity": self.severity.value,
                        "file": file_path,
                        "line": node.lineno,
                        "message": "Try block without finally for resource cleanup",
                        "explanation": "Resources acquired in try blocks should be released "
                                       "in finally blocks to ensure cleanup on exceptions.",
                        "fix": "Add a finally block for cleanup, or use context managers",
                    })

        return findings

    def _try_block_has_resource(self, node: ast.Try) -> bool:
        resource_keywords = ['open(', 'tempfile', 'connect', 'lock', 'Lock(',
                           'acquire', 'start()', '.begin()']

        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                source = ast.unparse(child) if hasattr(ast, 'unparse') else ''
                for kw in resource_keywords:
                    if kw in source:
                        return True

        return False
