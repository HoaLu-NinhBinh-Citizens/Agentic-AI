"""Circular import detection rule."""

from dataclasses import dataclass
from typing import Optional, List
from pathlib import Path

from src.shared.enums.severity import Severity


@dataclass
class CircularImportRule:
    """Detect potential circular imports.

    Circular imports can cause import errors and make code harder to understand.
    """

    rule_id: str = "IMP002"
    severity: Severity = Severity.WARNING

    def detect(self, content: str, file_path: str) -> list[dict]:
        """Detect potential circular imports in source code.

        Args:
            content: Path to source file
            file_path: Path to source file

        Returns:
            List of finding dictionaries
        """
        findings = []

        if not file_path.endswith('__init__.py'):
            return findings

        imports = self._extract_imports(content)
        module_name = Path(file_path).parent.name

        for imp in imports:
            if module_name in imp:
                findings.append({
                    "rule_id": self.rule_id,
                    "severity": self.severity.value,
                    "file": file_path,
                    "line": 1,
                    "message": f"Potential circular import: {imp}",
                    "explanation": "This import may create a circular dependency.",
                    "fix": "# Use TYPE_CHECKING or defer import",
                })

        return findings

    def _extract_imports(self, content: str) -> List[str]:
        """Extract import statements from content."""
        imports = []
        for line in content.split('\n'):
            stripped = line.strip()
            if stripped.startswith('from .') or stripped.startswith('import .'):
                imports.append(stripped)
        return imports
