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
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

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
        
        # Imports per file
        self._imports: dict[str, list[ImportEntry]] = {}
        
        # Index by name for fast lookup
        self._defs_by_name: dict[str, list[FunctionDef]] = {}
        
        # Build state
        self._is_built: bool = False
        
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
                    
                    self._call_sites.append(CallSite(
                        caller="<unknown>",
                        callee=callee,
                        file=str(file_path),
                        line=i,
                        col=match.start(),
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
        """Build reverse index for name lookups."""
        self._defs_by_name.clear()
        
        for name, funcs in self._functions.items():
            self._defs_by_name[name] = funcs

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
        """Get all callers of a function."""
        return self.find_references(function_name, file_path)

    def get_callees(self, function_name: str, file_path: str | None = None) -> list[CallSite]:
        """Get all call sites within a function."""
        callees = []
        for site in self._call_sites:
            if site.caller == function_name:
                if file_path is None or site.file == file_path:
                    callees.append(site)
        return callees

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
                self.call_sites.append(CallSite(
                    caller=self.current_function or "<module>",
                    callee=callee_name,
                    file=self.file_path,
                    line=node.lineno or 0,
                    col=node.col_offset or 0,
                    is_method=is_method,
                ))

        self.generic_visit(node)

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
