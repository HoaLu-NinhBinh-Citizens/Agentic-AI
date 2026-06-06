"""Cross-file dependency graph resolver.

This module provides cross-file dependency resolution for building complete
dependency graphs across multiple files and languages.

Features:
- Cross-language support (Python, C/C++, JavaScript/TypeScript)
- Import/include dependency tracking
- SafeTreeSitterIndexer integration
- Incremental dependency updates
- Circular dependency detection

Usage:
    resolver = CrossFileResolver(project_root)
    await resolver.build_graph()
    deps = resolver.get_dependents("src/utils.py")
"""

from __future__ import annotations

import ast
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Supported languages with their import patterns
LANGUAGE_PATTERNS = {
    "python": {
        "extensions": {".py"},
        "import_patterns": [
            r"^(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))",
        ],
        "include_patterns": [],
    },
    "c": {
        "extensions": {".c", ".h", ".cpp", ".hpp", ".cc", ".cxx"},
        "import_patterns": [],
        "include_patterns": [
            r'#include\s*[<"]([^>"]+)[>"]',
        ],
    },
    "javascript": {
        "extensions": {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"},
        "import_patterns": [
            r"^(?:import\s+.*?\s+from\s+['\"]([^'\"]+)['\"]|require\s*\(\s*['\"]([^'\"]+)['\"]\s*\))",
        ],
        "include_patterns": [],
    },
    "go": {
        "extensions": {".go"},
        "import_patterns": [
            r"^import\s+(?:\"([^\"]+)\"|(\w+))",
        ],
        "include_patterns": [],
    },
    "rust": {
        "extensions": {".rs"},
        "import_patterns": [
            r"use\s+([^;]+);",
        ],
        "include_patterns": [],
    },
}


@dataclass
class DependencyEdge:
    """An edge in the dependency graph."""
    source: str
    target: str
    dep_type: str  # "import", "include", "inherit", "composite"
    line: int = 0


@dataclass
class DependencyNode:
    """A node in the dependency graph."""
    file_path: str
    language: str
    exports: list[str] = field(default_factory=list)  # Symbols exported by this file
    imports: list[str] = field(default_factory=list)  # Files imported by this file


@dataclass
class DependencyGraphStats:
    """Statistics for the dependency graph."""
    total_files: int = 0
    total_dependencies: int = 0
    languages: dict[str, int] = field(default_factory=dict)
    circular_dependencies: list[list[str]] = field(default_factory=list)
    orphan_files: list[str] = field(default_factory=list)  # Files with no dependencies


class CrossFileResolver:
    """Cross-file dependency graph builder.
    
    This class builds a complete dependency graph across multiple files
    and languages, enabling tracking of import/include relationships.
    
    Usage:
        resolver = CrossFileResolver(Path("src/"))
        await resolver.build_graph()
        
        # Find all files that depend on utils.py
        dependents = resolver.get_dependents("src/utils.py")
        
        # Find all files that utils.py depends on
        dependencies = resolver.get_dependencies("src/utils.py")
    """
    
    def __init__(
        self,
        project_root: Path | str,
        incremental: bool = True,
    ):
        """
        Args:
            project_root: Root directory of the project
            incremental: Enable incremental updates
        """
        self.project_root = Path(project_root) if isinstance(project_root, str) else project_root
        self._incremental = incremental
        
        # Graph data structures
        self._nodes: dict[str, DependencyNode] = {}
        self._edges: list[DependencyEdge] = []
        self._dependents: dict[str, set[str]] = {}  # file -> set of files that depend on it
        self._dependencies: dict[str, set[str]] = {}  # file -> set of files it depends on
        
        # Language detection cache
        self._language_cache: dict[str, str] = {}
        
        # File modification tracking for incremental updates
        self._file_mtimes: dict[str, float] = {}
        
        # Stats
        self._stats: DependencyGraphStats = DependencyGraphStats()
    
    def _detect_language(self, file_path: Path) -> str:
        """Detect programming language from file extension.
        
        Args:
            file_path: Path to file
            
        Returns:
            Language string (python, c, javascript, go, rust)
        """
        path_str = str(file_path)
        if path_str in self._language_cache:
            return self._language_cache[path_str]
        
        suffix = file_path.suffix.lower()
        for lang, patterns in LANGUAGE_PATTERNS.items():
            if suffix in patterns["extensions"]:
                self._language_cache[path_str] = lang
                return lang
        
        self._language_cache[path_str] = "unknown"
        return "unknown"
    
    def _resolve_import(self, import_str: str, source_file: Path) -> Optional[str]:
        """Resolve an import string to an absolute file path.
        
        Args:
            import_str: Import string (e.g., "src.utils", "<stdio.h>")
            source_file: Path to the file containing the import
            
        Returns:
            Resolved file path or None if not resolvable
        """
        import_str = import_str.strip()
        
        # Handle C/C++ includes
        if import_str.startswith("<"):
            # System include - skip
            return None
        
        # Handle relative Python imports
        if "." in import_str or import_str.startswith("src."):
            parts = import_str.split(".")
            
            # Try to resolve as Python module
            for i in range(len(parts), 0, -1):
                module_path = "/".join(parts[:i])
                candidates = [
                    self.project_root / f"{module_path}.py",
                    self.project_root / module_path / "__init__.py",
                ]
                for candidate in candidates:
                    if candidate.exists():
                        return str(candidate)
        
        return None
    
    def _parse_imports_python(self, content: str, file_path: str) -> list[tuple[str, int]]:
        """Parse imports from Python content.
        
        Args:
            content: File content
            file_path: File path (for error messages)
            
        Returns:
            List of (import_str, line_number) tuples
        """
        imports = []
        lines = content.split("\n")
        
        # Regex patterns for Python imports
        import_from_pattern = re.compile(r"^\s*from\s+([\w.]+)\s+import")
        import_pattern = re.compile(r"^\s*import\s+([\w.]+)")
        
        for i, line in enumerate(lines, 1):
            # Skip comments
            if line.strip().startswith("#"):
                continue
            
            # Check for "from X import Y"
            match = import_from_pattern.match(line)
            if match:
                imports.append((match.group(1), i))
                continue
            
            # Check for "import X"
            match = import_pattern.match(line)
            if match:
                imports.append((match.group(1), i))
        
        return imports
    
    def _parse_imports_c(self, content: str, file_path: str) -> list[tuple[str, int]]:
        """Parse includes from C/C++ content.
        
        Args:
            content: File content
            file_path: File path (for error messages)
            
        Returns:
            List of (include_str, line_number) tuples
        """
        imports = []
        lines = content.split("\n")
        
        # C/C++ include patterns
        include_pattern = re.compile(r'#include\s*[<"]([^>"]+)[>"]')
        
        for i, line in enumerate(lines, 1):
            # Skip comments
            stripped = line.strip()
            if stripped.startswith("//") or stripped.startswith("/*"):
                continue
            
            match = include_pattern.search(line)
            if match:
                imports.append((match.group(1), i))
        
        return imports
    
    def _parse_imports_javascript(self, content: str, file_path: str) -> list[tuple[str, int]]:
        """Parse imports from JavaScript/TypeScript content.
        
        Args:
            content: File content
            file_path: File path (for error messages)
            
        Returns:
            List of (import_str, line_number) tuples
        """
        imports = []
        lines = content.split("\n")
        
        # ES6 import patterns
        import_pattern = re.compile(r"import\s+(?:(?:\{[^}]+\}|\*\s+as\s+\w+|\w+)\s+from\s+)?['\"]([^'\"]+)['\"]")
        
        # CommonJS require patterns
        require_pattern = re.compile(r"require\s*\(\s*['\"]([^'\"]+)['\"]\s*\)")
        
        for i, line in enumerate(lines, 1):
            # Skip comments
            stripped = line.strip()
            if stripped.startswith("//") or stripped.startswith("/*"):
                continue
            
            match = import_pattern.search(line)
            if match:
                imports.append((match.group(1), i))
                continue
            
            match = require_pattern.search(line)
            if match:
                imports.append((match.group(1), i))
        
        return imports
    
    def _parse_imports(self, content: str, file_path: Path) -> list[tuple[str, int]]:
        """Parse imports from file content based on language.
        
        Args:
            content: File content
            file_path: Path to file
            
        Returns:
            List of (import_str, line_number) tuples
        """
        language = self._detect_language(file_path)
        
        if language == "python":
            return self._parse_imports_python(content, str(file_path))
        elif language == "c":
            return self._parse_imports_c(content, str(file_path))
        elif language == "javascript":
            return self._parse_imports_javascript(content, str(file_path))
        else:
            return []
    
    async def build_graph(self, files: Optional[list[Path]] = None) -> DependencyGraphStats:
        """Build the dependency graph.
        
        Args:
            files: Optional list of files to analyze (defaults to project root)
            
        Returns:
            DependencyGraphStats with graph statistics
        """
        # Discover files if not provided
        if files is None:
            files = self._discover_files()
        
        self._stats.total_files = len(files)
        
        # Clear existing graph
        self._nodes.clear()
        self._edges.clear()
        self._dependents.clear()
        self._dependencies.clear()
        
        # Process each file
        for file_path in files:
            await self._process_file(file_path)
        
        # Build reverse indices
        self._build_indices()
        
        # Find circular dependencies
        self._stats.circular_dependencies = self._find_circular_dependencies()
        
        # Find orphan files
        self._stats.orphan_files = [
            f for f, deps in self._dependencies.items()
            if not deps and f in self._nodes
        ]
        
        # Compute stats
        self._stats.total_dependencies = len(self._edges)
        self._stats.languages = {
            lang: sum(1 for n in self._nodes.values() if n.language == lang)
            for lang in set(n.language for n in self._nodes.values())
        }
        
        logger.info(
            "Dependency graph built: files=%d, deps=%d, cycles=%d",
            self._stats.total_files,
            self._stats.total_dependencies,
            len(self._stats.circular_dependencies),
        )
        
        return self._stats
    
    def _discover_files(self) -> list[Path]:
        """Discover all source files in project root.
        
        Returns:
            List of source file paths
        """
        extensions: set[str] = set()
        for patterns in LANGUAGE_PATTERNS.values():
            extensions.update(patterns["extensions"])
        
        skip_dirs = {".git", "__pycache__", "node_modules", "build", "dist", ".venv", "venv"}
        
        files: list[Path] = []
        for ext in extensions:
            for file_path in self.project_root.rglob(f"*{ext}"):
                # Skip ignored directories
                if any(skip in file_path.parts for skip in skip_dirs):
                    continue
                files.append(file_path)
        
        return files
    
    async def _process_file(self, file_path: Path) -> None:
        """Process a single file and extract dependencies.
        
        Args:
            file_path: Path to file
        """
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
            language = self._detect_language(file_path)
            path_str = str(file_path)
            
            # Create node
            node = DependencyNode(
                file_path=path_str,
                language=language,
            )
            self._nodes[path_str] = node
            
            # Parse imports
            imports = self._parse_imports(content, file_path)
            
            # Resolve and create edges
            for import_str, line_num in imports:
                resolved = self._resolve_import(import_str, file_path)
                
                if resolved:
                    # Create edge
                    edge = DependencyEdge(
                        source=path_str,
                        target=resolved,
                        dep_type="import" if language == "python" else "include",
                        line=line_num,
                    )
                    self._edges.append(edge)
                    
                    # Track import in node
                    node.imports.append(resolved)
                    
                    # Ensure target node exists
                    if resolved not in self._nodes:
                        self._nodes[resolved] = DependencyNode(
                            file_path=resolved,
                            language=self._detect_language(Path(resolved)),
                        )
            
            # Update mtime tracking
            try:
                self._file_mtimes[path_str] = file_path.stat().st_mtime
            except OSError:
                pass
                
        except Exception as e:
            logger.warning("Failed to process %s: %s", file_path, e)
    
    def _build_indices(self) -> None:
        """Build reverse indices for fast lookups."""
        # Build dependents index (who depends on this file)
        for edge in self._edges:
            if edge.target not in self._dependents:
                self._dependents[edge.target] = set()
            self._dependents[edge.target].add(edge.source)
            
            # Build dependencies index (what does this file depend on)
            if edge.source not in self._dependencies:
                self._dependencies[edge.source] = set()
            self._dependencies[edge.source].add(edge.target)
    
    def get_dependents(self, file_path: str) -> list[str]:
        """Get all files that depend on the given file.
        
        Args:
            file_path: Path to file
            
        Returns:
            List of file paths that depend on this file
        """
        return list(self._dependents.get(file_path, set()))
    
    def get_dependencies(self, file_path: str) -> list[str]:
        """Get all files that the given file depends on.
        
        Args:
            file_path: Path to file
            
        Returns:
            List of file paths that this file depends on
        """
        return list(self._dependencies.get(file_path, set()))
    
    def get_transitive_dependents(self, file_path: str) -> set[str]:
        """Get all files that transitively depend on the given file.
        
        Args:
            file_path: Path to file
            
        Returns:
            Set of all transitive dependent file paths
        """
        result: set[str] = set()
        queue = [file_path]
        
        while queue:
            current = queue.pop()
            for dependent in self._dependents.get(current, set()):
                if dependent not in result:
                    result.add(dependent)
                    queue.append(dependent)
        
        return result
    
    def get_transitive_dependencies(self, file_path: str) -> set[str]:
        """Get all files that the given file transitively depends on.
        
        Args:
            file_path: Path to file
            
        Returns:
            Set of all transitive dependency file paths
        """
        result: set[str] = set()
        queue = [file_path]
        
        while queue:
            current = queue.pop()
            for dep in self._dependencies.get(current, set()):
                if dep not in result:
                    result.add(dep)
                    queue.append(dep)
        
        return result
    
    def get_affected_files(self, changed_file: str) -> list[str]:
        """Get all files that would be affected by changes to the given file.
        
        This includes the file itself and all files that transitively depend on it.
        
        Args:
            changed_file: Path to changed file
            
        Returns:
            List of affected file paths
        """
        affected = self.get_transitive_dependents(changed_file)
        affected.add(changed_file)
        return list(affected)
    
    def _find_circular_dependencies(self) -> list[list[str]]:
        """Find circular dependencies in the graph.
        
        Returns:
            List of cycles, each cycle is a list of file paths
        """
        cycles: list[list[str]] = []
        visited: set[str] = set()
        rec_stack: list[str] = []
        
        def dfs(node: str) -> None:
            if node in rec_stack:
                # Found cycle
                cycle_start = rec_stack.index(node)
                cycle = rec_stack[cycle_start:] + [node]
                cycles.append(cycle)
                return
            
            if node in visited:
                return
            
            visited.add(node)
            rec_stack.append(node)
            
            for dep in self._dependencies.get(node, set()):
                dfs(dep)
            
            rec_stack.pop()
        
        for node in self._nodes:
            if node not in visited:
                dfs(node)
        
        return cycles
    
    def update_file(self, file_path: Path | str) -> list[str]:
        """Update dependencies for a single file.
        
        This is used for incremental updates when a file changes.
        
        Args:
            file_path: Path to changed file
            
        Returns:
            List of files that were updated
        """
        file_path_str = str(file_path)
        updated = [file_path_str]
        
        # Clear old edges for this file
        old_edges = [e for e in self._edges if e.source == file_path_str]
        for edge in old_edges:
            self._edges.remove(edge)
        
        # Clear indices
        self._dependents.clear()
        self._dependencies.clear()
        
        # Re-process file
        if Path(file_path_str).exists():
            asyncio.run(self._process_file(Path(file_path_str)))
        else:
            # File was deleted, remove node
            if file_path_str in self._nodes:
                del self._nodes[file_path_str]
        
        # Rebuild indices
        self._build_indices()
        
        return updated
    
    def to_dict(self) -> dict[str, Any]:
        """Serialize dependency graph to dictionary.
        
        Returns:
            Dictionary representation of the graph
        """
        return {
            "stats": {
                "total_files": self._stats.total_files,
                "total_dependencies": self._stats.total_dependencies,
                "languages": self._stats.languages,
                "circular_dependencies_count": len(self._stats.circular_dependencies),
                "orphan_files_count": len(self._stats.orphan_files),
            },
            "nodes": {
                path: {
                    "language": node.language,
                    "imports": node.imports,
                    "exports": node.exports,
                }
                for path, node in self._nodes.items()
            },
            "edges": [
                {
                    "source": e.source,
                    "target": e.target,
                    "type": e.dep_type,
                    "line": e.line,
                }
                for e in self._edges
            ],
            "circular_dependencies": self._stats.circular_dependencies,
            "orphan_files": self._stats.orphan_files,
        }
    
    @property
    def stats(self) -> DependencyGraphStats:
        """Get graph statistics."""
        return self._stats


# Backward compatibility alias
DependencyResolver = CrossFileResolver
