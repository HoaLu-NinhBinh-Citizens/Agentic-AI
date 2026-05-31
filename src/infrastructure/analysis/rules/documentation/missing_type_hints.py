"""Missing type hints detection rule."""

from dataclasses import dataclass
import ast

from src.shared.enums.severity import Severity


@dataclass
class MissingTypeHintsRule:
    """Detect functions without type hints.

    Functions with parameters and return values should have
    type hints for better code documentation and tooling support.
    """

    rule_id: str = "DOC003"
    severity: Severity = Severity.INFO

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        try:
            tree = ast.parse(content)
        except SyntaxError:
            return findings

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not self._is_private(node.name):
                    if self._should_have_type_hints(node):
                        if not self._has_return_hint(node):
                            findings.append({
                                "rule_id": self.rule_id,
                                "severity": self.severity.value,
                                "file": file_path,
                                "line": node.lineno,
                                "message": f"Missing return type hint: {node.name}()",
                                "explanation": "Public functions should have return type hints "
                                               "for better documentation and IDE support.",
                                "fix": "Add return type annotation: def func() -> ReturnType:",
                            })

                        if self._has_params_without_hints(node):
                            findings.append({
                                "rule_id": self.rule_id,
                                "severity": self.severity.value,
                                "file": file_path,
                                "line": node.lineno,
                                "message": f"Missing parameter type hints: {node.name}()",
                                "explanation": "Function parameters should have type hints "
                                               "for better documentation.",
                                "fix": "Add type hints: def func(param: Type) -> ReturnType:",
                            })

        return findings

    def _is_private(self, name: str) -> bool:
        return name.startswith('_')

    def _should_have_type_hints(self, node) -> bool:
        if len(node.body) < 3:
            return False
        return True

    def _has_return_hint(self, node) -> bool:
        return node.returns is not None

    def _has_params_without_hints(self, node) -> bool:
        for arg in node.args.args:
            if arg.annotation is None and not arg.arg.startswith('_'):
                return True
        return False
