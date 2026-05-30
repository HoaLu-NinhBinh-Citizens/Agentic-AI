"""Dependency graph — tracks module-level imports/exports and detects circular imports.

Provides:
- Module-level import graph (what imports what)
- Circular import detection
- Import path resolution (relative → absolute)
- Export/reexport tracking
- Language-specific import patterns (Python, JS/TS, Rust, Go, C/C++)
- Incremental updates per file

Architecture:
    1. index_file() → extract imports/exports from a single file
    2. _parse_imports() → language-specific import statement parsing
    3. _resolve_import_path() → convert relative imports to absolute
    4. _detect_cycles() → Tarjan's SCC algorithm for circular import detection
    5. get_dependencies() / get_dependents() → query the graph
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ─── Data structures ───────────────────────────────────────────────────────────

@dataclass
class ImportStatement:
    """A single import statement."""
    module: str  # e.g., "os.path" or "." or "..utils"
    names: list[str]  # imported names, e.g. ["Path"] or ["*"]
    is_wildcard: bool = False
    is_relative: bool = False
    level: int = 0  # 0=absolute, 1=single-dot, 2=double-dot, etc.
    line: int = 0
    alias: str = ""  # "as X" alias

    def __hash__(self) -> int:
        return hash((self.module, tuple(self.names), self.level))


@dataclass
class ExportStatement:
    """A single export statement."""
    name: str
    line: int
    is_reexport: bool = False  # re-exporting from another module


@dataclass
class ModuleNode:
    """A module (file) in the dependency graph."""
    path: str  # Absolute or relative module path (e.g., "src/foo/bar.py")
    module_name: str  # Resolved module name (e.g., "foo.bar")
    file_path: str  # Physical file path
    imports: list[ImportStatement] = field(default_factory=list)
    exports: list[ExportStatement] = field(default_factory=list)
    size_lines: int = 0

    def __hash__(self) -> int:
        return hash(self.path)


@dataclass
class ImportEdge:
    """An import relationship: module_a imports module_b."""
    from_module: str  # e.g., "foo.bar"
    to_module: str    # e.g., "os.path"
    file_path: str
    import_stmt: str  # e.g., "from os.path import join"
    line: int
    is_circular: bool = False  # True if part of a circular import

    def __hash__(self) -> int:
        return hash((self.from_module, self.to_module, self.line))


@dataclass
class CircularImport:
    """A detected circular import chain."""
    modules: list[str]  # e.g. ["a", "b", "c", "a"]
    edges: list[tuple[str, str]]  # [(a, b), (b, c), (c, a)]
    severity: str = "error"

    @property
    def cycle_str(self) -> str:
        return " -> ".join(self.modules)


@dataclass
class DependencyGraphStats:
    """Statistics about the dependency graph."""
    modules_indexed: int = 0
    import_edges_added: int = 0
    circular_imports: int = 0
    largest_import_chain: int = 0


# ─── Language-specific import patterns ────────────────────────────────────────

@dataclass
class ImportPattern:
    """Compiled patterns for a language's import syntax."""
    # Python: import X, from X import Y
    python_import = re.compile(r"^\s*import\s+([\w.]+)(?:\s*,\s*([\w.]+))*")
    python_from = re.compile(
        r"^\s*from\s+(?:(\.+)([^\s]+?))?\s+import\s+(.+)$"
    )
    # JS/TS: import X from 'Y', import {X} from 'Y', require('X')
    js_import_named = re.compile(
        r"^\s*import\s+(?:{\s*)?([\w*,\s]+?)(?:\s*})?\s+from\s+['\"]([^'\"]+)['\"]"
    )
    js_import_default = re.compile(
        r"^\s*import\s+([\w$]+)\s+from\s+['\"]([^'\"]+)['\"]"
    )
    js_import_wildcard = re.compile(r"^\s*import\s+\*\s+as\s+(\w+)\s+from\s+['\"]([^'\"]+)['\"]")
    js_require = re.compile(r"^\s*(?:const|let|var|import)\s+.*=\s*require\s*\(['\"]([^'\"]+)['\"]\)")
    # Rust: use X::Y
    rust_use = re.compile(r"^\s*use\s+([\w:]+)")
    # Go: import "X", import ( "X" )
    go_import = re.compile(r'^\s*import\s+(?:(\w+)\s+)?["\']([^"\']+)["\']')
    # C/C++: #include <X> or #include "X"
    cpp_include = re.compile(r'^\s*#\s*include\s*[<"]([^>"]+)[>"]')


# ─── Main dependency graph ──────────────────────────────────────────────────────

class DependencyGraph:
    """Code dependency graph tracking module-level imports and exports.

    Supports: Python, JavaScript, TypeScript, Rust, Go, C/C++

    Usage:
        graph = DependencyGraph()
        await graph.index_directory("src/")
        deps = graph.get_dependencies("mymodule")
        cycles = graph.find_circular_imports()
        edges = graph.get_import_edges("src/foo.py")
    """

    def __init__(self) -> None:
        # module_name → ModuleNode
        self._modules: dict[str, ModuleNode] = {}

        # module_path → module_name (reverse lookup)
        self._path_to_module: dict[str, str] = {}

        # from_module → list of ImportEdge (outgoing)
        self._imports: dict[str, list[ImportEdge]] = {}

        # to_module → list of ImportEdge (incoming)
        self._imported_by: dict[str, list[ImportEdge]] = {}

        # Cache
        self._file_content: dict[str, str] = {}

        self._lock = asyncio.Lock()
        self._stats = DependencyGraphStats()

    @property
    def stats(self) -> DependencyGraphStats:
        return self._stats

    # ─── Indexing ─────────────────────────────────────────────────────────────

    async def index_file(self, path: str) -> dict[str, Any]:
        """Index a single file, extract imports and exports.

        Returns:
            Dict with import/export counts.
        """
        async with self._lock:
            return self._index_file_impl(path)

    def _index_file_impl(self, path: str) -> dict[str, Any]:
        """Internal file indexing (must hold lock)."""
        if not os.path.isfile(path):
            return {"path": path, "status": "not_found"}

        try:
            content = Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            return {"path": path, "status": "error", "error": str(e)}

        self._file_content[path] = content

        module_name = self._path_to_module_name(path)
        imports, exports = self._parse_imports_and_exports(path, content)

        node = ModuleNode(
            path=module_name,
            module_name=module_name,
            file_path=path,
            imports=imports,
            exports=exports,
            size_lines=len(content.splitlines()),
        )
        self._modules[module_name] = node
        self._path_to_module[path] = module_name

        # Build edges
        for imp in imports:
            resolved = self._resolve_import(imp, module_name, path)
            if not resolved:
                continue

            edge = ImportEdge(
                from_module=module_name,
                to_module=resolved,
                file_path=path,
                import_stmt=self._format_import_stmt(imp),
                line=imp.line,
            )
            self._imports.setdefault(module_name, []).append(edge)
            self._imported_by.setdefault(resolved, []).append(edge)

        self._stats.modules_indexed += 1
        self._stats.import_edges_added += len(imports)

        return {
            "path": path,
            "module": module_name,
            "status": "indexed",
            "imports": len(imports),
            "exports": len(exports),
        }

    async def index_directory(self, root: str) -> dict[str, Any]:
        """Index all supported files in a directory tree.

        Returns:
            Summary dict with total counts.
        """
        extensions = {
            ".py",
            ".js", ".jsx", ".ts", ".tsx",
            ".rs", ".go",
            ".c", ".cpp", ".h", ".hpp",
        }
        results: dict[str, Any] = {
            "modules": 0, "imports": 0, "exports": 0, "errors": 0
        }

        for dirpath, _, filenames in os.walk(root):
            for filename in filenames:
                if not any(filename.endswith(ext) for ext in extensions):
                    continue
                path = os.path.join(dirpath, filename)
                result = self._index_file_impl(path)
                results["modules"] += 1
                results["imports"] += result.get("imports", 0)
                results["exports"] += result.get("exports", 0)
                if result.get("status") == "error":
                    results["errors"] += 1

        return results

    # ─── Import parsing ────────────────────────────────────────────────────────

    def _parse_imports_and_exports(
        self,
        path: str,
        content: str,
    ) -> tuple[list[ImportStatement], list[ExportStatement]]:
        """Parse all import and export statements from file content."""
        imports: list[ImportStatement] = []
        exports: list[ExportStatement] = []
        lines = content.split("\n")
        ext = Path(path).suffix.lower()

        parsers = {
            ".py": self._parse_python_imports,
            ".js": self._parse_js_imports,
            ".jsx": self._parse_js_imports,
            ".ts": self._parse_js_imports,
            ".tsx": self._parse_js_imports,
            ".rs": self._parse_rust_imports,
            ".go": self._parse_go_imports,
        }

        parser = parsers.get(ext, self._parse_generic_imports)
        for i, line in enumerate(lines, 1):
            parsed_imports = parser(line, i)
            imports.extend(parsed_imports)

        # Parse exports
        exports = self._parse_exports(path, content)

        return imports, exports

    def _parse_python_imports(self, line: str, line_no: int) -> list[ImportStatement]:
        """Parse a Python import line."""
        imports: list[ImportStatement] = []

        # import X
        m = re.match(r"^\s*import\s+([\w.]+)", line)
        if m:
            module = m.group(1)
            imports.append(ImportStatement(
                module=module,
                names=[],
                is_relative=False,
                level=0,
                line=line_no,
            ))

        # import X as Y
        m = re.match(r"^\s*import\s+([\w.]+)\s+as\s+(\w+)", line)
        if m:
            module, alias = m.group(1), m.group(2)
            imp = ImportStatement(
                module=module,
                names=[],
                is_relative=False,
                level=0,
                line=line_no,
                alias=alias,
            )
            imports.append(imp)

        # from X import Y, Z
        m = re.match(r"^\s*from\s+(\.+)([\w.]*)\s+import\s+(.+)$", line)
        if m:
            level_str, module_part, names_str = m.group(1), m.group(2), m.group(3)
            level = len(level_str) if level_str else 0
            is_relative = level > 0
            module = module_part or ""

            names = [n.strip().split(" as ")[0] for n in names_str.split(",")]
            is_wildcard = "*" in names

            imports.append(ImportStatement(
                module=module,
                names=names,
                is_wildcard=is_wildcard,
                is_relative=is_relative,
                level=level,
                line=line_no,
            ))

        return imports

    def _parse_js_imports(self, line: str, line_no: int) -> list[ImportStatement]:
        """Parse JavaScript/TypeScript import lines."""
        imports: list[ImportStatement] = []

        # import { X } from 'module'
        m = re.match(
            r"^\s*import\s*{\s*([\w,\s]+?)\s*}\s+from\s+['\"]([^'\"]+)['\"]",
            line
        )
        if m:
            names = [n.strip() for n in m.group(1).split(",")]
            imports.append(ImportStatement(
                module=m.group(2),
                names=names,
                is_relative=False,
                level=0,
                line=line_no,
            ))

        # import X from 'module'
        m = re.match(
            r"^\s*import\s+([\w$]+)\s+from\s+['\"]([^'\"]+)['\"]",
            line
        )
        if m:
            imports.append(ImportStatement(
                module=m.group(2),
                names=[m.group(1)],
                is_relative=False,
                level=0,
                line=line_no,
            ))

        # import * as X from 'module'
        m = re.match(
            r"^\s*import\s+\*\s+as\s+(\w+)\s+from\s+['\"]([^'\"]+)['\"]",
            line
        )
        if m:
            imports.append(ImportStatement(
                module=m.group(2),
                names=[m.group(1)],
                is_wildcard=True,
                is_relative=False,
                level=0,
                line=line_no,
            ))

        # const/let/var X = require('module')
        m = re.match(
            r"^\s*(?:const|let|var)\s+\w+\s*=\s*require\s*\(['\"]([^'\"]+)['\"]\)",
            line
        )
        if m:
            imports.append(ImportStatement(
                module=m.group(1),
                names=[],
                is_relative=False,
                level=0,
                line=line_no,
            ))

        return imports

    def _parse_rust_imports(self, line: str, line_no: int) -> list[ImportStatement]:
        """Parse Rust use statements."""
        imports: list[ImportStatement] = []

        # use foo::bar;
        m = re.match(r"^\s*use\s+([\w:]+)", line)
        if m:
            imports.append(ImportStatement(
                module=m.group(1),
                names=[],
                is_relative=False,
                level=0,
                line=line_no,
            ))

        return imports

    def _parse_go_imports(self, line: str, line_no: int) -> list[ImportStatement]:
        """Parse Go import statements."""
        imports: list[ImportStatement] = []

        # import "module"
        m = re.match(r'^\s*import\s+(?:\w+\s+)?["\']([^"\']+)["\']', line)
        if m:
            imports.append(ImportStatement(
                module=m.group(1),
                names=[],
                is_relative=False,
                level=0,
                line=line_no,
            ))

        return imports

    def _parse_generic_imports(self, line: str, line_no: int) -> list[ImportStatement]:
        """Parse generic imports (C/C++ #include, fallback)."""
        imports: list[ImportStatement] = []

        # #include <X> or #include "X"
        m = re.match(r'^\s*#\s*include\s*[<"]([^>"]+)[>"]', line)
        if m:
            imports.append(ImportStatement(
                module=m.group(1),
                names=[],
                is_relative=False,
                level=0,
                line=line_no,
            ))

        return imports

    def _parse_exports(self, path: str, content: str) -> list[ExportStatement]:
        """Parse export statements (language-specific)."""
        exports: list[ExportStatement] = []
        lines = content.split("\n")
        ext = Path(path).suffix.lower()

        if ext in (".js", ".jsx", ".ts", ".tsx"):
            # export { X }, export const X, export function X
            for i, line in enumerate(lines, 1):
                for m in re.finditer(
                    r"export\s+(?:{\s*)?([\w$]+)",
                    line
                ):
                    name = m.group(1).rstrip("}").strip()
                    if name and name not in ("default", "{"):
                        exports.append(ExportStatement(name=name, line=i))
                # export default
                m = re.search(r"export\s+default\s+(\w+)", line)
                if m:
                    exports.append(ExportStatement(name=m.group(1), line=i))

        elif ext == ".py":
            # __all__ = [...]
            for i, line in enumerate(lines, 1):
                m = re.search(r"__all__\s*=\s*\[(.*)\]", line)
                if m:
                    names = re.findall(r"['\"]([\w]+)['\"]", m.group(1))
                    for name in names:
                        exports.append(ExportStatement(name=name, line=i))

        return exports

    # ─── Import resolution ────────────────────────────────────────────────────

    def _resolve_import(
        self,
        imp: ImportStatement,
        current_module: str,
        file_path: str,
    ) -> str | None:
        """Resolve a relative import to an absolute module name."""
        if imp.is_relative:
            return self._resolve_relative_import(imp, current_module)
        return imp.module

    def _resolve_relative_import(
        self,
        imp: ImportStatement,
        current_module: str,
    ) -> str:
        """Resolve a Python relative import (level=1 for ., 2 for .., etc.)."""
        parts = current_module.split(".")

        # Go up 'level-1' directories
        if imp.level > 0:
            up_levels = imp.level - 1
            resolved = ".".join(parts[:-up_levels]) if up_levels < len(parts) else ""
        else:
            resolved = ""

        if imp.module:
            resolved = f"{resolved}.{imp.module}" if resolved else imp.module

        return resolved.lstrip(".")

    def _path_to_module_name(self, path: str) -> str:
        """Convert a file path to a module name."""
        path = str(path)

        # Remove common prefixes
        for prefix in ("src/", "src\\", "lib/", "lib\\", "app/", "app\\"):
            if path.startswith(prefix):
                path = path[len(prefix):]
                break

        # Strip extension
        for ext in (".py", ".js", ".jsx", ".ts", ".tsx", ".rs", ".go"):
            if path.endswith(ext):
                path = path[: -len(ext)]
                break

        # Convert path separators to dots
        path = path.replace("/", ".").replace("\\", ".")

        # Handle __init__ modules
        if path.endswith(".__init__"):
            path = path[:-9]

        return path.strip(".")

    def _format_import_stmt(self, imp: ImportStatement) -> str:
        """Format an ImportStatement back to a string."""
        if imp.is_relative:
            dots = "." * imp.level
            base = f"from {dots}{imp.module}" if imp.module else f"from {dots}"
        else:
            base = f"import {imp.module}"

        if imp.names:
            names = ", ".join(imp.names)
            if imp.is_relative:
                return f"{base} import {names}"
            else:
                return f"{base} import {names}"

        return base

    # ─── Circular import detection ─────────────────────────────────────────────

    def find_circular_imports(self) -> list[CircularImport]:
        """Detect circular import chains using Tarjan's SCC algorithm.

        Returns:
            List of CircularImport objects.
        """
        visited: set[str] = set()
        stack: list[str] = []
        indices: dict[str, int] = {}
        lowlinks: dict[str, int] = {}
        on_stack: set[str] = set()
        index_counter = [0]
        cycles: list[CircularImport] = []

        def strongconnect(node: str) -> None:
            visited.add(node)
            indices[node] = index_counter[0]
            lowlinks[node] = index_counter[0]
            index_counter[0] += 1
            stack.append(node)
            on_stack.add(node)

            for edge in self._imports.get(node, []):
                neighbor = edge.to_module
                if neighbor not in indices:
                    strongconnect(neighbor)
                    lowlinks[node] = min(lowlinks[node], lowlinks[neighbor])
                elif neighbor in on_stack:
                    lowlinks[node] = min(lowlinks[node], indices[neighbor])

            if lowlinks[node] == indices[node]:
                # Found an SCC
                scc: list[str] = []
                while True:
                    w = stack.pop()
                    on_stack.remove(w)
                    scc.append(w)
                    if w == node:
                        break

                if len(scc) > 1:
                    # It's a circular import
                    cycle_modules = list(reversed(scc))
                    edges = [
                        (cycle_modules[i], cycle_modules[(i + 1) % len(cycle_modules)])
                        for i in range(len(cycle_modules))
                    ]
                    cycles.append(CircularImport(
                        modules=cycle_modules,
                        edges=edges,
                        severity="error",
                    ))

                    # Mark edges as circular
                    for from_mod, to_mod in edges:
                        for edge in self._imports.get(from_mod, []):
                            if edge.to_module == to_mod:
                                edge.is_circular = True

        for module in self._modules:
            if module not in visited:
                strongconnect(module)

        self._stats.circular_imports = len(cycles)
        return cycles

    # ─── Query API ────────────────────────────────────────────────────────────

    def get_dependencies(self, module_name: str) -> list[str]:
        """Get direct dependencies of a module (what it imports).

        Args:
            module_name: The module to query.

        Returns:
            List of module names that this module imports.
        """
        edges = self._imports.get(module_name, [])
        return sorted(set(e.to_module for e in edges))

    def get_dependents(self, module_name: str) -> list[str]:
        """Get modules that import this module.

        Args:
            module_name: The module to query.

        Returns:
            List of module names that import this module.
        """
        edges = self._imported_by.get(module_name, [])
        return sorted(set(e.from_module for e in edges))

    def get_import_edges(self, module_name: str) -> list[ImportEdge]:
        """Get all import edges for a module."""
        return self._imports.get(module_name, [])

    def get_all_edges(self) -> list[ImportEdge]:
        """Get all import edges in the graph."""
        edges: list[ImportEdge] = []
        seen: set[tuple[str, str]] = set()
        for module_edges in self._imports.values():
            for edge in module_edges:
                key = (edge.from_module, edge.to_module)
                if key not in seen:
                    seen.add(key)
                    edges.append(edge)
        return edges

    def get_transitive_dependencies(self, module_name: str) -> set[str]:
        """Get all transitive dependencies (BFS)."""
        visited: set[str] = {module_name}
        queue = [module_name]

        while queue:
            current = queue.pop(0)
            for dep in self.get_dependencies(current):
                if dep not in visited:
                    visited.add(dep)
                    queue.append(dep)

        visited.discard(module_name)
        return visited

    def get_transitive_dependents(self, module_name: str) -> set[str]:
        """Get all modules that depend on this module, transitively."""
        visited: set[str] = {module_name}
        queue = [module_name]

        while queue:
            current = queue.pop(0)
            for dep in self.get_dependents(current):
                if dep not in visited:
                    visited.add(dep)
                    queue.append(dep)

        visited.discard(module_name)
        return visited

    # ─── Maintenance ──────────────────────────────────────────────────────────

    def clear(self) -> None:
        """Clear all indexed data."""
        self._modules.clear()
        self._path_to_module.clear()
        self._imports.clear()
        self._imported_by.clear()
        self._file_content.clear()
        self._stats = DependencyGraphStats()

    def remove_file(self, path: str) -> None:
        """Remove all data for a file."""
        module_name = self._path_to_module.pop(path, None)
        if module_name and module_name in self._modules:
            del self._modules[module_name]

        # Remove import edges
        if module_name:
            for edges in self._imports.values():
                edges[:] = [e for e in edges if e.to_module != module_name]
            for edges in self._imported_by.values():
                edges[:] = [e for e in edges if e.from_module != module_name]

    def get_stats(self) -> dict[str, Any]:
        """Get dependency graph statistics."""
        cycles = self.find_circular_imports()
        return {
            "modules_indexed": self._stats.modules_indexed,
            "import_edges": self._stats.import_edges_added,
            "circular_imports": len(cycles),
            "unique_imports": len(self._imports),
            "largest_import_chain": self._stats.largest_import_chain,
        }

    def get_module_info(self, module_name: str) -> dict[str, Any] | None:
        """Get full information about a module."""
        node = self._modules.get(module_name)
        if not node:
            return None

        deps = self.get_dependencies(module_name)
        dependents = self.get_dependents(module_name)

        return {
            "name": node.module_name,
            "path": node.file_path,
            "size_lines": node.size_lines,
            "imports": [self._format_import_stmt(imp) for imp in node.imports],
            "exports": [e.name for e in node.exports],
            "dependencies": deps,
            "dependents": dependents,
            "total_imports": len(node.imports),
            "total_exports": len(node.exports),
        }
