"""Import resolver for resolving alias imports to original modules.

This module provides alias resolution for imports, enabling the call graph
to correctly track imported function calls across files.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ResolvedImport:
    """An import entry with resolved module information."""
    module: str
    name: str
    alias: Optional[str] = None
    resolved_module: Optional[str] = None
    
    @property
    def resolved_name(self) -> str:
        """Get the resolved name (alias or original)."""
        return self.alias if self.alias else self.name
    
    @property
    def full_name(self) -> str:
        """Get the full qualified name."""
        if self.module:
            return f"{self.module}.{self.name}"
        return self.name


class ImportResolver:
    """Resolve import aliases to original module names.
    
    This class tracks import statements and their aliases, allowing
    the call graph to correctly resolve aliased imports to their
    original module names.
    """
    
    def __init__(self) -> None:
        # alias -> ResolvedImport mapping
        self._aliases: dict[str, ResolvedImport] = {}
        # full qualified name -> original name
        self._module_aliases: dict[str, str] = {}
        # per-file imports
        self._file_imports: dict[str, list[ResolvedImport]] = {}
    
    def add_import(
        self,
        module: str,
        name: str,
        alias: Optional[str] = None,
        file_path: Optional[str] = None
    ) -> None:
        """Add an import entry.
        
        Args:
            module: The module being imported from
            name: The name being imported
            alias: Optional alias for the import
            file_path: Optional file path for tracking imports per-file
        """
        entry = ResolvedImport(
            module=module,
            name=name,
            alias=alias
        )
        
        key = alias if alias else name
        self._aliases[key] = entry
        
        # Build full qualified name
        if module:
            full_name = f"{module}.{name}"
            self._module_aliases[full_name] = full_name
            self._module_aliases[name] = full_name
            if alias:
                self._module_aliases[alias] = full_name
        else:
            self._module_aliases[name] = name
            if alias:
                self._module_aliases[alias] = name
        
        # Track per-file imports
        if file_path:
            if file_path not in self._file_imports:
                self._file_imports[file_path] = []
            self._file_imports[file_path].append(entry)
    
    def resolve(self, name: str) -> Optional[str]:
        """Resolve a name to its original module.
        
        Args:
            name: Name to resolve (alias or original)
            
        Returns:
            Original full name or None
        """
        return self._module_aliases.get(name)
    
    def get_import(self, name: str) -> Optional[ResolvedImport]:
        """Get import entry for a name.
        
        Args:
            name: Name to look up
            
        Returns:
            ResolvedImport entry or None
        """
        return self._aliases.get(name)
    
    def get_file_imports(self, file_path: str) -> list[ResolvedImport]:
        """Get all imports from a specific file.
        
        Args:
            file_path: Path to the file
            
        Returns:
            List of imports from that file
        """
        return self._file_imports.get(file_path, [])
    
    def parse_file(self, content: str, file_path: Optional[str] = None) -> ImportResolver:
        """Parse imports from file content.
        
        Args:
            content: File content to parse
            file_path: Optional file path for tracking
            
        Returns:
            ImportResolver with parsed imports
        """
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return self
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.add_import(
                        module='',
                        name=alias.name,
                        alias=alias.asname,
                        file_path=file_path
                    )
            
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    for alias in node.names:
                        self.add_import(
                            module=node.module,
                            name=alias.name,
                            alias=alias.asname,
                            file_path=file_path
                        )
        
        return self
    
    def clear(self) -> None:
        """Clear all resolved imports."""
        self._aliases.clear()
        self._module_aliases.clear()
        self._file_imports.clear()
    
    def copy(self) -> ImportResolver:
        """Create a copy of this resolver.
        
        Returns:
            New ImportResolver with same state
        """
        resolver = ImportResolver()
        resolver._aliases = dict(self._aliases)
        resolver._module_aliases = dict(self._module_aliases)
        resolver._file_imports = {k: list(v) for k, v in self._file_imports.items()}
        return resolver
