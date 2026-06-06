"""Cross-language support extension for CallGraph.

This module provides extensions to CallGraph for handling multiple languages
(Python, C/C++, JavaScript/TypeScript) beyond Python-only AST parsing.

Usage:
    from src.core.cognition.call_graph_extensions import extend_call_graph
    
    # Extend an existing CallGraph with cross-language support
    extended_graph = extend_call_graph(call_graph, project_root)
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

logger = __import__("logging").getLogger(__name__)


# Language-specific patterns for function/call detection
LANGUAGE_PATTERNS = {
    "python": {
        "function_pattern": re.compile(r"^(?:def|async\s+def)\s+(\w+)\s*\("),
        "class_pattern": re.compile(r"^class\s+(\w+)"),
        "call_pattern": re.compile(r"(\w+)\s*\([^)]*\)\s*;"),
    },
    "c": {
        "function_pattern": re.compile(r"^(?:\w+\s+)+(\w+)\s*\([^)]*\)\s*\{"),
        "struct_pattern": re.compile(r"^typedef\s+struct\s+(\w+)"),
        "call_pattern": re.compile(r"(\w+)\s*\([^)]*\)\s*;"),
    },
    "javascript": {
        "function_pattern": re.compile(r"^(?:function\s+(\w+)|const\s+(\w+)\s*=\s*(?:async\s+)?\(|(\w+)\s*:\s*(?:async\s+)?\()"),
        "class_pattern": re.compile(r"^class\s+(\w+)"),
        "call_pattern": re.compile(r"(\w+)\s*\([^)]*\)\s*;"),
    },
    "rust": {
        "function_pattern": re.compile(r"^(?:pub\s+)?(?:async\s+)?fn\s+(\w+)"),
        "struct_pattern": re.compile(r"^struct\s+(\w+)"),
        "call_pattern": re.compile(r"(\w+)\s*\([^)]*\)"),
    },
    "go": {
        "function_pattern": re.compile(r"^func\s+(?:\([^)]+\)\s+)?(\w+)"),
        "struct_pattern": re.compile(r"^type\s+(\w+)\s+struct"),
        "call_pattern": re.compile(r"(\w+)\s*\([^)]*\)"),
    },
}


# Built-in functions that should be skipped
_BUILTINS: set[str] = {
    "print", "len", "str", "int", "float", "bool", "list", "dict", "set", "tuple",
    "range", "enumerate", "zip", "map", "filter", "sum", "min", "max", "abs",
    "open", "file", "input", "isinstance", "hasattr", "getattr", "setattr",
    "type", "repr", "dir", "vars", "globals", "locals", "callable", "sorted",
    "reversed", "any", "all", "super", "property", "staticmethod", "classmethod",
    # C builtins
    "printf", "scanf", "malloc", "free", "memcpy", "memset", "strlen", "strcpy",
    # JS builtins
    "console.log", "console.error", "JSON.parse", "JSON.stringify",
    "Array.isArray", "Object.keys", "Object.values",
}


def detect_language(file_path: Path) -> str:
    """Detect programming language from file extension.
    
    Args:
        file_path: Path to file
        
    Returns:
        Language string (python, c, javascript, rust, go)
    """
    suffix = file_path.suffix.lower()
    
    lang_map = {
        ".py": "python",
        ".c": "c",
        ".h": "c",
        ".cpp": "c",
        ".hpp": "c",
        ".cc": "c",
        ".cxx": "c",
        ".js": "javascript",
        ".jsx": "javascript",
        ".ts": "javascript",
        ".tsx": "javascript",
        ".mjs": "javascript",
        ".cjs": "javascript",
        ".rs": "rust",
        ".go": "go",
    }
    
    return lang_map.get(suffix, "unknown")


def parse_calls_non_python(
    content: str,
    file_path: str,
    language: str,
) -> list[dict[str, Any]]:
    """Parse function calls from non-Python files.
    
    Args:
        content: File content
        file_path: Path to file (for error messages)
        language: Programming language
        
    Returns:
        List of call dictionaries
    """
    if language not in LANGUAGE_PATTERNS:
        return []
    
    patterns = LANGUAGE_PATTERNS[language]
    call_pattern = patterns.get("call_pattern")
    if not call_pattern:
        return []
    
    calls = []
    lines = content.split("\n")
    
    for i, line in enumerate(lines, 1):
        # Skip comments
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("/*"):
            continue
        
        # Find function calls
        for match in call_pattern.finditer(line):
            callee = match.group(1)
            
            # Skip builtins and keywords
            if callee.startswith("_") or not callee[0].isalpha():
                continue
            if callee in _BUILTINS:
                continue
            
            calls.append({
                "caller": "<module>",
                "callee": callee,
                "file": file_path,
                "line": i,
                "col": match.start(),
            })
    
    return calls


def parse_functions_non_python(
    content: str,
    file_path: str,
    language: str,
) -> list[dict[str, Any]]:
    """Parse function definitions from non-Python files.
    
    Args:
        content: File content
        file_path: Path to file (for error messages)
        language: Programming language
        
    Returns:
        List of function definition dictionaries
    """
    if language not in LANGUAGE_PATTERNS:
        return []
    
    patterns = LANGUAGE_PATTERNS[language]
    func_pattern = patterns.get("function_pattern")
    if not func_pattern:
        return []
    
    functions = []
    lines = content.split("\n")
    
    for i, line in enumerate(lines, 1):
        # Skip comments
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("/*"):
            continue
        
        # Find function definitions
        for match in func_pattern.finditer(line):
            # Handle multiple capture groups
            func_name = None
            for group_idx in range(1, match.lastindex + 1):
                if match.group(group_idx):
                    func_name = match.group(group_idx)
                    break
            
            if func_name:
                functions.append({
                    "name": func_name,
                    "file": file_path,
                    "line": i,
                    "end_line": i,  # Would need more complex parsing for actual end
                    "is_method": False,
                })
    
    return functions


def extend_call_graph(call_graph, project_root: Path | str) -> Any:
    """Extend a CallGraph with cross-language support.
    
    This function adds methods to an existing CallGraph for handling
    multiple programming languages beyond Python.
    
    Args:
        call_graph: Existing CallGraph instance to extend
        project_root: Root directory of the project
        
    Returns:
        Extended CallGraph with cross-language support
    """
    project_root = Path(project_root) if isinstance(project_root, str) else project_root
    
    # Add cross-language parsing method
    def parse_calls_cross_language(self, file_path: Path) -> list[dict[str, Any]]:
        """Parse function calls from file (supports multiple languages).
        
        Args:
            file_path: Path to file
            
        Returns:
            List of call dictionaries
        """
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
            language = detect_language(file_path)
            
            if language == "python":
                # Use existing Python AST parsing
                return []
            else:
                return parse_calls_non_python(content, str(file_path), language)
        except Exception as e:
            logger.warning("Failed to parse calls from %s: %s", file_path, e)
            return []
    
    # Add cross-language function parsing
    def parse_functions_cross_language(self, file_path: Path) -> list[dict[str, Any]]:
        """Parse function definitions from file (supports multiple languages).
        
        Args:
            file_path: Path to file
            
        Returns:
            List of function definition dictionaries
        """
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
            language = detect_language(file_path)
            
            if language == "python":
                # Use existing Python AST parsing
                return []
            else:
                return parse_functions_non_python(content, str(file_path), language)
        except Exception as e:
            logger.warning("Failed to parse functions from %s: %s", file_path, e)
            return []
    
    # Add method to build from directory with cross-language support
    def build_from_directory_cross_language(self, root: Path | str | None = None) -> None:
        """Build call graph from a directory with cross-language support.
        
        Args:
            root: Root directory to scan (default: project_root)
        """
        root_path = Path(root) if root else self.project_root
        
        extensions = {".py", ".c", ".h", ".cpp", ".hpp", ".js", ".ts", ".jsx", ".tsx", ".rs", ".go"}
        skip_dirs = {".git", "__pycache__", "node_modules", ".venv", "venv", "build", "dist"}
        
        indexed_files: dict[str, list[dict[str, Any]]] = {}
        
        try:
            from src.infrastructure.indexing.tree_sitter import SafeTreeSitterIndexer
            indexer = SafeTreeSitterIndexer()
        except ImportError:
            indexer = None
        
        for ext in extensions:
            for file_path in root_path.rglob(f"*{ext}"):
                # Skip ignored directories
                if any(skip in file_path.parts for skip in skip_dirs):
                    continue
                
                try:
                    if indexer:
                        result = indexer.index_file(str(file_path))
                        if result.get("status") == "success":
                            indexed_files[str(file_path)] = result.get("symbols", [])
                    else:
                        # Use simple parsing without tree-sitter
                        indexed_files[str(file_path)] = (
                            parse_functions_cross_language(self, file_path) +
                            parse_calls_cross_language(self, file_path)
                        )
                except Exception as e:
                    logger.debug("Failed to index %s: %s", file_path, e)
        
        self.build(indexed_files)
    
    # Attach methods to call_graph
    call_graph.parse_calls_cross_language = parse_calls_cross_language.__get__(call_graph, type(call_graph))
    call_graph.parse_functions_cross_language = parse_functions_cross_language.__get__(call_graph, type(call_graph))
    call_graph.build_from_directory_cross_language = build_from_directory_cross_language.__get__(call_graph, type(call_graph))
    
    return call_graph


class CrossLanguageCallGraph:
    """Call graph with built-in cross-language support.
    
    This is a wrapper class that provides cross-language support
    for CallGraph without modifying the original class.
    
    Usage:
        graph = CrossLanguageCallGraph(project_root)
        graph.build_from_directory()
        
        # Access all call sites across languages
        for site in graph._call_sites:
            print(f"{site.file}:{site.line}: {site.caller} -> {site.callee}")
    """
    
    def __init__(self, project_root: Path | str | None = None):
        """Initialize cross-language call graph.
        
        Args:
            project_root: Root directory of the project
        """
        from src.core.cognition.call_graph import CallGraph
        
        self._graph = CallGraph(project_root)
        self._project_root = Path(project_root) if project_root else None
    
    def build_from_directory(self, root: Path | str | None = None) -> None:
        """Build call graph from directory.
        
        Args:
            root: Root directory to scan
        """
        self._graph.build_from_directory(root)
        
        # Extend with cross-language support
        if self._project_root:
            extend_call_graph(self._graph, self._project_root)
    
    @property
    def _call_sites(self):
        """Access call sites from underlying graph."""
        return self._graph._call_sites
    
    @property
    def _functions(self):
        """Access function definitions from underlying graph."""
        return self._graph._functions
    
    def get_callers(self, function_name: str, file_path: str | None = None):
        """Get all callers of a function."""
        return self._graph.get_callers(function_name, file_path)
    
    def get_callees(self, function_name: str, file_path: str | None = None):
        """Get all callees of a function."""
        return self._graph.get_callees(function_name, file_path)
    
    def find_references(self, symbol_name: str, file_path: str | None = None):
        """Find all references to a symbol."""
        return self._graph.find_references(symbol_name, file_path)
    
    def find_cycles(self):
        """Find circular dependencies."""
        return self._graph.find_cycles()
    
    def to_dict(self):
        """Serialize to dictionary."""
        return self._graph.to_dict()
    
    def get_stats(self):
        """Get statistics."""
        return self._graph.get_stats()
