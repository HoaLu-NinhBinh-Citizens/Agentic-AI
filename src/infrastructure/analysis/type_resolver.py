"""Type resolution for Python/TypeScript/JavaScript.

Resolves imports, aliases, and basic type inference.
"""

from __future__ import annotations

import re
from typing import Optional, Any, Union
from dataclasses import dataclass, field


@dataclass
class TypeInfo:
    """Information about a resolved type."""
    name: str
    full_name: str  # module.ClassName
    module: Optional[str] = None
    is_builtin: bool = False
    confidence: float = 1.0


@dataclass
class ImportInfo:
    """Information about an import statement."""
    line: int
    names: list[tuple[str, Optional[str]]]  # (original, alias) pairs
    module: Optional[str] = None
    is_wildcard: bool = False


class TypeResolver:
    """Resolves types from imports and basic inference."""

    def __init__(self) -> None:
        self._imports: dict[str, list[ImportInfo]] = {}  # file -> imports
        self._alias_map: dict[str, dict[str, str]] = {}  # file -> alias -> original
        self._builtins = self._load_builtins()

    def _load_builtins(self) -> set[str]:
        """Load Python built-in types."""
        return {
            "int", "float", "str", "bool", "list", "dict", "set", "tuple",
            "None", "type", "object", "bytes", "bytearray",
            "range", "enumerate", "zip", "map", "filter",
            "print", "len", "range", "isinstance", "hasattr",
            "torch", "tf", "numpy", "pandas", "sklearn",
        }

    def parse_imports(self, content: str) -> list[ImportInfo]:
        """Parse all import statements from file content."""
        imports: list[ImportInfo] = []
        
        # Join lines and handle multiline imports
        normalized = self._normalize_multiline_imports(content)
        lines = normalized.split("\n")

        for i, line in enumerate(lines, 1):
            stripped = line.strip()

            # Skip empty lines and comments
            if not stripped or stripped.startswith("#"):
                continue

            # from X import Y
            if match := re.search(r"^from\s+(\S+)\s+import\s+(.+)$", stripped):
                module = match.group(1)
                names_str = match.group(2)
                names = self._parse_import_names(names_str)
                imports.append(ImportInfo(
                    line=i,
                    names=names,
                    module=module
                ))

            # import X
            elif re.search(r"^import\s+", stripped):
                if match := re.search(r"^import\s+(.+)$", stripped):
                    module = match.group(1).split(" as ")[0].strip()
                    alias = None
                    if " as " in stripped:
                        alias = stripped.split(" as ")[1].strip()
                    imports.append(ImportInfo(
                        line=i,
                        names=[(module.split(".")[-1], alias)],
                        module=module
                    ))

        return imports

    def _normalize_multiline_imports(self, content: str) -> str:
        """Normalize multiline imports with parentheses into single lines."""
        lines = content.split("\n")
        result: list[str] = []
        current_import = ""
        in_parentheses = False

        for line in lines:
            stripped = line.strip()
            
            if not in_parentheses:
                # Check if this starts a multiline import
                if re.match(r"from\s+\S+\s+import\s*\(", stripped):
                    # Extract 'from X import' part
                    match = re.match(r"(from\s+\S+\s+import\s*)", stripped)
                    if match:
                        current_import = match.group(1)
                        in_parentheses = True
                        # Check if it closes on same line
                        if ")" in stripped:
                            rest = stripped[len(match.group(0)):]
                            rest = rest.replace(")", "").strip()
                            if rest:
                                current_import += " " + rest
                            result.append(current_import)
                            current_import = ""
                            in_parentheses = False
                else:
                    result.append(line)
            else:
                # Inside parentheses
                if stripped.endswith(")"):
                    # End of multiline import - remove trailing )
                    clean = stripped.rstrip(")").rstrip(",").strip()
                    if clean:
                        current_import += ", " + clean
                    result.append(current_import)
                    current_import = ""
                    in_parentheses = False
                elif stripped == "(":
                    # Empty paren line, skip
                    pass
                else:
                    # Continue multiline
                    clean = stripped.rstrip(",").strip()
                    if clean:
                        if current_import.endswith(","):
                            current_import += " " + clean
                        else:
                            current_import += ", " + clean

        return "\n".join(result)

        return imports

    def _parse_import_names(
        self, names_str: str
    ) -> list[tuple[str, Optional[str]]]:
        """Parse 'A, B as C, D' into [(A, None), (B, C), (D, None)]."""
        names: list[tuple[str, Optional[str]]] = []
        # Handle parens: import (A, B)
        names_str = names_str.strip("()")

        for part in names_str.split(","):
            part = part.strip()
            if not part:
                continue
            if " as " in part:
                orig, alias = part.split(" as ")
                names.append((orig.strip(), alias.strip()))
            else:
                names.append((part.strip(), None))

        return names

    def build_alias_map(self, imports: list[ImportInfo]) -> dict[str, str]:
        """Build alias -> original mapping from imports."""
        alias_map: dict[str, str] = {}
        for imp in imports:
            for original, alias in imp.names:
                if alias:
                    alias_map[alias] = original
                else:
                    alias_map[original] = original
        return alias_map

    def resolve_name(
        self,
        name: str,
        content: str,
        line: int,
        language: str = "python"
    ) -> Optional[TypeInfo]:
        """Resolve a name at a specific line to its type."""
        imports = self.parse_imports(content)
        alias_map = self.build_alias_map(imports)

        # Check if name is an alias
        if name in alias_map:
            original = alias_map[name]
            # Look up in imports to find module
            for imp in imports:
                for orig, alias in imp.names:
                    if alias == name or orig == name:
                        return TypeInfo(
                            name=original,
                            full_name=f"{imp.module}.{original}" if imp.module else original,
                            module=imp.module,
                            confidence=0.95
                        )

        # Check builtins
        if name in self._builtins:
            return TypeInfo(
                name=name,
                full_name=name,
                is_builtin=True,
                confidence=1.0
            )

        return None

    def resolve_qualified_name(
        self,
        qualified: str,
        content: str
    ) -> Optional[TypeInfo]:
        """Resolve 'module.ClassName' style names."""
        # np.ndarray -> numpy.ndarray
        # torch.nn.Module -> torch.nn.Module
        parts = qualified.split(".")
        if len(parts) >= 2:
            module = ".".join(parts[:-1])
            name = parts[-1]
            return TypeInfo(
                name=name,
                full_name=qualified,
                module=module,
                confidence=0.9
            )
        return None

    def get_imported_symbols(self, imports: list[ImportInfo]) -> set[str]:
        """Get all symbols that can be referenced from imports."""
        symbols: set[str] = set()
        for imp in imports:
            for original, alias in imp.names:
                symbols.add(alias or original)
        return symbols

    def infer_type_from_context(
        self,
        name: str,
        content: str,
        line: int
    ) -> Optional[TypeInfo]:
        """Basic type inference from assignment context."""
        lines = content.split("\n")
        if line < 1 or line > len(lines):
            return None

        # Look backward for assignment
        for i in range(line - 1, -1, -1):
            l = lines[i].strip()
            # x = 5 -> int
            if match := re.match(rf"{re.escape(name)}\s*=\s*(\d+)\s*$", l):
                return TypeInfo(name="int", full_name="int", is_builtin=True, confidence=0.7)
            # x = 1.5 -> float
            if match := re.match(rf"{re.escape(name)}\s*=\s*[\d.]+\.\d+\s*$", l):
                return TypeInfo(name="float", full_name="float", is_builtin=True, confidence=0.7)
            # x = "..." -> str
            if match := re.match(rf"{re.escape(name)}\s*=\s*['\"].*['\"]\s*$", l):
                return TypeInfo(name="str", full_name="str", is_builtin=True, confidence=0.7)
            # x = [...] -> list
            if match := re.match(rf"{re.escape(name)}\s*=\s*\[\s*\]\s*$", l):
                return TypeInfo(name="list", full_name="list", is_builtin=True, confidence=0.6)
            # x = {{}} -> dict
            if match := re.match(rf"{re.escape(name)}\s*=\s*\{{.*}}\s*$", l):
                return TypeInfo(name="dict", full_name="dict", is_builtin=True, confidence=0.6)

        return None
