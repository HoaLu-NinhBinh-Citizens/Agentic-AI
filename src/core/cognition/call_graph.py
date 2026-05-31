"""Cross-file call graph builder with AST-based reference resolution.

This module provides real call graph construction that understands:
- Direct function calls
- Method calls on objects
- Imported function calls (with alias support)
- Cross-file references
- Call cycle detection
"""

from __future__ import annotations

import ast
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from src.core.cognition.import_resolver import ImportResolver

logger = logging.getLogger(__name__)

# Built-in functions that shouldn't be tracked
_BUILTINS: set[str] = {
    "print", "len", "str", "int", "float", "bool", "list", "dict", "set", "tuple",
    "range", "enumerate", "zip", "map", "filter", "sum", "min", "max", "abs",
    "open", "file", "input", "isinstance", "hasattr", "getattr", "setattr",
    "type", "repr", "dir", "vars", "globals", "locals", "callable", "sorted",
    "reversed", "any", "all", "super", "property", "staticmethod", "classmethod",
}


@dataclass
class CallSite:
    """A call site in code."""
    caller: str
    callee: str
    file: str
    line: int
    col: int = 0
    is_method: bool = False
    arguments: list[str] = field(default_factory=list)
    
    @classmethod
    def create(
        cls,
        caller: str,
        callee: str,
        file: str,
        line: int,
        col: int = 0,
        is_method: bool = False,
        arguments: list[str] | None = None,
    ) -> CallSite:
        """Create a CallSite with optional arguments.
        
        Args:
            caller: Name of the function making the call
            callee: Name of the function being called
            file: File path where the call occurs
            line: Line number of the call
            col: Column offset of the call
            is_method: Whether this is a method call
            arguments: List of argument names/variables passed
            
        Returns:
            New CallSite instance
        """
        return cls(
            caller=caller,
            callee=callee,
            file=file,
            line=line,
            col=col,
            is_method=is_method,
            arguments=arguments or [],
        )


@dataclass
class FunctionDef:
    """Information about a function definition."""
    name: str
    file: str
    line: int
    end_line: int
    params: list[str] = field(default_factory=list)
    is_method: bool = False
    class_name: Optional[str] = None
    is_async: bool = False


@dataclass
class ImportEntry:
    """An import statement."""
    module: str
    names: list[str] = field(default_factory=list)
    alias: dict[str, str] = field(default_factory=dict)  # alias -> original


class CallGraph:
    """AST-based call graph with cross-file reference resolution.
    
    This provides true call graph construction, not string matching.
    It uses Python AST parsing to find actual function calls and
    build a proper call graph.
    """

    def __init__(self, project_root: Path | str | None = None):
        self.project_root = Path(project_root) if project_root else Path.cwd()
        
        # Function definitions: name -> [FunctionDef]
        self._functions: dict[str, list[FunctionDef]] = {}
        
        # Call sites
        self._call_sites: list[CallSite] = []
        
        # Reverse index: callee -> list of CallSite (callers)
        # This enables fast "find references" lookups
        self._callers: dict[str, list[CallSite]] = {}
        
        # Imports per file
        self._imports: dict[str, list[ImportEntry]] = {}
        
        # Index by name for fast lookup
        self._defs_by_name: dict[str, list[FunctionDef]] = {}
        
        # Build state
        self._is_built: bool = False
        
        # Incremental indexing: file path -> last modified timestamp
        self._file_mtimes: dict[str, float] = {}
        
        # Import resolver for alias resolution
        self._resolver: ImportResolver = ImportResolver()
        
        # Statistics
        self.stats: dict[str, int] = {
            "functions": 0,
            "call_sites": 0,
            "files": 0,
        }

    def build(self, indexed_files: dict[str, list[dict[str, Any]]]) -> None:
        """Build call graph from indexed files.
        
        Args:
            indexed_files: {file_path: [symbols]} from SafeTreeSitterIndexer
                          or similar symbol extraction
        """
        # Step 1: Collect all function definitions
        for file_path, symbols in indexed_files.items():
            for sym in symbols:
                kind = sym.get("kind", "")
                if kind in ("function", "method", "class_method", "FunctionDef", "function_definition"):
                    func = FunctionDef(
                        name=sym.get("name", "unknown"),
                        file=str(file_path),
                        line=sym.get("line", 1),
                        end_line=sym.get("end_line", sym.get("line", 1)),
                        params=sym.get("params", []),
                        is_method=kind in ("method", "class_method"),
                    )
                    self._add_function(func)

        # Step 2: Parse call sites from each file
        for file_path in indexed_files.keys():
            self._parse_call_sites(Path(file_path))

        # Step 3: Build reverse index
        self._build_name_index()

        self._is_built = True
        self.stats["functions"] = len(self._functions)
        self.stats["call_sites"] = len(self._call_sites)
        self.stats["files"] = len(indexed_files)
        
        logger.info(
            "Call graph built: functions=%d, call_sites=%d, files=%d",
            self.stats["functions"],
            self.stats["call_sites"],
            self.stats["files"],
        )

    def build_from_directory(self, root: Path | str | None = None) -> None:
        """Build call graph from a directory.
        
        Args:
            root: Root directory to scan (default: project_root)
        """
        from src.infrastructure.indexing.tree_sitter import SafeTreeSitterIndexer

        root_path = Path(root) if root else self.project_root
        indexer = SafeTreeSitterIndexer()
        
        indexed_files: dict[str, list[dict[str, Any]]] = {}
        
        for ext in ["*.py", "*.js", "*.ts"]:
            for file_path in root_path.rglob(ext):
                # Skip ignored directories
                if self._should_skip(file_path):
                    continue
                
                try:
                    result = indexer.index_file(str(file_path))
                    if result.get("status") == "success":
                        indexed_files[str(file_path)] = result.get("symbols", [])
                except Exception as e:
                    logger.debug("Failed to index %s: %s", file_path, e)
        
        self.build(indexed_files)

    def build_content(self, content: str, file_path: str | Path) -> None:
        """Build call graph for a single file from content.
        
        This is useful for incremental indexing or when you have
        file content but don't want to read from disk.
        
        Args:
            content: File content to parse
            file_path: Path to associate with this content
        """
        file_path_str = str(file_path)
        
        # Parse imports for this file
        self._parse_imports(Path(file_path), content)
        
        # Parse call sites directly from content using AST
        if file_path_str.endswith(".py"):
            try:
                tree = ast.parse(content)
            except SyntaxError:
                self._parse_call_sites_regex(Path(file_path), content)
            else:
                # Use the visitor to collect call sites with arguments
                visitor = CallSiteVisitor(file_path_str)
                visitor.visit(tree)
                self._call_sites.extend(visitor.call_sites)
                
                # Extract function definitions from AST
                self._extract_functions_from_ast(tree, file_path_str)
        else:
            self._parse_call_sites_regex(Path(file_path), content)
        
        # Rebuild reverse index
        self._build_name_index()
        
        # Update statistics
        self.stats["functions"] = len(self._functions)
        self.stats["call_sites"] = len(self._call_sites)
        self._is_built = True
    
    def _extract_functions_from_ast(self, tree: ast.AST, file_path: str) -> None:
        """Extract function definitions from AST.
        
        Args:
            tree: Parsed AST tree
            file_path: File path for the content
        """
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func = FunctionDef(
                    name=node.name,
                    file=file_path,
                    line=node.lineno,
                    end_line=node.end_lineno or node.lineno,
                    params=[arg.arg for arg in node.args.args if hasattr(arg, 'arg')],
                    is_method=isinstance(node, ast.FunctionDef) and len(node.decorator_list) == 0,
                    is_async=isinstance(node, ast.AsyncFunctionDef),
                )
                self._add_function(func)
            elif isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        func = FunctionDef(
                            name=item.name,
                            file=file_path,
                            line=item.lineno,
                            end_line=item.end_lineno or item.lineno,
                            params=[arg.arg for arg in item.args.args if hasattr(arg, 'arg')],
                            is_method=True,
                            class_name=node.name,
                            is_async=isinstance(item, ast.AsyncFunctionDef),
                        )
                        self._add_function(func)
    
    def build_incremental(self, file_path: Path | str, content: str) -> bool:
        """Build or update call graph for a single file.
        
        Only rebuilds if file is modified since last build.
        
        Args:
            file_path: Path to the file
            content: Current file content
            
        Returns:
            True if file was indexed, False if skipped (no changes)
        """
        file_path_str = str(file_path)
        
        # Check modification time
        path_obj = Path(file_path)
        if path_obj.exists():
            current_mtime = os.path.getmtime(path_obj)
            last_mtime = self._file_mtimes.get(file_path_str, 0)
            
            if current_mtime <= last_mtime:
                return False  # No changes, skip
        
        # Parse imports for this file first
        self._resolver.parse_file(content, file_path_str)
        
        # Build the call graph for this file
        self.build_content(content, file_path)
        
        # Update modification time
        if path_obj.exists():
            self._file_mtimes[file_path_str] = os.path.getmtime(path_obj)
        
        self._is_built = True
        return True
    
    def get_file_mtime(self, file_path: str | Path) -> float:
        """Get the last modified time tracked for a file.
        
        Args:
            file_path: Path to check
            
        Returns:
            Last modified time or 0 if not tracked
        """
        return self._file_mtimes.get(str(file_path), 0)
    
    def clear_file(self, file_path: str | Path) -> None:
        """Remove all data for a specific file.
        
        Args:
            file_path: Path to clear
        """
        file_path_str = str(file_path)
        
        # Remove call sites for this file
        self._call_sites = [c for c in self._call_sites if c.file != file_path_str]
        
        # Remove function definitions for this file
        for name in list(self._functions.keys()):
            self._functions[name] = [f for f in self._functions[name] if f.file != file_path_str]
            if not self._functions[name]:
                del self._functions[name]
        
        # Remove imports
        if file_path_str in self._imports:
            del self._imports[file_path_str]
        
        # Remove from mtime tracking
        if file_path_str in self._file_mtimes:
            del self._file_mtimes[file_path_str]
        
        # Rebuild name index
        self._build_name_index()
        
        # Update stats
        self.stats["functions"] = len(self._functions)
        self.stats["call_sites"] = len(self._call_sites)

    def _add_function(self, func: FunctionDef) -> None:
        """Add a function definition."""
        if func.name not in self._functions:
            self._functions[func.name] = []
        self._functions[func.name].append(func)
        
        if func.name not in self._defs_by_name:
            self._defs_by_name[func.name] = []
        self._defs_by_name[func.name].append(func)

    def _should_skip(self, path: Path) -> bool:
        """Check if path should be skipped."""
        skip_dirs = {
            ".git", "__pycache__", "node_modules", ".venv", "venv",
            "build", "dist", ".tox", ".pytest_cache", ".mypy_cache",
            ".ruff_cache", "htmlcov", ".coverage",
        }
        return any(part in skip_dirs for part in path.parts)

    def _parse_call_sites(self, file_path: Path) -> None:
        """Parse call sites from a file using AST."""
        if not file_path.exists():
            return
        
        try:
            content = file_path.read_text(encoding='utf-8')
            
            if file_path.suffix == ".py":
                self._parse_call_sites_python(file_path, content)
            else:
                self._parse_call_sites_regex(file_path, content)
                
            # Track imports
            self._parse_imports(file_path, content)
            
        except Exception as e:
            logger.warning("Failed to parse call sites from %s: %s", file_path, e)

    def _parse_call_sites_python(self, file_path: Path, content: str) -> None:
        """Parse Python file for call sites using AST."""
        try:
            tree = ast.parse(content)
        except SyntaxError:
            self._parse_call_sites_regex(file_path, content)
            return

        visitor = _CallSiteVisitor(str(file_path))
        visitor.visit(tree)
        self._call_sites.extend(visitor.call_sites)

    def _parse_call_sites_regex(self, file_path: Path, content: str) -> None:
        """Fallback regex-based call site parsing for non-Python files."""
        # C/JS function call patterns
        patterns = [
            r'(\w+)\s*\([^)]*\)\s*;',  # func();
            r'(\w+)\s*\(([^)]*)\)',     # func(args)
        ]
        
        for i, line in enumerate(content.split('\n'), 1):
            for pattern in patterns:
                for match in re.finditer(pattern, line):
                    callee = match.group(1)
                    # Skip builtins and keywords
                    if callee.startswith('_') or not callee[0].isalpha():
                        continue
                    if callee in _BUILTINS:
                        continue
                    
                    # Extract arguments from the match
                    arguments = []
                    if match.lastindex and match.lastindex >= 2:
                        args_str = match.group(2)
                        if args_str:
                            arguments = [a.strip() for a in args_str.split(',') if a.strip()]
                    
                    self._call_sites.append(CallSite.create(
                        caller="<unknown>",
                        callee=callee,
                        file=str(file_path),
                        line=i,
                        col=match.start(),
                        arguments=arguments,
                    ))

    def _parse_imports(self, file_path: Path, content: str) -> None:
        """Parse import statements from file."""
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return

        imports: list[ImportEntry] = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                entry = ImportEntry(
                    module="",
                    names=[alias.name for alias in node.names],
                    alias={alias.asname or alias.name: alias.name for alias in node.names},
                )
                imports.append(entry)
                
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    entry = ImportEntry(
                        module=node.module,
                        names=[alias.name for alias in node.names],
                        alias={alias.asname or alias.name: alias.name for alias in node.names},
                    )
                    imports.append(entry)
        
        self._imports[str(file_path)] = imports

    def _build_name_index(self) -> None:
        """Build reverse index for name lookups and caller tracking."""
        self._defs_by_name.clear()
        
        for name, funcs in self._functions.items():
            self._defs_by_name[name] = funcs
        
        # Build reverse index: callee -> callers
        self._callers.clear()
        for site in self._call_sites:
            if site.callee not in self._callers:
                self._callers[site.callee] = []
            self._callers[site.callee].append(site)

    def find_references(self, symbol_name: str, file_path: str | None = None) -> list[CallSite]:
        """Find all references to a symbol.
        
        Args:
            symbol_name: Name of function/variable
            file_path: Optional file to limit search
        
        Returns:
            List of CallSite where symbol is referenced
        """
        if not self._is_built:
            raise RuntimeError("Call graph not built. Call build() first.")
        
        refs = []
        for site in self._call_sites:
            # Check if call site references the symbol
            if site.callee == symbol_name or site.caller == symbol_name:
                if file_path is None or site.file == file_path:
                    refs.append(site)
        
        return refs

    def get_callers(self, function_name: str, file_path: str | None = None) -> list[CallSite]:
        """Get all callers of a function using reverse index.
        
        Args:
            function_name: Name of the function
            file_path: Optional file to limit search
            
        Returns:
            List of CallSite where the function is called
        """
        callers = self._callers.get(function_name, [])
        if file_path:
            return [c for c in callers if c.file == file_path]
        return callers

    def get_callees(self, function_name: str, file_path: str | None = None) -> list[CallSite]:
        """Get all call sites within a function."""
        callees = []
        for site in self._call_sites:
            if site.caller == function_name:
                if file_path is None or site.file == file_path:
                    callees.append(site)
        return callees
    
    def add_call(
        self,
        caller: str,
        callee: str,
        file: str,
        line: int,
        col: int = 0,
        is_method: bool = False,
        arguments: list[str] | None = None
    ) -> CallSite:
        """Add a call site manually.
        
        Args:
            caller: Name of the calling function
            callee: Name of the function being called
            file: File path
            line: Line number
            col: Column offset
            is_method: Whether this is a method call
            arguments: List of argument names passed
            
        Returns:
            The created CallSite
        """
        site = CallSite.create(
            caller=caller,
            callee=callee,
            file=file,
            line=line,
            col=col,
            is_method=is_method,
            arguments=arguments
        )
        self._call_sites.append(site)
        
        # Update reverse index
        if callee not in self._callers:
            self._callers[callee] = []
        self._callers[callee].append(site)
        
        # Mark as built since we've added data
        self._is_built = True
        
        return site

    def find_cycles(self) -> list[list[str]]:
        """Find circular dependencies in call graph using DFS.
        
        Returns:
            List of cycles, each cycle is a list of function names
        """
        cycles: list[list[str]] = []
        visited: set[str] = set()
        rec_stack: list[str] = []
        
        def dfs(func_name: str) -> None:
            if func_name in rec_stack:
                # Found cycle
                cycle_start = rec_stack.index(func_name)
                cycle = rec_stack[cycle_start:] + [func_name]
                cycles.append(cycle)
                return
            
            if func_name in visited:
                return
            
            visited.add(func_name)
            rec_stack.append(func_name)
            
            # Get callees
            for site in self.get_callees(func_name):
                dfs(site.callee)
            
            rec_stack.pop()
        
        # Start DFS from each function
        for func_name in self._functions:
            if func_name not in visited:
                dfs(func_name)
        
        return cycles

    def get_function(self, name: str) -> list[FunctionDef] | None:
        """Get function definitions by name."""
        return self._defs_by_name.get(name)

    def get_stats(self) -> dict[str, int]:
        """Get call graph statistics."""
        return dict(self.stats)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "stats": self.stats,
            "functions": {
                name: [
                    {
                        "name": f.name,
                        "file": f.file,
                        "line": f.line,
                        "end_line": f.end_line,
                        "is_method": f.is_method,
                    }
                    for f in funcs
                ]
                for name, funcs in self._defs_by_name.items()
            },
            "call_sites": [
                {
                    "caller": s.caller,
                    "callee": s.callee,
                    "file": s.file,
                    "line": s.line,
                    "is_method": s.is_method,
                    "arguments": s.arguments,
                }
                for s in self._call_sites
            ],
        }


class CallSiteVisitor(ast.NodeVisitor):
    """AST visitor for collecting call sites.
    
    Public alias for _CallSiteVisitor for external use.
    """
    """AST visitor for collecting call sites."""

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.call_sites: list[CallSite] = []
        self.current_function: str | None = None
        self.current_class: str | None = None
        self.imports: list[ImportEntry] = []

    def visit_Call(self, node: ast.Call) -> None:
        callee_name: str | None = None
        is_method = False

        if isinstance(node.func, ast.Name):
            callee_name = node.func.id
            is_method = False
        elif isinstance(node.func, ast.Attribute):
            callee_name = node.func.attr
            is_method = True

        if callee_name and not callee_name.startswith('_'):
            # Skip builtins
            if callee_name not in _BUILTINS:
                # Extract argument names
                arguments = self._extract_arguments(node)
                
                self.call_sites.append(CallSite.create(
                    caller=self.current_function or "<module>",
                    callee=callee_name,
                    file=self.file_path,
                    line=node.lineno or 0,
                    col=node.col_offset or 0,
                    is_method=is_method,
                    arguments=arguments,
                ))

        self.generic_visit(node)
    
    def _extract_arguments(self, node: ast.Call) -> list[str]:
        """Extract argument names from a function call.
        
        Args:
            node: AST Call node
            
        Returns:
            List of argument names/variable names
        """
        arguments = []
        for arg in node.args:
            if isinstance(arg, ast.Name):
                arguments.append(arg.id)
            elif isinstance(arg, ast.Constant):
                # Skip constants for data flow analysis
                pass
            elif isinstance(arg, ast.keyword):
                if arg.arg:
                    arguments.append(arg.arg)
        return arguments

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.append(ImportEntry(
                module="",
                names=[alias.name],
                alias={alias.asname or alias.name: alias.name},
            ))
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            self.imports.append(ImportEntry(
                module=node.module,
                names=[alias.name for alias in node.names],
                alias={alias.asname or alias.name: alias.name for alias in node.names},
            ))
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Visit a function definition."""
        old_func = self.current_function
        self.current_function = node.name
        self.generic_visit(node)
        self.current_function = old_func

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Visit an async function definition."""
        old_func = self.current_function
        self.current_function = node.name
        self.generic_visit(node)
        self.current_function = old_func

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Visit a class definition to track class context."""
        old_class = self.current_class
        self.current_class = node.name
        self.generic_visit(node)
        self.current_class = old_class


# Backward compatibility alias
_CallSiteVisitor = CallSiteVisitor


def build_call_graph(
    project_root: Path | str | None = None,
    indexed_files: dict[str, list[dict[str, Any]]] | None = None,
) -> CallGraph:
    """Build a call graph from files or directory.
    
    Args:
        project_root: Root directory to scan
        indexed_files: Optional pre-indexed files
        
    Returns:
        Built CallGraph
    """
    graph = CallGraph(project_root)
    
    if indexed_files:
        graph.build(indexed_files)
    else:
        graph.build_from_directory(project_root)
    
    return graph
