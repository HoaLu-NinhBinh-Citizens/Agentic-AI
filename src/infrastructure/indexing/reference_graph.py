"""Reference graph — tracks symbol definition → all references.

Builds a complete reference map using tree-sitter:
- For each function/class/struct definition, find ALL usages across the codebase
- Uses tree-sitter query to find identifier nodes matching symbol name
- Groups by symbol name + file + line number
- Supports incremental updates (only re-index changed files)
- Integrates with SafeTreeSitterIndexer for language-aware parsing

Architecture:
    1. index_file() / index_directory() → parse with tree-sitter
    2. _extract_definitions() → find symbol definitions
    3. _find_all_references() → query for all identifier usages
    4. _build_call_graph() → map callers ↔ callees
    5. find_references() / find_callers() / find_callees() → query the graph
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from src.infrastructure.analysis.type_resolver import TypeResolver, TypeInfo
from src.infrastructure.analysis.import_tracker import ImportTracker
from src.infrastructure.analysis.semantic_resolver import SemanticResolver, ResolvedSymbol
from src.infrastructure.analysis.call_graph_builder import CallGraphBuilder, CallGraph

if TYPE_CHECKING:
    from src.infrastructure.indexing.tree_sitter import SafeTreeSitterIndexer

logger = logging.getLogger(__name__)


# ─── Data structures ──────────────────────────────────────────────────────────

@dataclass
class RefLocation:
    """Location of a symbol reference."""
    file_path: str
    line: int
    column: int
    context: str  # Surrounding line text for display
    node_type: str  # e.g., "identifier", "call", "type_identifier"
    is_call: bool = False  # True if this is a function call site

    def __hash__(self) -> int:
        return hash((self.file_path, self.line, self.column))


@dataclass
class DefLocation:
    """Location of a symbol definition."""
    file_path: str
    line: int
    column: int
    end_line: int
    symbol_type: str  # "function", "class", "struct", "enum", etc.
    node_type: str  # e.g., "function_definition", "class_definition"
    signature: str = ""  # Full signature text
    context: str = ""  # Surrounding line text


@dataclass
class SymbolInfo:
    """Complete symbol information: definition + references + call graph."""
    name: str
    definition: DefLocation | None
    references: list[RefLocation] = field(default_factory=list)
    callers: list[RefLocation] = field(default_factory=list)
    callees: list[RefLocation] = field(default_factory=list)
    file_count: int = 0
    total_references: int = 0


@dataclass
class SymbolLocation:
    """Resolved symbol location with type information."""
    name: str
    file_path: Path
    line: int
    kind: str  # "function", "class", "variable", "module"
    resolved_from: Optional[str] = None  # Original import path if aliased


@dataclass
class ReferenceGraphStats:
    """Statistics about the reference graph."""
    files_indexed: int = 0
    symbols_indexed: int = 0
    total_definitions: int = 0
    total_references: int = 0
    total_calls: int = 0
    circular_deps: list[list[str]] = field(default_factory=list)


# ─── Language-specific query builders ────────────────────────────────────────

# Query patterns per language for finding references
# Maps symbol type → list of tree-sitter query patterns
_IDENTIFIER_QUERIES: dict[str, list[str]] = {
    # C / C++
    "c": [
        '(identifier) @ref',
        '(call_expression (identifier) @ref)',
        '(declaration (identifier) @ref)',
        '(parameter_declaration (identifier) @ref)',
        '(field_identifier) @ref',
    ],
    "cpp": [
        '(identifier) @ref',
        '(call_expression (identifier) @ref)',
        '(declaration (identifier) @ref)',
        '(field_identifier) @ref',
    ],
    # Python
    "python": [
        '(identifier) @ref',
        '(call (identifier) @ref)',
        '(attribute (identifier) @ref)',
        '(parameter (identifier) @ref)',
        '(list_splat_pattern (identifier) @ref)',
        '(dictionary_splat_pattern (identifier) @ref)',
    ],
    # JavaScript / TypeScript
    "javascript": [
        '(identifier) @ref',
        '(call_expression (identifier) @ref)',
        '(member_expression (property (identifier) @ref))',
    ],
    "typescript": [
        '(identifier) @ref',
        '(call_expression (identifier) @ref)',
        '(type_identifier) @ref',
        '(member_expression (property (identifier) @ref))',
    ],
    # Rust
    "rust": [
        '(identifier) @ref',
        '(call_expression (identifier) @ref)',
        '(field_identifier) @ref',
        '(type_identifier) @ref',
        '(scoped_type_identifier (type_identifier) @ref)',
    ],
    # Go
    "go": [
        '(identifier) @ref',
        '(call_expression (identifier) @ref)',
        '(field_identifier) @ref',
        '(type_identifier) @ref',
    ],
    # Java
    "java": [
        '(identifier) @ref',
        '(method_invocation (identifier) @ref)',
        '(field_access (identifier) @ref)',
        '(type_identifier) @ref',
    ],
}

# Node types that indicate a function/method call
_CALL_NODE_TYPES: set[str] = {
    "call", "call_expression", "method_invocation",
    "function_call", "identifier",
}

# Node types to skip when finding references (avoid matching the definition itself)
_SKIP_CONTEXT_TYPES: set[str] = {
    "function_definition", "function_declaration", "function_item",
    "class_definition", "class_declaration", "class_specifier",
    "struct_specifier", "struct_item", "enum_item", "enum_specifier",
    "type_alias", "type_alias_declaration", "type_declaration",
    "parameter", "parameter_declaration", "list_splat_pattern",
    "dictionary_splat_pattern", "typed_parameter",
}

# Extensions that map to languages
_EXTENSION_LANGUAGE_MAP: dict[str, str] = {
    ".py": "python",
    ".c": "c", ".h": "c",
    ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp",
    ".hpp": "cpp",
    ".js": "javascript", ".jsx": "javascript",
    ".ts": "typescript", ".tsx": "typescript",
    ".rs": "rust",
    ".go": "go",
    ".java": "java",
}


def _detect_language(path: str) -> str:
    """Detect language from file extension."""
    ext = Path(path).suffix.lower()
    return _EXTENSION_LANGUAGE_MAP.get(ext, "text")


def _is_call_node(node_type: str, parent_type: str) -> bool:
    """Determine if an identifier is a function call site."""
    call_parent_types = {
        "call", "call_expression", "method_invocation",
        "await_expression", "yield_expression",
    }
    return parent_type in call_parent_types or node_type in _CALL_NODE_TYPES


# ─── Main reference graph ─────────────────────────────────────────────────────

class ReferenceGraph:
    """Tracks symbol references across the codebase.

    Builds a complete reference map by:
    1. Parsing each file with tree-sitter via SafeTreeSitterIndexer
    2. Extracting symbol definitions (functions, classes, etc.)
    3. Finding all identifier usages matching each symbol name
    4. Building call graphs (callers ↔ callees)

    Usage:
        indexer = SafeTreeSitterIndexer()
        ref_graph = ReferenceGraph(indexer)

        await ref_graph.index_directory("src/")
        refs = ref_graph.find_references("process_data")
        callers = ref_graph.find_callers("handle_request")
        info = ref_graph.get_symbol_info("MyClass")
    """

    def __init__(
        self,
        indexer: Optional["SafeTreeSitterIndexer"] = None,
        max_file_size_bytes: int = 10 * 1024 * 1024,
    ) -> None:
        self._indexer = indexer
        self._max_file_size = max_file_size_bytes
        self._type_resolver = TypeResolver()
        self._import_tracker: Optional[ImportTracker] = None

        # Semantic resolution
        self._semantic_resolver = SemanticResolver()
        self._call_graph_builder = CallGraphBuilder(self._semantic_resolver)
        self._call_graph: Optional[CallGraph] = None
        self._contents_cache: dict[Path, str] = {}

        # symbol_name → list of RefLocation (all references)
        self._refs: dict[str, list[RefLocation]] = {}

        # symbol_name → DefLocation (primary definition)
        self._defs: dict[str, DefLocation] = {}

        # file_path → set of symbol names defined in that file
        self._file_symbols: dict[str, set[str]] = {}

        # function_name → list of RefLocation (incoming call sites)
        self._callers: dict[str, list[RefLocation]] = {}

        # function_name → list of RefLocation (outgoing calls)
        self._callees: dict[str, list[RefLocation]] = {}

        # IMPROVED: Track import aliases per file for better cross-file resolution
        # file_path → {alias_name: (original_name, source_module)}
        self._import_aliases: dict[str, dict[str, tuple[str, str]]] = {}

        self._stats = ReferenceGraphStats()
        self._lock = asyncio.Lock()

    @property
    def stats(self) -> ReferenceGraphStats:
        return self._stats

    # ─── Indexing ─────────────────────────────────────────────────────────────

    def _track_import_aliases(self, file_path: str, content: str) -> None:
        """Track import aliases in a file for better cross-file resolution.

        Handles:
        - import X as Y
        - from X import Y as Z
        - from X import Y
        """
        aliases: dict[str, tuple[str, str]] = {}

        for match in re.finditer(r"^import\s+(\S+)(?:\s+as\s+(\w+))?", content, re.MULTILINE):
            module = match.group(1)
            alias = match.group(2) or module.split(".")[-1]
            aliases[alias] = (module, module)

        for match in re.finditer(
            r"^from\s+(\S+)\s+import\s+(.+?)$",
            content,
            re.MULTILINE
        ):
            module = match.group(1)
            names_str = match.group(2)
            for name_match in re.finditer(r"(\w+)(?:\s+as\s+(\w+))?", names_str):
                original = name_match.group(1)
                alias = name_match.group(2) or original
                aliases[alias] = (original, module)

        self._import_aliases[file_path] = aliases

    def _resolve_alias(
        self,
        name: str,
        file_path: str,
    ) -> tuple[str, str] | None:
        """Resolve an alias to its original name and module.

        Returns:
            Tuple of (original_name, module) if found, None otherwise.
        """
        aliases = self._import_aliases.get(file_path, {})
        return aliases.get(name)

    def _resolve_symbol_with_alias_tracking(
        self,
        name: str,
        file_path: str,
        content: str,
        line: int,
    ) -> Optional[SymbolLocation]:
        """Resolve a symbol considering import aliases.

        This improves cross-file resolution by tracking:
        - import os → alias: os
        - import pandas as pd → alias: pd → maps to pandas
        - from collections import OrderedDict as OD → alias: OD
        """
        # First check import aliases
        alias_info = self._resolve_alias(name, file_path)
        if alias_info:
            original, module = alias_info
            # Try to find the original symbol in project
            defn = self._defs.get(original)
            if defn:
                return SymbolLocation(
                    name=name,
                    file_path=Path(defn.file_path),
                    line=defn.line,
                    kind=defn.symbol_type,
                    resolved_from=f"{module}.{original}",
                )

        # Fall back to type resolution
        type_info = self._type_resolver.resolve_name(name, content, line)
        if type_info and type_info.module:
            if self._import_tracker:
                symbol_export = self._import_tracker.resolve_import(
                    Path(file_path), name, type_info.module
                )
                if symbol_export:
                    return SymbolLocation(
                        name=name,
                        file_path=symbol_export.file_path,
                        line=symbol_export.line,
                        kind=symbol_export.kind,
                        resolved_from=type_info.full_name,
                    )

        # Fall back to normal lookup
        return self._find_symbol_in_project(name)

    async def index_file(self, path: str) -> dict[str, Any]:
        """Index a single file for symbol definitions and references.

        Returns:
            Dict with indexed symbols count and reference count.
        """
        async with self._lock:
            return await self._index_file_impl(path)

    async def _index_file_impl(self, path: str) -> dict[str, Any]:
        """Internal file indexing (must hold lock)."""
        if not os.path.isfile(path):
            return {"path": path, "status": "not_found"}

        try:
            stat = os.stat(path)
            if stat.st_size > self._max_file_size:
                return {"path": path, "status": "skipped", "reason": "file_too_large"}
        except OSError as e:
            return {"path": path, "status": "error", "error": str(e)}

        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except OSError as e:
            return {"path": path, "status": "error", "error": str(e)}

        lines = content.split("\n")
        language = _detect_language(path)

        # Track import aliases for better cross-file resolution
        self._track_import_aliases(path, content)

        # Use indexer if available, otherwise parse manually
        if self._indexer is not None:
            result = await self._index_with_indexer(path, content, language)
        else:
            result = self._index_standalone(path, content, language, lines)

        self._stats.files_indexed += 1
        return result

    async def _index_with_indexer(
        self,
        path: str,
        content: str,
        language: str,
    ) -> dict[str, Any]:
        """Use SafeTreeSitterIndexer to extract symbols, then find references."""
        symbols_count = 0
        refs_count = 0

        # Get symbols from the indexer
        try:
            result = await self._indexer.index_file(path, content)
            symbols = result.get("symbols", [])
        except Exception as e:
            logger.debug("indexer_failed", path=path, error=str(e))
            symbols = []

        if not symbols:
            return {"path": path, "status": "ok", "symbols": 0, "references": 0}

        file_symbols: set[str] = set()

        for sym in symbols:
            name = sym.get("name", "")
            if not name:
                continue

            sym_type = sym.get("type", "symbol")
            line = sym.get("line", 1)
            end_line = sym.get("end_line", line)
            node_type = sym.get("node_type", "")

            # Record definition
            def_loc = DefLocation(
                file_path=path,
                line=line,
                column=0,
                end_line=end_line,
                symbol_type=sym_type,
                node_type=node_type,
                signature=sym.get("signature", ""),
                context=sym.get("context", ""),
            )
            self._defs[name] = def_loc
            file_symbols.add(name)

            # Find all references to this symbol
            refs = self._find_references_in_content(
                name, path, content, language, line, end_line
            )
            self._refs.setdefault(name, []).extend(refs)
            refs_count += len(refs)

            # If it's a function, build call graph
            if sym_type == "function":
                self._callers.setdefault(name, [])
                self._callees.setdefault(name, [])
                for ref in refs:
                    if ref.is_call:
                        self._callers[name].append(ref)

            symbols_count += 1

        self._file_symbols[path] = file_symbols
        self._stats.symbols_indexed += symbols_count
        self._stats.total_references += refs_count

        return {
            "path": path,
            "status": "ok",
            "symbols": symbols_count,
            "references": refs_count,
        }

    def _index_standalone(
        self,
        path: str,
        content: str,
        language: str,
        lines: list[str],
    ) -> dict[str, Any]:
        """Standalone indexing without SafeTreeSitterIndexer."""
        symbols = self._extract_symbols_standalone(content, language, lines)
        file_symbols: set[str] = set()

        for sym in symbols:
            name = sym["name"]
            if not name:
                continue

            def_loc = DefLocation(
                file_path=path,
                line=sym["line"],
                column=0,
                end_line=sym.get("end_line", sym["line"]),
                symbol_type=sym["type"],
                node_type=sym.get("node_type", "regex"),
            )
            self._defs[name] = def_loc
            file_symbols.add(name)

            refs = self._find_references_in_content(
                name, path, content, language, sym["line"], sym.get("end_line", sym["line"])
            )
            self._refs.setdefault(name, []).extend(refs)

        self._file_symbols[path] = file_symbols
        return {
            "path": path,
            "status": "ok",
            "symbols": len(symbols),
            "references": sum(len(self._refs.get(s["name"], [])) for s in symbols),
        }

    def _extract_symbols_standalone(
        self,
        content: str,
        language: str,
        lines: list[str],
    ) -> list[dict[str, Any]]:
        """Regex-based symbol extraction as fallback."""
        symbols: list[dict[str, Any]] = []
        patterns: list[tuple[str, str, Any]] = [
            # Python
            ("function", "python",
             re.compile(r"^\s*(?:async\s+)?def\s+([a-zA-Z_][\w]*)\s*\(", re.MULTILINE)),
            ("class", "python",
             re.compile(r"^\s*class\s+([A-Za-z_][\w]*)\s*(?:\([^)]*\))?:", re.MULTILINE)),
            # C
            ("function", "c",
             re.compile(r"^\s*(?:static\s+|inline\s+)?(?:void|int|char|float|double|bool|long|short|unsigned)\s+([a-z_][a-z0-9_]*)\s*\([^;{]*", re.MULTILINE)),
            ("struct", "c",
             re.compile(r"^\s*struct\s+([A-Za-z_][\w]*)\s*\{", re.MULTILINE)),
            # Rust
            ("function", "rust",
             re.compile(r"^\s*(?:pub\s+)?(?:async\s+)?fn\s+([a-z_][\w]*)\s*[<(]", re.MULTILINE)),
            ("struct", "rust",
             re.compile(r"^\s*struct\s+([A-Za-z_][\w]*)\s*(?:<[^>]*>)?\s*[{:]", re.MULTILINE)),
            # TypeScript
            ("function", "typescript",
             re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+([a-zA-Z_$][\w$]*)\s*\(", re.MULTILINE)),
            ("class", "typescript",
             re.compile(r"^\s*(?:export\s+)?class\s+([A-Za-z_$][\w$]*)\s*(?:extends|implements)?", re.MULTILINE)),
            # JavaScript
            ("function", "javascript",
             re.compile(r"^\s*(?:async\s+)?function\s+([a-zA-Z_$][\w$]*)\s*\(", re.MULTILINE)),
        ]

        lang = language.lower()
        for sym_type, p_lang, pattern in patterns:
            if p_lang not in ("text", lang):
                continue
            for i, line in enumerate(lines, 1):
                m = pattern.match(line)
                if m:
                    symbols.append({
                        "type": sym_type,
                        "name": m.group(1),
                        "line": i,
                        "end_line": i,
                    })

        return symbols

    def _find_references_in_content(
        self,
        symbol_name: str,
        file_path: str,
        content: str,
        language: str,
        def_line: int,
        def_end_line: int,
    ) -> list[RefLocation]:
        """Find all references to a symbol in a file's content.

        Searches for identifier nodes matching symbol_name, excluding
        the definition location.
        """
        refs: list[RefLocation] = []
        lines = content.split("\n")

        # Build a regex that matches the symbol name as a whole word
        # Be careful with special regex chars in symbol names
        escaped = re.escape(symbol_name)
        # Allow $ for JS/TS, : for namespaced names
        escaped = escaped.replace(r"\$", "[$]")
        pattern = re.compile(r"\b" + escaped + r"\b")

        for i, line in enumerate(lines, 1):
            # Skip the definition lines
            if def_line <= i <= def_end_line:
                continue

            for m in pattern.finditer(line):
                col = m.start()
                is_call = self._detect_call_context(line, col, m.end(), symbol_name)

                refs.append(RefLocation(
                    file_path=file_path,
                    line=i,
                    column=col,
                    context=line.strip(),
                    node_type="identifier",
                    is_call=is_call,
                ))

        return refs

    def _detect_call_context(
        self,
        line: str,
        start: int,
        end: int,
        name: str,
    ) -> bool:
        """Detect if a symbol occurrence is a function call.

        Heuristic: check if name is followed by '(' with optional whitespace.
        """
        rest = line[end:]
        return bool(re.match(r"\s*\(", rest))

    async def index_directory(self, root: str) -> dict[str, Any]:
        """Index an entire directory tree.

        Args:
            root: Root directory path.

        Returns:
            Summary dict with counts.
        """
        extensions = {
            ".py", ".c", ".h", ".cpp", ".hpp", ".cc", ".cxx",
            ".js", ".ts", ".tsx", ".jsx", ".rs", ".go", ".java",
        }
        results: dict[str, Any] = {
            "files": 0, "symbols": 0, "references": 0, "errors": 0
        }

        for dirpath, _, filenames in os.walk(root):
            for filename in filenames:
                if not any(filename.endswith(ext) for ext in extensions):
                    continue
                path = os.path.join(dirpath, filename)
                result = await self.index_file(path)
                results["files"] += 1
                results["symbols"] += result.get("symbols", 0)
                results["references"] += result.get("references", 0)
                if result.get("status") == "error":
                    results["errors"] += 1

        return results

    # ─── Query API ─────────────────────────────────────────────────────────────

    def find_references(
        self,
        symbol_name: str,
        file_filter: str = "",
    ) -> list[RefLocation]:
        """Find all references to a symbol.

        Args:
            symbol_name: Name of the symbol to search for.
            file_filter: If set, only return refs from files matching this substring.

        Returns:
            List of RefLocation sorted by (file, line).
        """
        refs = self._refs.get(symbol_name, [])
        if file_filter:
            refs = [r for r in refs if file_filter in r.file_path]
        # Sort by file then line
        refs.sort(key=lambda r: (r.file_path, r.line))
        return refs

    def find_callers(self, function_name: str) -> list[RefLocation]:
        """Find all call sites that invoke a function (incoming call graph).

        Returns:
            List of RefLocation where the function is called.
        """
        callers = self._callers.get(function_name, [])
        callers.sort(key=lambda r: (r.file_path, r.line))
        return callers

    def find_callees(self, function_name: str) -> list[RefLocation]:
        """Find all functions called by a function (outgoing call graph).

        Returns:
            List of RefLocation for direct function calls within the given function.
        """
        callees = self._callees.get(function_name, [])
        callees.sort(key=lambda r: (r.file_path, r.line))
        return callees

    def get_symbol_info(self, symbol_name: str) -> SymbolInfo:
        """Get full symbol information: definition + references + call graph.

        Args:
            symbol_name: Name of the symbol.

        Returns:
            SymbolInfo with all known data, or SymbolInfo with empty fields
            if symbol not found.
        """
        defn = self._defs.get(symbol_name)
        refs = self.find_references(symbol_name)
        callers = self.find_callers(symbol_name) if defn and defn.symbol_type == "function" else []
        callees = self.find_callees(symbol_name) if defn and defn.symbol_type == "function" else []

        files = {r.file_path for r in refs}
        if defn:
            files.add(defn.file_path)

        return SymbolInfo(
            name=symbol_name,
            definition=defn,
            references=refs,
            callers=callers,
            callees=callees,
            file_count=len(files),
            total_references=len(refs),
        )

    # ─── Graph queries ──────────────────────────────────────────────────────────

    def get_call_graph(self, root_function: str) -> dict[str, Any]:
        """Get the call graph starting from a root function.

        Returns:
            Dict with 'nodes' (set of function names) and 'edges' (list of (caller, callee)).
        """
        visited: set[str] = set()
        edges: list[tuple[str, str]] = []
        queue = [root_function]

        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)

            callees = self.find_callees(current)
            for callee in callees:
                callee_name = self._extract_name_from_ref(callee)
                if callee_name:
                    edges.append((current, callee_name))
                    if callee_name not in visited:
                        queue.append(callee_name)

        return {"nodes": visited, "edges": edges}

    def find_circular_dependencies(self) -> list[list[str]]:
        """Detect circular dependencies in the call graph using DFS.

        Returns:
            List of cycles, each cycle is a list of function names.
        """
        cycles: list[list[str]] = []
        visited: set[str] = set()
        rec_stack: set[str] = set()
        path: list[str] = []

        def dfs(node: str) -> None:
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for callee_ref in self._callees.get(node, []):
                callee_name = self._extract_name_from_ref(callee_ref)
                if not callee_name:
                    continue
                if callee_name not in visited:
                    dfs(callee_name)
                elif callee_name in rec_stack:
                    # Found a cycle
                    cycle_start = path.index(callee_name)
                    cycle = path[cycle_start:] + [callee_name]
                    cycles.append(cycle)

            path.pop()
            rec_stack.remove(node)

        for fn_name in list(self._callees.keys()):
            if fn_name not in visited:
                dfs(fn_name)

        return cycles

    @staticmethod
    def _extract_name_from_ref(ref: RefLocation) -> str:
        """Extract the symbol name from a RefLocation.
        
        Returns the symbol name (e.g. 'process_data'), not the full context line.
        The 'name' field contains the actual symbol identifier, while 'context'
        contains the full line which would incorrectly include surrounding code.
        """
        return ref.name

    # ─── Type resolution integration ────────────────────────────────────────────

    def set_import_tracker(self, tracker: ImportTracker) -> None:
        """Set import tracker for cross-file resolution."""
        self._import_tracker = tracker

    def resolve_symbol(
        self,
        name: str,
        file_path: str,
        content: str,
        line: int
    ) -> Optional[SymbolLocation]:
        """Resolve a symbol with type information.
        
        Uses type resolution to handle imports and aliases, then falls back
        to normal reference lookup.
        """
        # First try type resolution for imports
        type_info = self._type_resolver.resolve_name(name, content, line)
        if type_info and type_info.module:
            # This name came from an import
            if self._import_tracker:
                symbol_export = self._import_tracker.resolve_import(
                    Path(file_path), name, type_info.module
                )
                if symbol_export:
                    return SymbolLocation(
                        name=name,
                        file_path=symbol_export.file_path,
                        line=symbol_export.line,
                        kind=symbol_export.kind,
                        resolved_from=type_info.full_name
                    )
        
        # Fall back to normal reference lookup
        return self._find_symbol_in_project(name)

    def _find_symbol_in_project(self, name: str) -> Optional[SymbolLocation]:
        """Find a symbol definition in the project."""
        defn = self._defs.get(name)
        if defn:
            return SymbolLocation(
                name=name,
                file_path=Path(defn.file_path),
                line=defn.line,
                kind=defn.symbol_type,
                resolved_from=None
            )
        return None

    def resolve_qualified_symbol(
        self,
        qualified_name: str,
        content: str
    ) -> Optional[TypeInfo]:
        """Resolve a qualified name (e.g., 'numpy.ndarray')."""
        return self._type_resolver.resolve_qualified_name(qualified_name, content)

    # ─── Semantic Resolution ────────────────────────────────────────────────────

    def build_semantic_index(
        self,
        files: list[Path],
        contents: dict[Path, str]
    ) -> None:
        """Build semantic index for cross-file resolution.
        
        Must be called before using semantic resolution methods.
        
        Args:
            files: List of file paths to index.
            contents: Dict mapping file paths to their content strings.
        """
        self._contents_cache = dict(contents)
        self._semantic_resolver.index_project(files, contents)
        self._call_graph = self._call_graph_builder.build(files, contents)

    def build_call_graph(
        self,
        files: list[Path],
        contents: dict[Path, str]
    ) -> CallGraph:
        """Build semantic call graph for the project.
        
        Args:
            files: List of file paths to analyze.
            contents: Dict mapping file paths to their content strings.
            
        Returns:
            CallGraph with edges, callers, callees, and class info.
        """
        self._call_graph = self._call_graph_builder.build(files, contents)
        return self._call_graph

    def resolve_symbol_semantic(
        self,
        name: str,
        file_path: Path,
        content: str,
        line: int
    ) -> Optional[ResolvedSymbol]:
        """Resolve symbol using semantic analysis.
        
        Uses AST-based resolution to handle:
        - Local variable definitions
        - Import statements (including aliases)
        - Module-level exports
        - Builtin functions
        
        Args:
            name: Symbol name to resolve.
            file_path: Path to the file containing the reference.
            content: File content.
            line: Line number of the reference (1-indexed).
            
        Returns:
            ResolvedSymbol with full context, or None if not found.
        """
        return self._semantic_resolver.resolve_symbol(
            name, file_path, content, line
        )

    def resolve_qualified_semantic(
        self,
        qualified: str,
        file_path: Path,
        content: str
    ) -> Optional[ResolvedSymbol]:
        """Resolve qualified name using semantic analysis.
        
        Handles names like 'module.ClassName', 'package.module.function', etc.
        
        Args:
            qualified: Qualified name string.
            file_path: Path to the file containing the reference.
            content: File content.
            
        Returns:
            ResolvedSymbol with full context, or None if not found.
        """
        return self._semantic_resolver.resolve_qualified(qualified, file_path, content)

    def get_semantic_call_graph(self) -> Optional[CallGraph]:
        """Get the semantic call graph.
        
        Returns:
            CallGraph if build_call_graph() has been called, None otherwise.
        """
        return self._call_graph

    def find_call_path(self, start: str, end: str) -> list[str]:
        """Find call path from start to end.
        
        Args:
            start: Starting function name.
            end: Target function name.
            
        Returns:
            List of function names from start to end.
        """
        if not self._call_graph:
            return []
        return self._call_graph.find_path(start, end)

    def find_circular_dependencies_semantic(self) -> list[list[str]]:
        """Find circular dependencies using semantic call graph.
        
        Returns:
            List of cycles, each cycle is a list of function names.
        """
        if not self._call_graph:
            return []
        return self._call_graph.find_cycles()

    def get_method_overrides(
        self,
        base_method: str
    ) -> list:
        """Find methods that override a base class method.
        
        Args:
            base_method: Name of base method (e.g., 'object.__init__').
            
        Returns:
            List of MethodInfo for overriding methods.
        """
        if not self._call_graph:
            return []
        return self._call_graph.find_override_methods(base_method)

    # ─── Maintenance ────────────────────────────────────────────────────────────

    def clear(self) -> None:
        """Clear all indexed data."""
        self._refs.clear()
        self._defs.clear()
        self._file_symbols.clear()
        self._callers.clear()
        self._callees.clear()
        self._import_aliases.clear()  # Clear import aliases
        self._stats = ReferenceGraphStats()
        self._semantic_resolver = SemanticResolver()
        self._call_graph_builder = CallGraphBuilder(self._semantic_resolver)
        self._call_graph = None
        self._contents_cache.clear()

    def remove_file(self, path: str) -> None:
        """Remove all data associated with a file."""
        symbols = self._file_symbols.pop(path, set())
        for name in symbols:
            # Remove refs from this file
            if name in self._refs:
                self._refs[name] = [
                    r for r in self._refs[name] if r.file_path != path
                ]
                if not self._refs[name]:
                    del self._refs[name]
            # Remove callers from this file
            if name in self._callers:
                self._callers[name] = [
                    r for r in self._callers[name] if r.file_path != path
                ]
            # Remove callees from this file
            if name in self._callees:
                self._callees[name] = [
                    r for r in self._callees[name] if r.file_path != path
                ]
        # Remove import aliases for this file
        self._import_aliases.pop(path, None)

    def get_stats(self) -> dict[str, Any]:
        """Get reference graph statistics."""
        circular = self.find_circular_dependencies()
        return {
            "files_indexed": self._stats.files_indexed,
            "symbols_indexed": self._stats.symbols_indexed,
            "total_definitions": len(self._defs),
            "total_references": sum(len(v) for v in self._refs.values()),
            "total_calls": sum(len(v) for v in self._callers.values()),
            "circular_dependencies": len(circular),
            "unique_files": len(self._file_symbols),
        }
