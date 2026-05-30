"""Symbol graph — builds call graphs, detects circular dependencies, supports incremental updates.

Provides:
- Function/class/struct symbol nodes with metadata
- Call graph edges (caller → callee)
- Circular dependency detection via DFS
- Incremental updates (re-index only changed files)
- Integration with SafeTreeSitterIndexer for language-aware parsing

Architecture:
    1. index_file() → parse with tree-sitter, extract symbols
    2. _build_call_edges() → find function calls and build edges
    3. _detect_cycles() → DFS to find circular dependencies
    4. get_callers() / get_callees() → query call graph
    5. find_circular_deps() → return all cycles
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from src.infrastructure.indexing.tree_sitter import SafeTreeSitterIndexer

logger = logging.getLogger(__name__)


# ─── Data structures ──────────────────────────────────────────────────────────

@dataclass
class SymbolNode:
    """A symbol in the graph."""
    name: str
    kind: str  # "function", "class", "struct", "enum", "type", "impl", "trait"
    file_path: str
    line: int
    end_line: int
    signature: str = ""
    docstring: str = ""
    decorators: list[str] = field(default_factory=list)

    def __hash__(self) -> int:
        return hash((self.name, self.file_path, self.line))


@dataclass
class CallEdge:
    """An edge in the call graph: caller → callee."""
    caller: str  # function name
    caller_file: str
    caller_line: int
    callee: str  # function name being called
    callee_file: str
    callee_line: int
    is_indirect: bool = False  # True if called via function pointer / callback

    def __hash__(self) -> int:
        return hash((self.caller, self.callee, self.caller_line))


@dataclass
class CycleInfo:
    """A detected circular dependency."""
    functions: list[str]  # Cycle path, e.g. [A, B, C, A]
    total_calls: int
    severity: str = "warning"  # "info", "warning", "error"


@dataclass
class SymbolGraphStats:
    """Statistics about the symbol graph."""
    files_indexed: int = 0
    symbols_added: int = 0
    call_edges_added: int = 0
    cycles_detected: int = 0
    incremental_updates: int = 0


# ─── Language-specific patterns ───────────────────────────────────────────────

# Node types that represent call sites (per language)
_CALL_NODE_PATTERNS: dict[str, list[tuple[str, str]]] = {
    # (parent_node_type, identifier_access_pattern)
    "c": [
        (r"\bcall_expression\b", r"\bidentifier\b"),
        (r"\bield_access\b", r"\bidentifier\b"),
    ],
    "cpp": [
        (r"\bcall_expression\b", r"\bidentifier\b"),
        (r"\bield_access\b", r"\bidentifier\b"),
    ],
    "python": [
        (r"\bcall\b", r"\bidentifier\b"),
        (r"\battr\b", r"\bidentifier\b"),
    ],
    "javascript": [
        (r"\bcall_expression\b", r"\bidentifier\b"),
        (r"\bmember_expression\b", r"\bidentifier\b"),
    ],
    "typescript": [
        (r"\bcall_expression\b", r"\bidentifier\b"),
        (r"\bmember_expression\b", r"\bidentifier\b"),
    ],
    "rust": [
        (r"\bcall_expression\b", r"\bidentifier\b"),
        (r"\bield_expression\b", r"\bidentifier\b"),
    ],
    "go": [
        (r"\bcall_expression\b", r"\bidentifier\b"),
    ],
    "java": [
        (r"\bethod_invocation\b", r"\bidentifier\b"),
        (r"\bield_access\b", r"\bidentifier\b"),
    ],
}


# ─── Main symbol graph ─────────────────────────────────────────────────────────

class SymbolGraph:
    """Builds symbol dependency graphs with call graph support.

    Usage:
        indexer = SafeTreeSitterIndexer()
        graph = SymbolGraph(indexer)

        await graph.index_directory("src/")
        callers = graph.get_callers("process_data")
        cycles = graph.find_circular_dependencies()
        deps = graph.get_dependents("MyClass")
    """

    def __init__(
        self,
        indexer: Optional["SafeTreeSitterIndexer"] = None,
    ) -> None:
        self._indexer = indexer
        self._nodes: dict[str, SymbolNode] = {}  # name → node (unique per file+name)
        self._nodes_by_file: dict[str, list[SymbolNode]] = {}  # file → nodes
        self._call_edges: list[CallEdge] = []  # all call edges
        self._callers_map: dict[str, list[CallEdge]] = {}  # callee → incoming edges
        self._callees_map: dict[str, list[CallEdge]] = {}  # caller → outgoing edges
        self._file_content: dict[str, str] = {}  # path → content cache
        self._file_mtime: dict[str, float] = {}  # path → mtime
        self._lock = asyncio.Lock()
        self._stats = SymbolGraphStats()

    @property
    def stats(self) -> SymbolGraphStats:
        return self._stats

    # ─── Indexing ─────────────────────────────────────────────────────────────

    async def index_file(self, path: str) -> dict[str, Any]:
        """Index a single file, extract symbols and call edges.

        Returns:
            Dict with symbol count and call edge count.
        """
        async with self._lock:
            return await self._index_file_impl(path)

    async def _index_file_impl(self, path: str) -> dict[str, Any]:
        """Internal file indexing (must hold lock)."""
        if not os.path.isfile(path):
            return {"path": path, "status": "not_found"}

        try:
            mtime = os.path.getmtime(path)
        except OSError:
            mtime = 0.0

        try:
            content = Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            return {"path": path, "status": "error", "error": str(e)}

        # Check if incremental update needed
        if path in self._file_mtime and self._file_mtime[path] == mtime:
            return {"path": path, "status": "unchanged", "symbols": 0, "edges": 0}

        # Remove old data for this file
        self._remove_file_data(path)

        self._file_mtime[path] = mtime
        self._file_content[path] = content

        # Extract symbols and build call edges
        symbols = self._extract_symbols(path, content)
        edges = self._extract_call_edges(path, content, symbols)

        # Register nodes
        file_nodes: list[SymbolNode] = []
        for sym in symbols:
            node = SymbolNode(
                name=sym["name"],
                kind=sym["kind"],
                file_path=path,
                line=sym["line"],
                end_line=sym.get("end_line", sym["line"]),
                signature=sym.get("signature", ""),
                decorators=sym.get("decorators", []),
            )
            self._nodes[sym["name"]] = node
            file_nodes.append(node)

        self._nodes_by_file[path] = file_nodes

        # Register call edges
        for edge in edges:
            self._call_edges.append(edge)
            self._callers_map.setdefault(edge.callee, []).append(edge)
            self._callees_map.setdefault(edge.caller, []).append(edge)

        self._stats.files_indexed += 1
        self._stats.symbols_added += len(symbols)
        self._stats.call_edges_added += len(edges)
        self._stats.incremental_updates += 1

        return {
            "path": path,
            "status": "indexed",
            "symbols": len(symbols),
            "edges": len(edges),
        }

    async def index_directory(self, root: str) -> dict[str, Any]:
        """Index all supported files in a directory tree.

        Returns:
            Summary dict with total counts.
        """
        extensions = {".py", ".c", ".h", ".cpp", ".hpp", ".cc",
                      ".js", ".ts", ".tsx", ".rs", ".go", ".java"}
        results: dict[str, Any] = {
            "files": 0, "symbols": 0, "edges": 0, "errors": 0
        }

        for dirpath, _, filenames in os.walk(root):
            for filename in filenames:
                if not any(filename.endswith(ext) for ext in extensions):
                    continue
                path = os.path.join(dirpath, filename)
                result = await self.index_file(path)
                results["files"] += 1
                results["symbols"] += result.get("symbols", 0)
                results["edges"] += result.get("edges", 0)
                if result.get("status") == "error":
                    results["errors"] += 1

        return results

    def _remove_file_data(self, path: str) -> None:
        """Remove all data for a file (for incremental re-index)."""
        # Remove nodes
        if path in self._nodes_by_file:
            for node in self._nodes_by_file[path]:
                self._nodes.pop(node.name, None)
            del self._nodes_by_file[path]
            self._stats.files_indexed = max(0, self._stats.files_indexed - 1)

        # Remove edges
        old_edges = [e for e in self._call_edges if e.caller_file == path or e.callee_file == path]
        for edge in old_edges:
            self._call_edges.remove(edge)
            callers = self._callers_map.get(edge.callee, [])
            if edge in callers:
                callers.remove(edge)
            callees = self._callees_map.get(edge.caller, [])
            if edge in callees:
                callees.remove(edge)

        self._file_content.pop(path, None)
        self._file_mtime.pop(path, None)

    # ─── Symbol extraction ─────────────────────────────────────────────────────

    def _extract_symbols(self, path: str, content: str) -> list[dict[str, Any]]:
        """Extract symbol definitions from file content.

        Uses SafeTreeSitterIndexer if available, falls back to regex.
        """
        if self._indexer is not None:
            try:
                import asyncio
                result = asyncio.run(self._indexer.index_file(path, content))
                return result.get("symbols", [])
            except Exception as e:
                logger.debug("indexer_failed_for_symbols", path=path, error=str(e))

        return self._extract_symbols_regex(path, content)

    def _extract_symbols_regex(self, path: str, content: str) -> list[dict[str, Any]]:
        """Regex-based symbol extraction (fallback)."""
        symbols: list[dict[str, Any]] = []
        lines = content.split("\n")
        ext = Path(path).suffix.lower()

        patterns: list[tuple[str, str, Any]] = [
            # Python
            ("function", "py",
             re.compile(r"^\s*(?:async\s+)?def\s+([a-zA-Z_][\w]*)\s*\(")),
            ("class", "py",
             re.compile(r"^\s*class\s+([A-Za-z_][\w]*)\s*(?:\([^)]*\))?:")),
            # C / C++
            ("function", "c",
             re.compile(r"^\s*(?:static\s+|inline\s+)?"
                       r"(?:void|int|char|float|double|bool|long|short|unsigned|[A-Z_][\w]*)\s*"
                       r"([a-z_][a-z0-9_]*)\s*\([^;{]*\{")),
            ("struct", "c",
             re.compile(r"^\s*struct\s+([A-Za-z_][\w]*)\s*\{")),
            ("enum", "c",
             re.compile(r"^\s*enum\s+([A-Za-z_][\w]*)\s*\{")),
            # JavaScript / TypeScript
            ("function", "js",
             re.compile(r"^\s*(?:async\s+)?function\s+([a-zA-Z_$][\w$]*)\s*\(")),
            ("class", "js",
             re.compile(r"^\s*class\s+([A-Za-z_$][\w$]*)\s*(?:extends)?")),
            ("function", "ts",
             re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+([a-zA-Z_$][\w$]*)\s*\(")),
            ("class", "ts",
             re.compile(r"^\s*(?:export\s+)?class\s+([A-Za-z_$][\w$]*)\s*(?:extends|implements)?")),
            # Rust
            ("function", "rs",
             re.compile(r"^\s*(?:pub\s+)?(?:async\s+)?fn\s+([a-z_][\w]*)\s*[<(]")),
            ("struct", "rs",
             re.compile(r"^\s*struct\s+([A-Za-z_][\w]*)\s*(?:<[^>]*>)?\s*[{:]")),
            ("enum", "rs",
             re.compile(r"^\s*enum\s+([A-Za-z_][\w]*)\s*(?:<[^>]*>)?")),
            # Go
            ("function", "go",
             re.compile(r"^\s*func\s+(?:\([^)]*\)\s*)?([A-Za-z_][\w]*)\s*\(")),
        ]

        # Map extension to language key
        ext_map = {".py": "py", ".c": "c", ".cpp": "c", ".h": "c", ".hpp": "c",
                   ".js": "js", ".ts": "ts", ".tsx": "ts", ".jsx": "js",
                   ".rs": "rs", ".go": "go", ".java": "c"}

        lang = ext_map.get(ext, "text")

        def _get_indent(line: str) -> int:
            """Get indentation level of a line (spaces / tab equivalent)."""
            stripped = line.lstrip()
            return len(line) - len(stripped)

        def _compute_end_line(
            def_line: int,
            def_indent: int,
            lines: list[str],
            language: str,
        ) -> int:
            """Compute end line for a symbol using indentation / brace tracking."""
            if language in ("py", "rs", "go"):
                # Skip blank lines and find dedent
                for j in range(def_line + 1, len(lines)):
                    ln = lines[j]
                    if ln.strip() == "":
                        continue
                    # End of scope when we see a line with <= def_indent that's not whitespace
                    if _get_indent(ln) <= def_indent:
                        return j
                return def_line
            elif language == "c":
                # Check if opening brace is on the def line
                def_text = lines[def_line - 1]
                if "{" not in def_text:
                    return def_line
                # Track brace depth
                brace_depth = def_text.count("{") - def_text.count("}")
                for j in range(def_line, len(lines)):
                    brace_depth += lines[j].count("{") - lines[j].count("}")
                    if brace_depth <= 0 and j > def_line - 1:
                        return j
                return def_line
            return def_line

        for kind, p_lang, pattern in patterns:
            if p_lang not in ("text", lang):
                continue
            for i, line in enumerate(lines, 1):
                m = pattern.match(line)
                if m:
                    # Extract decorators for Python
                    decorators: list[str] = []
                    if i > 1 and lang == "py":
                        dec_line = lines[i - 2].strip()
                        if dec_line.startswith("@"):
                            decorators.append(dec_line[1:])

                    # Compute end_line using indentation
                    def_indent = _get_indent(line)
                    end_ln = _compute_end_line(i, def_indent, lines, lang)

                    symbols.append({
                        "name": m.group(1),
                        "kind": kind,
                        "line": i,
                        "end_line": end_ln,
                        "decorators": decorators,
                        "signature": line.strip(),
                    })

        return symbols

    # ─── Call edge extraction ─────────────────────────────────────────────────

    def _extract_call_edges(
        self,
        path: str,
        content: str,
        symbols: list[dict[str, Any]],
    ) -> list[CallEdge]:
        """Extract function call edges from file content.

        For each function definition, finds all function calls within its body
        and creates CallEdge entries.
        """
        edges: list[CallEdge] = []
        lines = content.split("\n")

        # Build function body ranges
        functions: list[tuple[str, int, int]] = []
        for sym in symbols:
            if sym.get("kind") == "function":
                functions.append((sym["name"], sym["line"], sym.get("end_line", sym["line"])))

        # Find all function calls using regex
        # Pattern: identifier followed by ( — handles most languages
        # Use ^|\s instead of \b so it matches both start-of-line and after whitespace
        call_pattern = re.compile(r"(?:^|\s)([a-zA-Z_][\w]{0,64})\s*\(")

        for func_name, start_line, end_line in functions:
            body_lines = lines[start_line - 1:end_line]

            for i, line in enumerate(body_lines):
                # Skip comments and strings; strip leading indentation for regex matching
                stripped = self._strip_comments_and_strings(line.lstrip())
                # Skip definition lines (def, class, async def, etc.)
                if stripped.startswith(("def ", "class ", "async ", "fn ", "func ", "struct ", "enum ")):
                    continue
                for m in call_pattern.finditer(stripped):
                    called = m.group(1)
                    # Skip built-in / keywords
                    if called in {
                        "if", "while", "for", "return", "throw",
                        "print", "len", "range", "str", "int", "float",
                        "list", "dict", "set", "tuple", "map", "filter",
                        "abs", "min", "max", "sum", "sorted", "reversed",
                        "open", "super", "self", "this", "True", "False", "None",
                    }:
                        continue
                    # Skip if it looks like a macro/define
                    if called.isupper():
                        continue

                    called_line = start_line + i

                    edges.append(CallEdge(
                        caller=func_name,
                        caller_file=path,
                        caller_line=start_line,
                        callee=called,
                        callee_file=path,
                        callee_line=called_line,
                    ))

        return edges

    @staticmethod
    def _strip_comments_and_strings(line: str) -> str:
        """Remove comments and string literals from a line for analysis."""
        result = []
        i = 0
        in_string = False
        string_char = ""
        in_multiline_comment = False

        while i < len(line):
            c = line[i]

            # Handle multiline comment
            if not in_string and i + 1 < len(line) and line[i:i+2] == "/*":
                in_multiline_comment = True
                i += 2
                continue
            if in_multiline_comment:
                if i + 1 < len(line) and line[i:i+2] == "*/":
                    in_multiline_comment = False
                    i += 2
                else:
                    i += 1
                continue

            # Handle single-line comment
            if not in_string and c == "/" and i + 1 < len(line) and line[i+1] == "/":
                break  # Rest of line is comment

            # Handle Python comment
            if not in_string and c == "#":
                break

            # Handle strings — only trigger on unescaped quotes
            if c in ('"', "'"):
                # Check for escaped quote: preceded by backslash with even count
                escaped = False
                j = i - 1
                backslash_count = 0
                while j >= 0 and line[j] == "\\":
                    backslash_count += 1
                    j -= 1
                if backslash_count % 2 == 1:
                    escaped = True

                if not escaped:
                    if not in_string:
                        in_string = True
                        string_char = c
                        result.append(" ")  # Replace opening quote with space
                    elif c == string_char:
                        in_string = False
                        result.append(" ")  # Replace closing quote with space
                    i += 1
                    continue

            if not in_string:
                result.append(c)
            i += 1

        return "".join(result)

    # ─── Call graph queries ───────────────────────────────────────────────────

    def get_callers(self, function_name: str) -> list[CallEdge]:
        """Get all functions that call the given function (incoming edges)."""
        edges = self._callers_map.get(function_name, [])
        return sorted(edges, key=lambda e: (e.caller_file, e.caller_line))

    def get_callees(self, function_name: str) -> list[CallEdge]:
        """Get all functions called by the given function (outgoing edges)."""
        edges = self._callees_map.get(function_name, [])
        return sorted(edges, key=lambda e: (e.callee_file, e.callee_line))

    def get_dependents(self, symbol_name: str) -> list[str]:
        """Get symbols that depend on this symbol (transitive closure of call graph)."""
        visited: set[str] = set()
        queue = [symbol_name]

        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)

            callers = self.get_callers(current)
            for edge in callers:
                if edge.caller not in visited:
                    queue.append(edge.caller)

        visited.discard(symbol_name)
        return sorted(visited)

    def get_dependencies(self, symbol_name: str) -> list[str]:
        """Get symbols that this symbol depends on (transitive closure)."""
        visited: set[str] = set()
        queue = [symbol_name]

        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)

            callees = self.get_callees(current)
            for edge in callees:
                if edge.callee not in visited:
                    queue.append(edge.callee)

        visited.discard(symbol_name)
        return sorted(visited)

    # ─── Circular dependency detection ─────────────────────────────────────────

    def find_circular_dependencies(self) -> list[CycleInfo]:
        """Detect circular dependencies in the call graph via DFS.

        Returns:
            List of CycleInfo, each containing the cycle path and metadata.
        """
        cycles: list[CycleInfo] = []
        visited: set[str] = set()
        rec_stack: set[str] = set()
        path: list[str] = []

        def dfs(node: str) -> None:
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for edge in self._callees_map.get(node, []):
                callee = edge.callee
                if callee not in visited:
                    dfs(callee)
                elif callee in rec_stack:
                    cycle_start = path.index(callee)
                    cycle = path[cycle_start:] + [callee]
                    cycles.append(CycleInfo(
                        functions=cycle,
                        total_calls=len(cycle) - 1,
                        severity="warning" if len(cycle) <= 4 else "error",
                    ))

            path.pop()
            rec_stack.remove(node)

        for fn_name in list(self._callees_map.keys()):
            if fn_name not in visited:
                dfs(fn_name)

        # Deduplicate cycles (same cycle can appear multiple ways)
        seen: set[tuple[str, ...]] = set()
        unique: list[CycleInfo] = []
        for cycle in cycles:
            key = tuple(cycle.functions)
            if key not in seen:
                seen.add(key)
                unique.append(cycle)

        self._stats.cycles_detected = len(unique)
        return unique

    # ─── Graph traversal ───────────────────────────────────────────────────────

    def get_reachable(self, root: str, direction: str = "callees") -> set[str]:
        """Get all functions reachable from root.

        Args:
            root: Starting function name.
            direction: "callees" for forward traversal, "callers" for backward.
        """
        visited: set[str] = set()
        queue = [root]

        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)

            if direction == "callees":
                edges = self._callees_map.get(current, [])
                for edge in edges:
                    if edge.callee not in visited:
                        queue.append(edge.callee)
            else:
                edges = self._callers_map.get(current, [])
                for edge in edges:
                    if edge.caller not in visited:
                        queue.append(edge.caller)

        visited.discard(root)
        return visited

    def get_call_depth(self, caller: str, callee: str) -> int | None:
        """Find the minimum call depth from caller to callee (BFS).

        Returns:
            Number of hops, or None if not reachable.
        """
        visited: set[str] = {caller}
        queue: list[tuple[str, int]] = [(caller, 0)]

        while queue:
            current, depth = queue.pop(0)
            for edge in self._callees_map.get(current, []):
                if edge.callee == callee:
                    return depth + 1
                if edge.callee not in visited:
                    visited.add(edge.callee)
                    queue.append((edge.callee, depth + 1))

        return None

    # ─── Maintenance ───────────────────────────────────────────────────────────

    def clear(self) -> None:
        """Clear all indexed data."""
        self._nodes.clear()
        self._nodes_by_file.clear()
        self._call_edges.clear()
        self._callers_map.clear()
        self._callees_map.clear()
        self._file_content.clear()
        self._file_mtime.clear()
        self._stats = SymbolGraphStats()

    def get_stats(self) -> dict[str, Any]:
        """Get symbol graph statistics."""
        cycles = self.find_circular_dependencies()
        return {
            "files_indexed": self._stats.files_indexed,
            "total_symbols": len(self._nodes),
            "call_edges": len(self._call_edges),
            "circular_dependencies": len(cycles),
            "incremental_updates": self._stats.incremental_updates,
            "unique_callers": len(self._callers_map),
            "unique_callees": len(self._callees_map),
        }
