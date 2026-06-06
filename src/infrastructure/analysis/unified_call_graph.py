"""Unified call graph interface combining both implementations.

This module provides a single entry point for call graph operations,
delegating to the appropriate implementation based on the use case:

- `src.core.cognition.call_graph.CallGraph` — Cross-file AST-based graph
  with incremental indexing, argument tracking, and file watcher support.
- `src.infrastructure.analysis.call_graph_builder.CallGraphBuilder` — Semantic
  graph with alias resolution, class hierarchy, and dynamic dispatch.

The UnifiedCallGraph wraps both and provides a consistent API.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, List

logger = logging.getLogger(__name__)


@dataclass
class UnifiedCallSite:
    """Normalized call site from either implementation."""

    caller: str
    callee: str
    file: str
    line: int
    col: int = 0
    is_method: bool = False
    arguments: list[str] = field(default_factory=list)
    receiver_type: Optional[str] = None


@dataclass
class UnifiedFunctionDef:
    """Normalized function definition."""

    name: str
    file: str
    line: int
    end_line: int
    params: list[str] = field(default_factory=list)
    is_method: bool = False
    class_name: Optional[str] = None
    is_async: bool = False


@dataclass
class UnifiedCallGraphStats:
    """Statistics for the unified call graph."""

    functions: int = 0
    call_sites: int = 0
    files: int = 0
    cycles: int = 0
    source: str = ""  # Which implementation was used


class UnifiedCallGraph:
    """Unified interface over both call graph implementations.

    Provides a single API for:
    - Building call graphs (from files, directories, or content)
    - Querying callers/callees (with reverse index)
    - Incremental updates
    - Cycle detection
    - Alias resolution

    Usage:
        graph = UnifiedCallGraph(project_root=".")
        graph.build_from_directory()
        callers = graph.get_callers("my_function")
        graph.build_incremental(Path("changed_file.py"), content)
    """

    def __init__(self, project_root: str | Path | None = None):
        """Initialize the unified call graph.

        Args:
            project_root: Root directory of the project
        """
        self._project_root = Path(project_root) if project_root else Path.cwd()
        self._core_graph = None  # Lazy-initialized
        self._semantic_graph = None  # Lazy-initialized
        self._is_built = False

    @property
    def core_graph(self):
        """Get or create the core call graph (incremental, AST-based)."""
        if self._core_graph is None:
            from src.core.cognition.call_graph import CallGraph
            self._core_graph = CallGraph(self._project_root)
        return self._core_graph

    @property
    def semantic_graph(self):
        """Get or create the semantic call graph (alias-aware, class hierarchy)."""
        if self._semantic_graph is None:
            from src.infrastructure.analysis.call_graph_builder import CallGraphBuilder
            from src.infrastructure.analysis.semantic_resolver import SemanticResolver
            from src.infrastructure.analysis.alias_resolver import AliasResolver
            resolver = SemanticResolver()
            alias_resolver = AliasResolver()
            self._semantic_graph = CallGraphBuilder(resolver, alias_resolver)
        return self._semantic_graph

    def build_from_directory(self, root: str | Path | None = None) -> UnifiedCallGraphStats:
        """Build call graph from a directory using the core implementation.

        Args:
            root: Root directory to scan (default: project_root)

        Returns:
            Build statistics
        """
        self.core_graph.build_from_directory(root or self._project_root)
        self._is_built = True
        stats = self.core_graph.get_stats()
        return UnifiedCallGraphStats(
            functions=stats.get("functions", 0),
            call_sites=stats.get("call_sites", 0),
            files=stats.get("files", 0),
            source="core_cognition",
        )

    def build_from_content(self, content: str, file_path: str | Path) -> None:
        """Build/update call graph for a single file from content.

        Args:
            content: File content
            file_path: Path to associate with the content
        """
        self.core_graph.build_content(content, file_path)
        self._is_built = True

    def build_incremental(self, file_path: str | Path, content: str) -> bool:
        """Incrementally update call graph for a changed file.

        Only re-indexes if file has been modified since last build.

        Args:
            file_path: Path to the file
            content: Current file content

        Returns:
            True if file was re-indexed, False if skipped
        """
        return self.core_graph.build_incremental(Path(file_path), content)

    def build_semantic(
        self,
        files: list[Path],
        contents: dict[Path, str],
    ) -> UnifiedCallGraphStats:
        """Build semantic call graph with alias resolution and class hierarchy.

        Use this when you need accurate alias resolution and method dispatch.

        Args:
            files: List of file paths
            contents: Dict mapping paths to content

        Returns:
            Build statistics
        """
        graph = self.semantic_graph.build(files, contents)
        self._is_built = True
        return UnifiedCallGraphStats(
            functions=len(graph.classes) + len(graph.methods),
            call_sites=len(graph.edges),
            files=len(files),
            source="semantic_builder",
        )

    # ─── Query API ───────────────────────────────────────────────────────────

    def get_callers(
        self, function_name: str, file_path: Optional[str] = None
    ) -> list[UnifiedCallSite]:
        """Get all callers of a function (reverse index lookup).

        Args:
            function_name: Name of the function
            file_path: Optional file filter

        Returns:
            List of call sites that call this function
        """
        if not self._is_built:
            return []

        raw_callers = self.core_graph.get_callers(function_name, file_path)
        return [
            UnifiedCallSite(
                caller=c.caller,
                callee=c.callee,
                file=c.file,
                line=c.line,
                col=c.col,
                is_method=c.is_method,
                arguments=c.arguments,
            )
            for c in raw_callers
        ]

    def get_callees(
        self, function_name: str, file_path: Optional[str] = None
    ) -> list[UnifiedCallSite]:
        """Get all functions called by a given function.

        Args:
            function_name: Name of the calling function
            file_path: Optional file filter

        Returns:
            List of call sites within this function
        """
        if not self._is_built:
            return []

        raw_callees = self.core_graph.get_callees(function_name, file_path)
        return [
            UnifiedCallSite(
                caller=c.caller,
                callee=c.callee,
                file=c.file,
                line=c.line,
                col=c.col,
                is_method=c.is_method,
                arguments=c.arguments,
            )
            for c in raw_callees
        ]

    def find_references(
        self, symbol_name: str, file_path: Optional[str] = None
    ) -> list[UnifiedCallSite]:
        """Find all references to a symbol.

        Args:
            symbol_name: Name of the symbol
            file_path: Optional file filter

        Returns:
            List of call sites referencing this symbol
        """
        if not self._is_built:
            return []

        refs = self.core_graph.find_references(symbol_name, file_path)
        return [
            UnifiedCallSite(
                caller=r.caller,
                callee=r.callee,
                file=r.file,
                line=r.line,
                col=r.col,
                is_method=r.is_method,
                arguments=r.arguments,
            )
            for r in refs
        ]

    def find_cycles(self) -> list[list[str]]:
        """Find circular dependencies in the call graph.

        Returns:
            List of cycles, each cycle is a list of function names
        """
        if not self._is_built:
            return []
        return self.core_graph.find_cycles()

    def get_function(self, name: str) -> Optional[UnifiedFunctionDef]:
        """Get function definition by name.

        Args:
            name: Function name

        Returns:
            UnifiedFunctionDef or None
        """
        defs = self.core_graph.get_function(name)
        if not defs:
            return None
        d = defs[0]
        return UnifiedFunctionDef(
            name=d.name,
            file=d.file,
            line=d.line,
            end_line=d.end_line,
            params=d.params,
            is_method=d.is_method,
            class_name=d.class_name,
            is_async=d.is_async,
        )

    def clear_file(self, file_path: str | Path) -> None:
        """Remove all data for a specific file.

        Args:
            file_path: Path to clear
        """
        self.core_graph.clear_file(file_path)

    def get_stats(self) -> UnifiedCallGraphStats:
        """Get current statistics."""
        if not self._is_built:
            return UnifiedCallGraphStats()
        raw = self.core_graph.get_stats()
        return UnifiedCallGraphStats(
            functions=raw.get("functions", 0),
            call_sites=raw.get("call_sites", 0),
            files=raw.get("files", 0),
            source="unified",
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize the call graph to a dictionary."""
        if not self._is_built:
            return {"stats": {}, "functions": {}, "call_sites": []}
        return self.core_graph.to_dict()
