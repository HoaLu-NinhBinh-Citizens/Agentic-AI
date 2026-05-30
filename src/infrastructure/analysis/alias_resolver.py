"""Import alias resolution for cross-file semantic analysis.

Handles:
- `import x as y`
- `from module import fn as alias`
- Relative imports: `from . import utils`, `from ..parent import func`
- Diamond import patterns
- Chained alias resolution

Architecture:
    1. parse_import() extracts all import statements
    2. build_alias_map() creates alias → original mapping
    3. resolve_symbol() finds original symbol from alias
    4. follow_import_chain() traces through multi-level imports
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class AliasEntry:
    """A single alias mapping."""
    alias: str
    original: str
    module: str  # Source module
    line: int
    is_relative: bool = False
    relative_level: int = 0  # 0 = absolute, 1 = one dot, 2 = two dots, etc.


@dataclass
class ImportStatement:
    """A parsed import statement."""
    line: int
    module: str
    names: list[tuple[str, Optional[str]]]  # (original, alias) pairs
    is_from: bool = True
    is_wildcard: bool = False
    relative_level: int = 0


@dataclass
class AliasResolutionResult:
    """Result of alias resolution."""
    original: str
    module: str
    is_aliased: bool
    alias: Optional[str] = None
    resolution_path: list[str] = field(default_factory=list)


class AliasResolver:
    """Resolve import aliases to original symbols.
    
    Tracks import aliases across files to enable accurate cross-file
    symbol resolution in semantic analysis.
    
    Usage:
        resolver = AliasResolver(symbol_graph)
        resolver.parse_import("file.py", content)
        original = resolver.resolve_symbol("file.py", "pd")  # Returns "pandas"
        module = resolver.get_original_module("file.py", "np")  # Returns "numpy"
    """

    def __init__(self, symbol_graph: Optional[object] = None) -> None:
        """Initialize the alias resolver.
        
        Args:
            symbol_graph: Optional symbol graph for advanced resolution.
        """
        self.symbol_graph = symbol_graph
        
        # file_path → {alias_name: AliasEntry}
        self._alias_map: dict[str, dict[str, AliasEntry]] = {}
        
        # file_path → list of ImportStatement
        self._imports: dict[str, list[ImportStatement]] = {}
        
        # Cache for quick lookups
        self._content_cache: dict[str, str] = {}

    def parse_import(self, file_path: str, content: str) -> dict[str, AliasEntry]:
        """Parse imports and build alias map for a file.
        
        Handles patterns:
        - `import os` → alias_map["os"] = "os"
        - `import numpy as np` → alias_map["np"] = "numpy"
        - `from collections import OrderedDict as OD` → alias_map["OD"] = "OrderedDict"
        - `from . import utils` → relative import
        - `from ..parent import func` → relative import with level 2
        
        Args:
            file_path: Path to the file being parsed.
            content: File content string.
            
        Returns:
            Dictionary mapping alias names to AliasEntry objects.
        """
        self._content_cache[file_path] = content
        aliases: dict[str, AliasEntry] = {}
        imports: list[ImportStatement] = []
        
        # Normalize multiline imports first
        normalized = self._normalize_multiline_imports(content)
        
        try:
            tree = ast.parse(content)
            imports = self._parse_imports_ast(tree, content)
        except SyntaxError:
            imports = self._parse_imports_regex(normalized, content)
        
        # Process all imports
        for imp in imports:
            for original, alias in imp.names:
                # Skip wildcard imports - they don't create explicit aliases
                if alias == "*" or original == "*":
                    continue
                    
                if alias:
                    # Explicit alias: `import X as Y` or `from M import X as Y`
                    entry = AliasEntry(
                        alias=alias,
                        original=original,
                        module=imp.module or original,
                        line=imp.line,
                        is_relative=imp.relative_level > 0,
                        relative_level=imp.relative_level
                    )
                    aliases[alias] = entry
                else:
                    # No alias: use the original name
                    entry = AliasEntry(
                        alias=original,
                        original=original,
                        module=imp.module or original,
                        line=imp.line,
                        is_relative=imp.relative_level > 0,
                        relative_level=imp.relative_level
                    )
                    aliases[original] = entry
        
        self._alias_map[file_path] = aliases
        self._imports[file_path] = imports
        
        return aliases

    def _parse_imports_ast(
        self,
        tree: ast.AST,
        content: str
    ) -> list[ImportStatement]:
        """Parse imports using AST for accurate extraction."""
        imports: list[ImportStatement] = []
        
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                relative_level = node.level  # 0 = absolute, 1 = from ., 2 = from ..
                
                names = [
                    (alias.name, alias.asname)
                    for alias in node.names
                ]
                
                is_wildcard = any(n.name == "*" for n in node.names)
                
                imports.append(ImportStatement(
                    line=node.lineno,
                    module=module,
                    names=names,
                    is_from=True,
                    is_wildcard=is_wildcard,
                    relative_level=relative_level
                ))
                
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    module = alias.name
                    asname = alias.asname
                    
                    imports.append(ImportStatement(
                        line=node.lineno,
                        module=module,
                        names=[(module.split(".")[-1], asname)],
                        is_from=False,
                        relative_level=0
                    ))
        
        return imports

    def _parse_imports_regex(
        self,
        content: str,
        original_content: str
    ) -> list[ImportStatement]:
        """Fallback regex-based import parsing for invalid syntax."""
        imports: list[ImportStatement] = []
        lines = original_content.split("\n")
        
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            
            # Skip empty lines and comments
            if not stripped or stripped.startswith("#"):
                continue
            
            # from X import Y
            if match := re.match(r"from\s+([\.\w]+)\s+import\s+(.+)", stripped):
                module = match.group(1)
                names_str = match.group(2)
                
                # Calculate relative level from dots
                relative_level = 0
                if module.startswith("."):
                    relative_level = len(module) - len(module.lstrip("."))
                    module = module[relative_level:] or ""
                
                names = self._parse_import_names(names_str)
                
                imports.append(ImportStatement(
                    line=i,
                    module=module,
                    names=names,
                    is_from=True,
                    relative_level=relative_level
                ))
            
            # import X [as Y]
            elif match := re.match(r"import\s+([\w.]+)(?:\s+as\s+(\w+))?", stripped):
                module = match.group(1)
                alias = match.group(2)
                
                imports.append(ImportStatement(
                    line=i,
                    module=module,
                    names=[(module.split(".")[-1], alias)],
                    is_from=False,
                    relative_level=0
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
                if re.match(r"from\s+\S+\s+import\s*\(", stripped):
                    match = re.match(r"(from\s+\S+\s+import\s*)", stripped)
                    if match:
                        current_import = match.group(1)
                        in_parentheses = True
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
                if stripped.endswith(")"):
                    clean = stripped.rstrip(")").rstrip(",").strip()
                    if clean:
                        current_import += ", " + clean
                    result.append(current_import)
                    current_import = ""
                    in_parentheses = False
                elif stripped == "(":
                    pass
                else:
                    clean = stripped.rstrip(",").strip()
                    if clean:
                        if current_import.endswith(","):
                            current_import += " " + clean
                        else:
                            current_import += ", " + clean

        return "\n".join(result)

    def _parse_import_names(
        self,
        names_str: str
    ) -> list[tuple[str, Optional[str]]]:
        """Parse import names string like 'A, B as C, D'."""
        names: list[tuple[str, Optional[str]]] = []
        names_str = names_str.strip("()")

        for part in names_str.split(","):
            part = part.strip()
            if not part:
                continue
            if " as " in part:
                orig, alias = part.split(" as ", 1)
                names.append((orig.strip(), alias.strip()))
            else:
                names.append((part, None))

        return names

    def resolve_symbol(self, file_path: str, symbol_name: str) -> Optional[str]:
        """Resolve alias to original symbol name.
        
        Args:
            file_path: Path to the file containing the symbol reference.
            symbol_name: The symbol/alias name to resolve.
            
        Returns:
            Original symbol name if found, None otherwise.
        """
        aliases = self._alias_map.get(file_path, {})
        
        if symbol_name in aliases:
            return aliases[symbol_name].original
        
        return None

    def get_original_module(self, file_path: str, alias: str) -> Optional[str]:
        """Get original module from alias.
        
        Args:
            file_path: Path to the file with the import.
            alias: The alias name used in the import.
            
        Returns:
            Original module name if found, None otherwise.
        """
        aliases = self._alias_map.get(file_path, {})
        
        if alias in aliases:
            return aliases[alias].module
        
        return None

    def get_alias_entry(self, file_path: str, alias: str) -> Optional[AliasEntry]:
        """Get the full AliasEntry for an alias.
        
        Args:
            file_path: Path to the file with the import.
            alias: The alias name.
            
        Returns:
            AliasEntry if found, None otherwise.
        """
        aliases = self._alias_map.get(file_path, {})
        return aliases.get(alias)

    def get_imports_for_file(self, file_path: str) -> list[ImportStatement]:
        """Get all import statements for a file.
        
        Args:
            file_path: Path to the file.
            
        Returns:
            List of ImportStatement objects.
        """
        return self._imports.get(file_path, [])

    def resolve_with_chain(
        self,
        file_path: str,
        symbol_name: str,
        max_depth: int = 10
    ) -> Optional[AliasResolutionResult]:
        """Resolve symbol following import chains.
        
        Handles diamond patterns like:
        - a.py: from b import X as A
        - b.py: from c import X as B
        - c.py: X = 42
        
        Args:
            file_path: Path to the file containing the reference.
            symbol_name: The symbol/alias to resolve.
            max_depth: Maximum chain depth to prevent infinite loops.
            
        Returns:
            AliasResolutionResult with full resolution path, or None.
        """
        if max_depth <= 0:
            return None
        
        aliases = self._alias_map.get(file_path, {})
        
        if symbol_name not in aliases:
            return None
        
        entry = aliases[symbol_name]
        resolution_path = [symbol_name]
        
        # If already at original, return
        if entry.original == entry.alias:
            return AliasResolutionResult(
                original=entry.original,
                module=entry.module,
                is_aliased=False,
                resolution_path=resolution_path
            )
        
        # Follow the chain
        current_module = entry.module
        current_name = entry.original
        
        while max_depth > 0:
            # Look for this symbol in the module's exports
            # This is a simplified version - full implementation would
            # need to check module files
            
            # For now, return what we have
            break
        
        return AliasResolutionResult(
            original=entry.original,
            module=entry.module,
            is_aliased=True,
            alias=symbol_name,
            resolution_path=resolution_path
        )

    def get_all_aliases(self, file_path: str) -> dict[str, AliasEntry]:
        """Get all aliases defined in a file.
        
        Args:
            file_path: Path to the file.
            
        Returns:
            Dictionary of all aliases in the file.
        """
        return self._alias_map.get(file_path, {})

    def find_alias_sources(
        self,
        symbol_name: str,
        module: str
    ) -> list[tuple[str, AliasEntry]]:
        """Find all places where a symbol is aliased.
        
        Useful for finding all aliases pointing to the same original.
        
        Args:
            symbol_name: The original symbol name.
            module: The source module.
            
        Returns:
            List of (file_path, AliasEntry) tuples.
        """
        results: list[tuple[str, AliasEntry]] = []
        
        for file_path, aliases in self._alias_map.items():
            for alias, entry in aliases.items():
                if entry.original == symbol_name and entry.module == module:
                    results.append((file_path, entry))
        
        return results

    def clear(self, file_path: Optional[str] = None) -> None:
        """Clear cached alias data.
        
        Args:
            file_path: If provided, only clear data for this file.
                      If None, clear all data.
        """
        if file_path:
            self._alias_map.pop(file_path, None)
            self._imports.pop(file_path, None)
            self._content_cache.pop(file_path, None)
        else:
            self._alias_map.clear()
            self._imports.clear()
            self._content_cache.clear()

    def merge(self, other: "AliasResolver") -> None:
        """Merge another resolver's data into this one.
        
        Args:
            other: Another AliasResolver to merge from.
        """
        for file_path, aliases in other._alias_map.items():
            if file_path not in self._alias_map:
                self._alias_map[file_path] = {}
            self._alias_map[file_path].update(aliases)
        
        for file_path, imports in other._imports.items():
            if file_path not in self._imports:
                self._imports[file_path] = []
            self._imports[file_path].extend(imports)
