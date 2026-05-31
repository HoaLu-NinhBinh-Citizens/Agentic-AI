"""Recursive function without memoization detection rule."""

from dataclasses import dataclass
import re
import ast

from src.shared.enums.severity import Severity


@dataclass
class RecursiveWithoutMemoRule:
    """Detect recursive functions that could benefit from memoization.

    Recursive functions without caching can have exponential time complexity.
    Consider adding @lru_cache or explicit memoization.
    """

    rule_id: str = "PERF004"
    severity: Severity = Severity.MEDIUM

    def detect(self, content: str, file_path: str) -> list[dict]:
        findings = []

        try:
            tree = ast.parse(content)
        except SyntaxError:
            return findings

        recursive_funcs = self._find_recursive_functions(tree)

        for func_name, lineno in recursive_funcs:
            func_lines = content.split('\n')
            context = '\n'.join(func_lines[max(0, lineno-1):lineno+10])

            if 'lru_cache' not in context and 'cache' not in context:
                if 'functools' not in content or '@' not in context:
                    findings.append({
                        "rule_id": self.rule_id,
                        "severity": self.severity.value,
                        "file": file_path,
                        "line": lineno,
                        "message": f"Recursive function without memoization: {func_name}()",
                        "explanation": "Recursive functions without caching have exponential "
                                       "time complexity for repeated subproblems.",
                        "fix": "Add @functools.lru_cache decorator",
                    })

        return findings

    def _find_recursive_functions(self, tree: ast.AST) -> list[tuple[str, int]]:
        recursive_funcs = []

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_name = node.name
                func_calls = [n.id for n in ast.walk(node)
                              if isinstance(n, ast.Name) and n.id == func_name]

                if len(func_calls) > 1:
                    recursive_funcs.append((func_name, node.lineno))

        return recursive_funcs
