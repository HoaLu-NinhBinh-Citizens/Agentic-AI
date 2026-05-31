"""Missing cleanup in tests detection rule."""

from dataclasses import dataclass
import ast

from src.shared.enums.severity import Severity


@dataclass
class MissingCleanupRule:
    """Detect missing cleanup in tests.

    Tests that create resources should clean them up
    to avoid resource leaks and test interference.
    """

    rule_id: str = "TEST010"
    severity: Severity = Severity.MEDIUM

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        if not self._is_test_file(content):
            return findings

        try:
            tree = ast.parse(content)
        except SyntaxError:
            return findings

        resource_patterns = {
            'open': 'file',
            'tempfile': 'temp file',
            'database': 'database connection',
            'redis': 'Redis connection',
            'client': 'HTTP client',
        }

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                if self._is_test_function(node.name):
                    has_resource = self._function_has_resource(node)
                    has_cleanup = self._function_has_cleanup(node)

                    if has_resource and not has_cleanup:
                        findings.append({
                            "rule_id": self.rule_id,
                            "severity": self.severity.value,
                            "file": file_path,
                            "line": node.lineno,
                            "message": f"Resource without cleanup in: {node.name}()",
                            "explanation": "Resources opened in tests should be cleaned up "
                                           "to avoid resource leaks.",
                            "fix": "Use try/finally, context managers, or tearDown() for cleanup",
                        })

        return findings

    def _is_test_file(self, content: str) -> bool:
        return 'test_' in content or '_test.py' in content

    def _is_test_function(self, name: str) -> bool:
        return name.startswith('test_') or name.endswith('_test')

    def _function_has_resource(self, node: ast.FunctionDef) -> bool:
        resource_keywords = ['open(', 'tempfile', 'MongoClient', 'Redis(',
                           'Connection', 'Client(', 'Session()']
        source = ast.unparse(node) if hasattr(ast, 'unparse') else ''

        for kw in resource_keywords:
            if kw in source:
                return True
        return False

    def _function_has_cleanup(self, node: ast.FunctionDef) -> bool:
        cleanup_keywords = ['finally:', 'tearDown', 'close()', '.close(',
                          '__exit__', '__aexit__', 'del ', 'cleanup']
        source = ast.unparse(node) if hasattr(ast, 'unparse') else ''

        for kw in cleanup_keywords:
            if kw in source:
                return True
        return False
