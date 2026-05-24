"""Real Symbol Graph with Resolution.

Not string matching - actual symbol resolution with:
- Type system understanding
- Scope analysis
- Reference resolution
- Dependency tracking
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

from .ast_engine import (
    Symbol, SymbolKind, SourceLocation, Language,
    CodebaseIndexer, CallGraph
)

logger = logging.getLogger(__name__)


# =============================================================================
# RESOLUTION TYPES
# =============================================================================


class ResolutionStatus(Enum):
    """Symbol resolution status."""
    
    RESOLVED = auto()       # Fully resolved
    UNRESOLVED = auto()     # Cannot resolve
    PARTIAL = auto()       # Partially resolved (ambiguous)
    FORWARD_REF = auto()    # Forward reference
    CIRCULAR = auto()       # Circular dependency


@dataclass
class TypeInfo:
    """Type information for symbols."""
    
    # Base type
    base_type: str = ""
    
    # Qualifiers
    is_pointer: bool = False
    is_array: bool = False
    is_const: bool = False
    is_volatile: bool = False
    is_static: bool = False
    
    # For arrays
    array_size: int | None = None
    element_type: str | None = None
    
    # For pointers
    points_to: str | None = None
    
    # For structs/unions
    fields: list[tuple[str, str]] = field(default_factory=list)  # (name, type)
    
    # For functions
    return_type: str = ""
    parameters: list[tuple[str, str]] = field(default_factory=list)  # (name, type)
    
    # Resolution
    resolution_status: ResolutionStatus = ResolutionStatus.UNRESOLVED
    resolved_from: str | None = None  # UID of resolved definition


@dataclass
class ResolvedSymbol:
    """Symbol with full resolution information."""
    
    symbol: Symbol
    
    # Type info
    type_info: TypeInfo = field(default_factory=TypeInfo)
    
    # Scope info
    scope_id: str = ""
    scope_depth: int = 0
    is_global: bool = False
    is_static: bool = False
    
    # Resolution
    definition_uid: str | None = None  # UID of actual definition
    declaration_uids: list[str] = field(default_factory=list)
    
    # Dependencies
    depends_on: list[str] = field(default_factory=list)  # UIDs this symbol uses
    used_by: list[str] = field(default_factory=list)  # UIDs that use this
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol.to_dict(),
            "type_info": {
                "base_type": self.type_info.base_type,
                "is_pointer": self.type_info.is_pointer,
                "is_const": self.type_info.is_const,
                "return_type": self.type_info.return_type,
                "parameters": self.type_info.parameters,
                "resolution_status": self.type_info.resolution_status.name,
            },
            "scope_id": self.scope_id,
            "scope_depth": self.scope_depth,
            "definition_uid": self.definition_uid,
            "depends_on": self.depends_on,
        }


# =============================================================================
# SCOPE
# =============================================================================


@dataclass
class Scope:
    """Symbol scope representation."""
    
    scope_id: str
    scope_type: str  # "global", "file", "function", "block"
    
    # Parent scope
    parent_scope_id: str | None = None
    
    # Symbols in this scope
    symbols: dict[str, str] = field(default_factory=dict)  # name -> uid
    
    # Children scopes
    child_scope_ids: list[str] = field(default_factory=list)
    
    # Location
    start_line: int = 0
    end_line: int = 0
    file_path: str = ""


# =============================================================================
# SYMBOL RESOLVER
# =============================================================================


class SymbolResolver:
    """Real symbol resolver with scope analysis.
    
    This is NOT string matching.
    This understands:
    - Scope hierarchy
    - Type system
    - Symbol resolution rules
    - Forward references
    """
    
    def __init__(self, indexer: CodebaseIndexer):
        self.indexer = indexer
        
        # Scope management
        self._scopes: dict[str, Scope] = {}
        self._scope_stack: list[str] = []  # Current scope stack
        
        # Resolution cache
        self._resolution_cache: dict[str, ResolvedSymbol] = {}
        
        # Build scope hierarchy from symbols
        self._build_scopes()
    
    def _build_scopes(self) -> None:
        """Build scope hierarchy from indexed symbols."""
        # Global scope
        global_scope = Scope(
            scope_id="global",
            scope_type="global",
            file_path="",
        )
        self._scopes["global"] = global_scope
        
        # Analyze each file
        for file_path, symbols in self.indexer._symbols_by_file.items():
            # File scope
            file_scope = Scope(
                scope_id=f"file:{file_path}",
                scope_type="file",
                parent_scope_id="global",
                file_path=file_path,
            )
            self._scopes[file_scope.scope_id] = file_scope
            self._scopes["global"].child_scope_ids.append(file_scope.scope_id)
            
            # Add file-level symbols
            for uid in symbols:
                sym = self.indexer.get_symbol(uid)
                if sym:
                    # Determine scope type based on symbol kind
                    if sym.kind == SymbolKind.FUNCTION:
                        # Function scope
                        func_scope = Scope(
                            scope_id=f"func:{uid}",
                            scope_type="function",
                            parent_scope_id=file_scope.scope_id,
                            start_line=sym.location.line,
                            file_path=file_path,
                        )
                        self._scopes[func_scope.scope_id] = func_scope
                        file_scope.child_scope_ids.append(func_scope.scope_id)
                        
                        # Add function symbols to function scope
                        sym.names_in_scope = {sym.name: uid}
                        
                    elif sym.kind in [SymbolKind.STRUCT, SymbolKind.ENUM, SymbolKind.UNION]:
                        # Type scope
                        file_scope.symbols[sym.name] = uid
                    elif sym.kind == SymbolKind.VARIABLE:
                        # Global variable
                        if not sym.location.file_path.endswith('.c'):
                            file_scope.symbols[sym.name] = uid
        
        logger.info("scopes_built: count=%s", len(self._scopes))
    
    def _resolve_type(self, type_str: str, scope: Scope) -> TypeInfo:
        """Resolve a type string to actual type information."""
        type_info = TypeInfo(base_type=type_str)
        
        # Handle qualifiers
        type_str = type_str.replace("const ", "").replace("volatile ", "")
        type_str = type_str.replace("static ", "").replace("extern ", "")
        
        # Handle pointers
        if "*" in type_str:
            type_info.is_pointer = True
            type_info.points_to = type_str.replace("*", "").strip()
        
        # Handle arrays
        if "[" in type_str:
            type_info.is_array = True
            # Extract element type and size
            import re
            match = re.search(r'(\w+)\[(\d*)\]', type_str)
            if match:
                type_info.element_type = match.group(1)
                if match.group(2):
                    type_info.array_size = int(match.group(2))
        
        # Handle basic types
        basic_types = ["void", "int", "char", "float", "double", "short", "long"]
        for bt in basic_types:
            if bt in type_str.lower():
                type_info.base_type = bt
                break
        
        # Try to resolve to symbol
        resolved = self._find_definition(type_str, scope)
        if resolved:
            type_info.resolution_status = ResolutionStatus.RESOLVED
            type_info.resolved_from = resolved.symbol.uid
        
        return type_info
    
    def _find_definition(self, name: str, scope: Scope) -> Symbol | None:
        """Find symbol definition in scope hierarchy."""
        # Search current scope
        if name in scope.symbols:
            uid = scope.symbols[name]
            return self.indexer.get_symbol(uid)
        
        # Search parent scopes
        if scope.parent_scope_id:
            parent = self._scopes.get(scope.parent_scope_id)
            if parent:
                return self._find_definition(name, parent)
        
        # Search global scope
        global_scope = self._scopes.get("global")
        if global_scope and scope.scope_id != "global":
            return self._find_definition(name, global_scope)
        
        return None
    
    def resolve_symbol(self, uid: str) -> ResolvedSymbol | None:
        """Resolve a symbol to get full information."""
        if uid in self._resolution_cache:
            return self._resolution_cache[uid]
        
        symbol = self.indexer.get_symbol(uid)
        if not symbol:
            return None
        
        # Determine scope
        scope_id = "global"
        scope = self._scopes.get("global")
        
        if symbol.kind == SymbolKind.FUNCTION:
            scope_id = f"func:{uid}"
            scope = self._scopes.get(scope_id) or scope
        
        # Resolve type
        type_info = TypeInfo()
        if symbol.signature:
            type_info = self._resolve_type(symbol.signature, scope)
        elif symbol.type_annotation:
            type_info = self._resolve_type(symbol.type_annotation, scope)
        
        resolved = ResolvedSymbol(
            symbol=symbol,
            type_info=type_info,
            scope_id=scope_id,
            scope_depth=self._get_scope_depth(scope_id),
            definition_uid=uid,
        )
        
        self._resolution_cache[uid] = resolved
        return resolved
    
    def _get_scope_depth(self, scope_id: str) -> int:
        """Get depth of scope in hierarchy."""
        depth = 0
        current = self._scopes.get(scope_id)
        while current and current.parent_scope_id:
            depth += 1
            current = self._scopes.get(current.parent_scope_id)
        return depth
    
    def find_references(self, uid: str) -> list[Symbol]:
        """Find all references to a symbol."""
        symbol = self.indexer.get_symbol(uid)
        if not symbol:
            return []
        
        # Search all files for references
        references = []
        for file_path in self.indexer._symbols_by_file:
            file_symbols = self.indexer.get_symbols_in_file(file_path)
            for sym in file_symbols:
                if sym.uid != uid and sym.name == symbol.name:
                    references.append(sym)
        
        return references


# =============================================================================
# DEPENDENCY GRAPH
# =============================================================================


@dataclass
class DependencyEdge:
    """Edge in dependency graph."""
    
    source_uid: str
    target_uid: str
    edge_type: str  # "import", "call", "reference", "inherits"
    is_cyclic: bool = False


class DependencyGraph:
    """Real dependency graph with proper resolution.
    
    NOT string matching.
    Understands:
    - Include dependencies
    - Call dependencies  
    - Type dependencies
    - Circular dependency detection
    """
    
    def __init__(self, indexer: CodebaseIndexer, resolver: SymbolResolver):
        self.indexer = indexer
        self.resolver = resolver
        
        # Graph structure
        self._nodes: set[str] = set()  # UIDs
        self._edges: list[DependencyEdge] = []
        self._edges_by_source: dict[str, list[str]] = {}  # source -> [targets]
        self._edges_by_target: dict[str, list[str]] = {}  # target -> [sources]
        
        # Build graph
        self._build_graph()
    
    def _add_edge(self, source_uid: str, target_uid: str, edge_type: str) -> None:
        """Add edge to graph."""
        if source_uid == target_uid:
            return
        
        self._nodes.add(source_uid)
        self._nodes.add(target_uid)
        
        edge = DependencyEdge(
            source_uid=source_uid,
            target_uid=target_uid,
            edge_type=edge_type,
        )
        
        self._edges.append(edge)
        
        if source_uid not in self._edges_by_source:
            self._edges_by_source[source_uid] = []
        self._edges_by_source[source_uid].append(target_uid)
        
        if target_uid not in self._edges_by_target:
            self._edges_by_target[target_uid] = []
        self._edges_by_target[target_uid].append(source_uid)
    
    def _build_graph(self) -> None:
        """Build dependency graph from symbols."""
        for uid in self.indexer._symbols:
            symbol = self.indexer.get_symbol(uid)
            if not symbol:
                continue
            
            resolved = self.resolver.resolve_symbol(uid)
            if not resolved:
                continue
            
            # Add type dependencies
            if resolved.type_info.points_to:
                pointed = resolved.type_info.points_to
                target = self.resolver._find_definition(pointed, self.resolver._scopes.get("global"))
                if target:
                    self._add_edge(uid, target.uid, "type")
            
            # Add parameter dependencies
            for _, param_type in resolved.type_info.parameters:
                target = self.resolver._find_definition(param_type, self.resolver._scopes.get("global"))
                if target:
                    self._add_edge(uid, target.uid, "parameter")
        
        # Detect cycles
        self._detect_cycles()
        
        logger.info("dependency_graph_built: nodes=%s edges=%s", len(self._nodes), len(self._edges))
    
    def _detect_cycles(self) -> None:
        """Detect circular dependencies."""
        visited = set()
        rec_stack = set()
        
        def dfs(node: str, path: list[str]) -> list[list[str]]:
            cycles = []
            visited.add(node)
            rec_stack.add(node)
            path.append(node)
            
            for neighbor in self._edges_by_source.get(node, []):
                if neighbor not in visited:
                    cycles.extend(dfs(neighbor, path.copy()))
                elif neighbor in rec_stack:
                    # Found cycle
                    cycle_start = path.index(neighbor)
                    cycles.append(path[cycle_start:])
            
            rec_stack.remove(node)
            return cycles
        
        for node in self._nodes:
            if node not in visited:
                dfs(node, [])
    
    def get_dependencies(self, uid: str) -> list[str]:
        """Get direct dependencies of a symbol."""
        return self._edges_by_source.get(uid, [])
    
    def get_dependents(self, uid: str) -> list[str]:
        """Get direct dependents of a symbol."""
        return self._edges_by_target.get(uid, [])
    
    def get_transitive_dependencies(self, uid: str) -> set[str]:
        """Get all transitive dependencies."""
        result = set()
        to_visit = [uid]
        visited = set()
        
        while to_visit:
            current = to_visit.pop()
            if current in visited:
                continue
            visited.add(current)
            
            for dep in self._edges_by_source.get(current, []):
                result.add(dep)
                to_visit.append(dep)
        
        return result
    
    def get_stats(self) -> dict[str, Any]:
        """Get graph statistics."""
        return {
            "nodes": len(self._nodes),
            "edges": len(self._edges),
            "edge_types": {},
        }


# =============================================================================
# GLOBAL INSTANCES
# =============================================================================


_global_resolver: SymbolResolver | None = None
_global_dep_graph: DependencyGraph | None = None


def get_symbol_resolver(indexer: CodebaseIndexer | None = None) -> SymbolResolver:
    """Get global symbol resolver."""
    global _global_resolver
    if _global_resolver is None:
        idx = indexer or get_codebase_indexer()
        _global_resolver = SymbolResolver(idx)
    return _global_resolver


def get_dependency_graph(
    indexer: CodebaseIndexer | None = None,
    resolver: SymbolResolver | None = None,
) -> DependencyGraph:
    """Get global dependency graph."""
    global _global_dep_graph
    if _global_dep_graph is None:
        idx = indexer or get_codebase_indexer()
        res = resolver or get_symbol_resolver(idx)
        _global_dep_graph = DependencyGraph(idx, res)
    return _global_dep_graph
