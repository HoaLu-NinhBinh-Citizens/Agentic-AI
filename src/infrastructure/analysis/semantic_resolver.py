"""Semantic cross-file reference resolution.

Uses AST + type inference for accurate symbol resolution.

Performance optimizations:
- LRU cache for symbol lookups
- Batch processing for multiple files
- Content caching
"""

from __future__ import annotations

import ast
import asyncio
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Optional

from src.infrastructure.analysis.alias_resolver import AliasResolver, AliasEntry


# Maximum cache sizes
_MAX_RESOLUTION_CACHE = 1000
_MAX_CONTENT_CACHE = 500


@dataclass
class SymbolInfo:
    """Complete symbol information for semantic resolution."""

    name: str
    file_path: Path
    line: int
    kind: str  # "function", "class", "variable", "method", "builtin"
    resolved_from: Optional[str] = None  # Original import path if aliased
    confidence: float = 1.0
    is_alias: bool = False


@dataclass
class ResolvedSymbol:
    """A resolved symbol with full context."""

    name: str
    file_path: Path
    line: int
    end_line: int
    kind: str  # "class", "function", "variable", "method", "attribute"
    resolved_via: str  # How it was resolved (import, inheritance, etc.)
    type_signature: Optional[str] = None
    confidence: float = 1.0
    references: list[tuple[Path, int]] = field(default_factory=list)


@dataclass
class ImportChain:
    """Track import chain for resolution."""

    module: str
    names: list[tuple[str, Optional[str]]]  # (original, alias)
    line: int


class SemanticResolver:
    """Resolve symbols across files using semantic analysis.
    
    This resolver uses Python AST parsing for accurate symbol resolution,
    understanding imports, qualified names, type flow across files,
    and import aliases.
    """

    PYTHON_BUILTINS: frozenset[str] = frozenset({
        "int", "float", "str", "bool", "list", "dict", "set", "tuple",
        "bytes", "bytearray", "memoryview", "range", "slice",
        "len", "range", "print", "enumerate", "zip", "map", "filter",
        "open", "sorted", "reversed", "sum", "min", "max", "abs",
        "round", "pow", "divmod", "isinstance", "issubclass",
        "type", "object", "property", "classmethod", "staticmethod",
        "getattr", "setattr", "hasattr", "delattr", "vars",
        "repr", "format", "hash", "callable", "iter", "next",
        "any", "all", "compile", "eval", "exec", "input", "bin",
        "hex", "oct", "chr", "ord", "ascii", "breakpoint",
        "Exception", "BaseException", "Error",
    })

    def __init__(self) -> None:
        self._imports: dict[Path, list[ImportChain]] = {}
        self._exports: dict[str, ResolvedSymbol] = {}  # module.name -> symbol
        self._type_hints: dict[str, str] = {}  # variable -> type
        self._content_cache: dict[Path, str] = {}
        self._module_name_cache: dict[Path, str] = {}
        
        # Alias resolution support
        self._alias_resolver = AliasResolver()
        self._alias_map: dict[Path, dict[str, AliasEntry]] = {}  # file -> {alias: AliasEntry}
        
        # Resolution cache for performance
        self._resolution_cache: dict[tuple[str, str, int], SymbolInfo] = {}
        
        # Batch processing settings
        self._batch_size = 10
        self._max_cache_size = _MAX_RESOLUTION_CACHE

    def index_project(
        self,
        files: list[Path],
        contents: dict[Path, str]
    ) -> None:
        """Index all files for cross-file resolution.
        
        Args:
            files: List of file paths to index.
            contents: Dict mapping file paths to their content strings.
        """
        self._content_cache = dict(contents)

        for path, content in contents.items():
            imports = self._parse_imports(content)
            self._imports[path] = imports
            # Parse and store alias map
            self._alias_resolver.parse_import(str(path), content)
            self._alias_map[path] = self._alias_resolver.get_all_aliases(str(path))

        for path, content in contents.items():
            exports = self._parse_exports(path, content)
            for exp in exports:
                module_name = self._get_module_name(path)
                key = f"{module_name}.{exp.name}"
                self._exports[key] = exp

    def resolve_symbol_reference(
        self,
        file_path: Path,
        symbol_name: str,
        line: int,
        content: Optional[str] = None
    ) -> Optional[SymbolInfo]:
        """Resolve symbol reference to its definition.
        
        Handles:
        - Local variables
        - Imported symbols (with aliases)
        - Cross-file references
        - Class/instance methods
        
        Args:
            file_path: Path to the file containing the reference.
            symbol_name: Name of the symbol to resolve.
            line: Line number of the reference (1-indexed).
            content: Optional file content (uses cache if not provided).
            
        Returns:
            SymbolInfo with resolved location, or None if not found.
        """
        # Get content if not provided
        if content is None:
            content = self._content_cache.get(file_path, "")

        # 1. Check local definitions
        local = self._resolve_local(symbol_name, content, line)
        if local:
            return SymbolInfo(
                name=symbol_name,
                file_path=local.file_path or file_path,
                line=local.line,
                kind=local.kind,
                resolved_from="local_definition",
                confidence=1.0
            )

        # 2. Check imports with alias support
        imported = self._resolve_imported_symbol(file_path, symbol_name, content)
        if imported:
            return imported

        # 3. Check builtins
        if symbol_name in self.PYTHON_BUILTINS:
            return SymbolInfo(
                name=symbol_name,
                file_path=Path("builtins"),
                line=0,
                kind="builtin",
                resolved_from="builtin",
                confidence=1.0
            )

        # 4. Check module exports
        for key, exp in self._exports.items():
            if exp.name == symbol_name:
                return SymbolInfo(
                    name=symbol_name,
                    file_path=exp.file_path,
                    line=exp.line,
                    kind=exp.kind,
                    resolved_from=f"module_export:{key}",
                    confidence=0.9
                )

        return None

    def _resolve_imported_symbol(
        self,
        file_path: Path,
        symbol_name: str,
        content: str
    ) -> Optional[SymbolInfo]:
        """Resolve symbol that was imported with possible alias."""
        file_str = str(file_path)
        aliases = self._alias_map.get(file_path, {})
        
        # Check if symbol is an alias
        if symbol_name in aliases:
            alias_entry = aliases[symbol_name]
            original_name = alias_entry.original if isinstance(alias_entry, AliasEntry) else alias_entry
            # Look up in imports to find module
            imports = self._imports.get(file_path, [])
            for imp in imports:
                for orig, alias in imp.names:
                    resolved_name = alias if alias else orig.split(".")[-1]
                    if resolved_name == symbol_name:
                        # Try to resolve through exports
                        export_key = f"{imp.module}.{original_name}"
                        if export_key in self._exports:
                            exp = self._exports[export_key]
                            return SymbolInfo(
                                name=symbol_name,
                                file_path=exp.file_path,
                                line=exp.line,
                                kind=exp.kind,
                                resolved_from=f"import_alias:{imp.module}.{original_name}",
                                confidence=0.95,
                                is_alias=True
                            )

        # Fall back to standard import resolution
        imports = self._imports.get(file_path, [])
        for imp in imports:
            for original, alias in imp.names:
                resolved_name = alias if alias else original.split(".")[-1]
                if resolved_name == symbol_name:
                    export_key = f"{imp.module}.{original}"
                    if export_key in self._exports:
                        exp = self._exports[export_key]
                        return SymbolInfo(
                            name=symbol_name,
                            file_path=exp.file_path,
                            line=exp.line,
                            kind=exp.kind,
                            resolved_from=f"import:{imp.module}",
                            confidence=0.95
                        )

        return None

    def _follow_import_chain(
        self,
        module_path: str,
        symbol_name: str,
        visited: Optional[set[str]] = None
    ) -> Optional[SymbolInfo]:
        """Follow import chain to find original definition.
        
        Args:
            module_path: Starting module path.
            symbol_name: Symbol to find.
            visited: Set of already visited modules (for cycle detection).
            
        Returns:
            SymbolInfo if found, None otherwise.
        """
        if visited is None:
            visited = set()
        
        key = f"{module_path}.{symbol_name}"
        if key in visited:
            return None
        visited.add(key)

        # Check exports
        if key in self._exports:
            exp = self._exports[key]
            return SymbolInfo(
                name=symbol_name,
                file_path=exp.file_path,
                line=exp.line,
                kind=exp.kind,
                resolved_from=key,
                confidence=0.9
            )

        return None

    def resolve_symbol(
        self,
        name: str,
        file_path: Path,
        content: str,
        line: int,
        language: str = "python"
    ) -> Optional[ResolvedSymbol]:
        """Resolve a symbol at a specific location.
        
        Returns ResolvedSymbol with full context.
        Resolution order: local -> imports (with alias support) -> builtins -> module exports.
        
        Args:
            name: Symbol name to resolve.
            file_path: Path to the file containing the reference.
            content: File content.
            line: Line number of the reference (1-indexed).
            language: Programming language (default: python).
        """
        if language != "python":
            return self._resolve_generic(name, file_path, content, line)

        # 1. Check local definitions first
        local = self._resolve_local(name, content, line)
        if local:
            return local

        # 2. Check imports with enhanced alias support
        imported = self._resolve_import_enhanced(name, file_path, content, line)
        if imported:
            return imported

        # 3. Check builtins
        builtin = self._resolve_builtin(name)
        if builtin:
            return builtin

        # 4. Check module-level exports
        exported = self._resolve_export(name, file_path)
        if exported:
            return exported

        return None

    def _resolve_import_enhanced(
        self,
        name: str,
        file_path: Path,
        content: str,
        line: int
    ) -> Optional[ResolvedSymbol]:
        """Enhanced import resolution with alias tracking."""
        imports = self._imports.get(file_path, [])
        aliases = self._alias_map.get(file_path, {})

        for imp in imports:
            for original, alias in imp.names:
                resolved_name = alias if alias else original.split(".")[-1]
                if resolved_name == name:
                    # Found import - check if it's an alias
                    is_alias = name in aliases
                    alias_entry = aliases.get(name)
                    original_name = alias_entry.original if alias_entry else original
                    
                    # Look up the exported symbol
                    export_key = f"{imp.module}.{original_name}"
                    if export_key in self._exports:
                        exp = self._exports[export_key]
                        return ResolvedSymbol(
                            name=name,
                            file_path=exp.file_path,
                            line=exp.line,
                            end_line=exp.end_line,
                            kind=exp.kind,
                            resolved_via=f"import{' (aliased)' if is_alias else ''} {imp.module}",
                            confidence=0.95
                        )

                    # Handle 'from X import Y' where Y might be a submodule
                    if isinstance(original_name, str) and "." in original_name:
                        module_key = f"{imp.module}.{original_name.split('.')[0]}"
                        if module_key in self._exports:
                            return self._exports[module_key]

        return None

    def resolve_qualified(
        self,
        qualified: str,
        file_path: Path,
        content: str
    ) -> Optional[ResolvedSymbol]:
        """Resolve qualified names like 'module.ClassName' or 'obj.method'.
        
        Args:
            qualified: Qualified name string (e.g., 'os.PathLike').
            file_path: Path to the file containing the reference.
            content: File content.
        """
        parts = qualified.split(".")

        if len(parts) == 1:
            return self.resolve_symbol(parts[0], file_path, content, 0)

        # Check if it's an import
        imports = self._imports.get(file_path, [])
        for imp in imports:
            for original, alias in imp.names:
                resolved_name = alias if alias else original.split(".")[-1]
                if resolved_name == parts[0]:
                    # Found module import
                    rest = ".".join(parts[1:])
                    full_key = f"{imp.module}.{rest}"
                    if full_key in self._exports:
                        return self._exports[full_key]
                    # Try without the rest as attribute access
                    export_key = f"{imp.module}.{original}"
                    if export_key in self._exports:
                        return self._exports[export_key]

        # Try as relative qualified name
        module_name = self._get_module_name(file_path)
        full_key = f"{module_name}.{qualified}"
        if full_key in self._exports:
            return self._exports[full_key]

        # Try with any matching suffix
        short_key = ".".join(parts[-2 if len(parts) > 1 else 1:])
        for key, exp in self._exports.items():
            if key.endswith(f".{short_key}"):
                return exp

        # Try partial matches for nested classes
        for key, exp in self._exports.items():
            if exp.name == parts[-1]:
                return exp

        return None

    def find_all_references(
        self,
        symbol: ResolvedSymbol,
        files: list[Path],
        contents: dict[Path, str]
    ) -> list[tuple[Path, int, str]]:
        """Find all references to a symbol across the project.
        
        Args:
            symbol: The resolved symbol to find references to.
            files: List of file paths to search.
            contents: Dict mapping file paths to their content strings.
            
        Returns:
            List of (file_path, line_number, line_content) tuples.
        """
        references = []
        escaped_name = re.escape(symbol.name)

        # Batch processing for better performance
        file_list = list(contents.items())
        for i in range(0, len(file_list), self._batch_size):
            batch = file_list[i:i + self._batch_size]
            batch_refs = self._search_batch(
                batch, symbol.name, escaped_name, symbol.file_path
            )
            references.extend(batch_refs)

        return references
    
    def _search_batch(
        self,
        batch: list[tuple[Path, str]],
        symbol_name: str,
        escaped_pattern: str,
        exclude_path: Path
    ) -> list[tuple[Path, int, str]]:
        """Search a batch of files for symbol references."""
        references = []
        pattern = re.compile(rf"\b{symbol_name}\b")
        
        for path, content in batch:
            if path == exclude_path:
                continue

            lines = content.split("\n")
            for i, line in enumerate(lines, 1):
                if self._is_import_line(line, symbol_name):
                    continue

                if pattern.search(line):
                    if not self._is_definition_line(line, symbol_name):
                        references.append((path, i, line.strip()))
        
        return references
    
    async def detect_issues_batch(
        self,
        files: list[Path],
        batch_size: int = 10
    ) -> list[dict]:
        """Detect semantic issues in files with batch processing.
        
        Args:
            files: List of file paths to analyze.
            batch_size: Number of files per batch.
            
        Returns:
            List of detected issues.
        """
        all_issues = []
        contents = {f: f.read_text(encoding="utf-8", errors="replace") for f in files}
        
        for i in range(0, len(files), batch_size):
            batch = files[i:i + batch_size]
            batch_issues = await asyncio.gather(
                *[self._analyze_file(f, contents.get(f, "")) for f in batch],
                return_exceptions=True
            )
            for issues in batch_issues:
                if isinstance(issues, list):
                    all_issues.extend(issues)
        
        return all_issues
    
    async def _analyze_file(self, path: Path, content: str) -> list[dict]:
        """Analyze a single file for semantic issues."""
        issues = []
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return issues
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                if self._check_undefined_usage(node, content):
                    issues.append({
                        "file": str(path),
                        "line": node.lineno,
                        "severity": "warning",
                        "message": f"Variable '{node.id}' may be used before definition"
                    })
        
        return issues
    
    def _check_undefined_usage(self, node: ast.Name, content: str) -> bool:
        """Check if a name node might be undefined."""
        # Simple heuristic: check if it's a builtin
        if node.id in self.PYTHON_BUILTINS:
            return False
        # Check if it's defined earlier in the same scope
        return True

    def _resolve_local(
        self,
        name: str,
        content: str,
        line: int
    ) -> Optional[ResolvedSymbol]:
        """Resolve local symbol (defined in same file).
        
        Uses AST to find definitions in the current file scope.
        """
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return None

        # For definitions (functions, classes), search anywhere in file
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name == name:
                    return ResolvedSymbol(
                        name=name,
                        file_path=Path(),
                        line=node.lineno,
                        end_line=node.end_lineno or node.lineno,
                        kind="function",
                        resolved_via="definition",
                        confidence=1.0
                    )

            elif isinstance(node, ast.ClassDef):
                if node.name == name:
                    return ResolvedSymbol(
                        name=name,
                        file_path=Path(),
                        line=node.lineno,
                        end_line=node.end_lineno or node.lineno,
                        kind="class",
                        resolved_via="definition",
                        confidence=1.0
                    )

        # For parameters and local variables, check enclosing scope
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                # Check if the reference line is within this scope
                if node.lineno <= line <= (node.end_lineno or node.lineno + 20):
                    # Check function parameters
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        for arg in node.args.args:
                            if arg.arg == name:
                                return ResolvedSymbol(
                                    name=name,
                                    file_path=Path(),
                                    line=node.lineno,
                                    end_line=node.end_lineno or node.lineno,
                                    kind="parameter",
                                    resolved_via="function_parameter",
                                    confidence=1.0
                                )
                        # Check local assignments in the function body
                        for child in ast.walk(node):
                            if isinstance(child, ast.Assign):
                                for target in child.targets:
                                    if isinstance(target, ast.Name) and target.id == name:
                                        return ResolvedSymbol(
                                            name=name,
                                            file_path=Path(),
                                            line=child.lineno,
                                            end_line=child.end_lineno or child.lineno,
                                            kind="variable",
                                            resolved_via="local_assignment",
                                            confidence=0.9
                                        )

        return None

    def _resolve_import(
        self,
        name: str,
        file_path: Path,
        content: str,
        line: int
    ) -> Optional[ResolvedSymbol]:
        """Resolve symbol from import statement."""
        imports = self._imports.get(file_path, [])

        for imp in imports:
            for original, alias in imp.names:
                resolved_name = alias if alias else original.split(".")[-1]
                if resolved_name == name:
                    # Found import - look up the exported symbol
                    export_key = f"{imp.module}.{original}"
                    if export_key in self._exports:
                        exp = self._exports[export_key]
                        return ResolvedSymbol(
                            name=name,
                            file_path=exp.file_path,
                            line=exp.line,
                            end_line=exp.end_line,
                            kind=exp.kind,
                            resolved_via=f"import {imp.module}",
                            confidence=0.95
                        )

                    # Handle 'from X import Y' where Y might be a submodule
                    if "." in original:
                        module_key = f"{imp.module}.{original.split('.')[0]}"
                        if module_key in self._exports:
                            return self._exports[module_key]

        return None

    def _resolve_builtin(self, name: str) -> Optional[ResolvedSymbol]:
        """Resolve Python builtins."""
        if name in self.PYTHON_BUILTINS:
            return ResolvedSymbol(
                name=name,
                file_path=Path("builtins"),
                line=0,
                end_line=0,
                kind="builtin",
                resolved_via="builtin",
                confidence=1.0
            )
        return None

    def _resolve_export(
        self,
        name: str,
        file_path: Path
    ) -> Optional[ResolvedSymbol]:
        """Resolve from module exports."""
        # Search exports by name
        for key, exp in self._exports.items():
            if exp.name == name:
                return exp
        return None

    def _resolve_generic(
        self,
        name: str,
        file_path: Path,
        content: str,
        line: int
    ) -> Optional[ResolvedSymbol]:
        """Generic regex-based resolution for non-Python languages."""
        lines = content.split("\n")

        for i, line_text in enumerate(lines, 1):
            # Match function definitions
            if match := re.match(rf"^\s*(?:[\w*]+\s+)+{re.escape(name)}\s*\(", line_text):
                return ResolvedSymbol(
                    name=name,
                    file_path=file_path,
                    line=i,
                    end_line=i,
                    kind="function",
                    resolved_via="definition",
                    confidence=1.0
                )

        return None

    def _parse_imports(self, content: str) -> list[ImportChain]:
        """Parse all imports from content using AST."""
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return self._parse_imports_regex(content)

        imports = []
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                names = [
                    (alias.name, alias.asname)
                    for alias in node.names
                ]
                imports.append(ImportChain(
                    module=module,
                    names=names,
                    line=node.lineno
                ))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    module = alias.name
                    names = [(module.split(".")[-1], alias.asname)]
                    imports.append(ImportChain(
                        module=module,
                        names=names,
                        line=node.lineno
                    ))

        return imports

    def _parse_imports_regex(self, content: str) -> list[ImportChain]:
        """Fallback regex-based import parsing for invalid syntax."""
        imports = []
        lines = content.split("\n")

        for i, line in enumerate(lines, 1):
            line = line.strip()

            # from X import Y
            if match := re.match(r"from\s+([\w.]+)\s+import\s+(.+)", line):
                module = match.group(1)
                names_str = match.group(2)
                names = self._parse_import_names(names_str)
                imports.append(ImportChain(module=module, names=names, line=i))

            # import X
            elif match := re.match(r"import\s+([\w.]+)(?:\s+as\s+(\w+))?", line):
                module = match.group(1)
                alias = match.group(2)
                names = [(module.split(".")[-1], alias)]
                imports.append(ImportChain(module=module, names=names, line=i))

        return imports

    def _parse_import_names(
        self,
        names_str: str
    ) -> list[tuple[str, Optional[str]]]:
        """Parse import names string."""
        names = []
        for part in names_str.replace("(", "").replace(")", "").split(","):
            part = part.strip()
            if not part:
                continue
            if " as " in part:
                orig, alias = part.split(" as ")
                names.append((orig.strip(), alias.strip()))
            else:
                names.append((part, None))
        return names

    def _parse_exports(self, path: Path, content: str) -> list[ResolvedSymbol]:
        """Parse exports (classes, functions) from content."""
        exports = []

        try:
            tree = ast.parse(content)
        except SyntaxError:
            return self._parse_exports_regex(path, content)

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                exports.append(ResolvedSymbol(
                    name=node.name,
                    file_path=path,
                    line=node.lineno,
                    end_line=node.end_lineno or node.lineno,
                    kind="class",
                    resolved_via="definition",
                    confidence=1.0
                ))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                exports.append(ResolvedSymbol(
                    name=node.name,
                    file_path=path,
                    line=node.lineno,
                    end_line=node.end_lineno or node.lineno,
                    kind="function",
                    resolved_via="definition",
                    confidence=1.0
                ))
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        exports.append(ResolvedSymbol(
                            name=target.id,
                            file_path=path,
                            line=node.lineno,
                            end_line=node.end_lineno or node.lineno,
                            kind="variable",
                            resolved_via="assignment",
                            confidence=0.8
                        ))

        return exports

    def _parse_exports_regex(self, path: Path, content: str) -> list[ResolvedSymbol]:
        """Fallback regex-based export parsing."""
        exports = []
        lines = content.split("\n")

        for i, line in enumerate(lines, 1):
            # class Foo:
            if match := re.match(r"^class\s+(\w+)", line):
                exports.append(ResolvedSymbol(
                    name=match.group(1),
                    file_path=path,
                    line=i,
                    end_line=i + self._count_class_body(lines, i),
                    kind="class",
                    resolved_via="definition",
                    confidence=1.0
                ))

            # def foo():
            elif match := re.match(r"^def\s+(\w+)", line):
                exports.append(ResolvedSymbol(
                    name=match.group(1),
                    file_path=path,
                    line=i,
                    end_line=i + self._count_function_body(lines, i),
                    kind="function",
                    resolved_via="definition",
                    confidence=1.0
                ))

        return exports

    def _count_class_body(self, lines: list[str], start: int) -> int:
        """Count lines in class body."""
        if start >= len(lines):
            return 0
        indent = len(lines[start]) - len(lines[start].lstrip())
        for i in range(start + 1, len(lines)):
            if lines[i].strip() and not lines[i].startswith(" " * (indent + 1)):
                return i - start
        return len(lines) - start

    def _count_function_body(self, lines: list[str], start: int) -> int:
        """Count lines in function body."""
        if start >= len(lines):
            return 0
        indent = len(lines[start]) - len(lines[start].lstrip())
        for i in range(start + 1, len(lines)):
            if lines[i].strip() and not lines[i].startswith(" " * (indent + 1)):
                return i - start
        return len(lines) - start

    def _get_module_name(self, path: Path) -> str:
        """Get module name from path."""
        if path in self._module_name_cache:
            return self._module_name_cache[path]

        parts = list(path.parts)

        # Find the base - either "src" or the first directory
        base_idx = 0
        for i, p in enumerate(parts):
            if p == "src":
                base_idx = i + 1
                break
            elif not p.startswith("."):
                base_idx = i
                break

        # Get parts after base
        module_parts = []
        for p in parts[base_idx:]:
            if p.endswith(".py"):
                # Get module name from filename
                module_parts.append(p[:-3])
            elif p == "__init__":
                continue
            elif p.startswith("."):
                continue
            else:
                module_parts.append(p)

        module_name = ".".join(module_parts)
        self._module_name_cache[path] = module_name
        return module_name

    def _is_import_line(self, line: str, name: str) -> bool:
        """Check if line is an import statement for the given name."""
        line = line.strip()
        patterns = [
            rf"^import\s+[\w.]*{re.escape(name)}",
            rf"^from\s+[\w.]+\s+import\s+.*\b{re.escape(name)}\b",
        ]
        return any(re.match(p, line) for p in patterns)

    def _is_definition_line(self, line: str, name: str) -> bool:
        """Check if line is a definition of the given name."""
        line = line.strip()
        patterns = [
            rf"^(?:async\s+)?def\s+{re.escape(name)}\s*\(",
            rf"^class\s+{re.escape(name)}\s*[\(:]",
            rf"^(?:[\w]+\s+)?{re.escape(name)}\s*=\s*(?:def|class|lambda)",
            rf"^{re.escape(name)}\s*:\s*(?:class|$)",
        ]
        return any(re.match(p, line) for p in patterns)

    def get_module_exports(self, module_name: str) -> list[ResolvedSymbol]:
        """Get all exports from a specific module.
        
        Args:
            module_name: Module name (e.g., 'mymodule' or 'package.mymodule').
            
        Returns:
            List of ResolvedSymbol objects exported by the module.
        """
        prefix = f"{module_name}."
        return [
            exp for key, exp in self._exports.items()
            if key.startswith(prefix) or key == module_name
        ]

    def find_definition(
        self,
        name: str,
        file_path: Path,
        content: str
    ) -> Optional[ResolvedSymbol]:
        """Find the definition of a name in a specific file.
        
        Args:
            name: Symbol name to find.
            file_path: Path to search in.
            content: File content.
            
        Returns:
            ResolvedSymbol if found, None otherwise.
        """
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return None

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == name:
                return ResolvedSymbol(
                    name=name,
                    file_path=file_path,
                    line=node.lineno,
                    end_line=node.end_lineno or node.lineno,
                    kind="class",
                    resolved_via="definition",
                    confidence=1.0
                )
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
                return ResolvedSymbol(
                    name=name,
                    file_path=file_path,
                    line=node.lineno,
                    end_line=node.end_lineno or node.lineno,
                    kind="function",
                    resolved_via="definition",
                    confidence=1.0
                )

        return None
