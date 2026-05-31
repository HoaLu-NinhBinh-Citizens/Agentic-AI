"""Unused import detection rule."""

from dataclasses import dataclass
from typing import Optional, Set
import ast
import re

from src.shared.enums.severity import Severity


@dataclass
class UnusedImportRule:
    """Detect unused imports.

    Unused imports add clutter and can indicate refactoring needed.
    """

    rule_id: str = "IMP001"
    severity: Severity = Severity.INFO

    def detect(self, content: str, file_path: str) -> list[dict]:
        """Detect unused imports in source code.

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

        imports = self._collect_imports(tree)
        if not imports:
            return findings

        used = self._find_usages(content, imports)

        for name, line_no in imports.items():
            if name not in used:
                findings.append({
                    "rule_id": self.rule_id,
                    "severity": self.severity.value,
                    "file": file_path,
                    "line": line_no,
                    "message": f"Unused import: {name}",
                    "explanation": "This import is not used in the file.",
                    "fix": "# Remove the unused import",
                })

        return findings

    def _collect_imports(self, tree: ast.AST) -> dict[str, int]:
        """Collect all imports from AST."""
        imports = {}

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.asname if alias.asname else alias.name
                    imports[name] = node.lineno
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    name = alias.asname if alias.asname else alias.name
                    imports[name] = node.lineno

        return imports

    def _find_usages(self, content: str, imports: dict[str, int]) -> Set[str]:
        """Find which imports are used in the content."""
        used = set()

        for imp in imports:
            pattern = rf'\b{re.escape(imp)}\b'
            matches = list(re.finditer(pattern, content))
            if len(matches) > 1:
                used.add(imp)

        return used
