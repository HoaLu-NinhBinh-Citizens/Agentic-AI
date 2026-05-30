"""Unified CodeContext — provides ALL context needed by any detector.

This replaces fragmented approaches where each detector collected its own context.
Now, all detectors receive a single CodeContext containing:
- File content and AST (from SafeTreeSitterIndexer)
- Symbol definitions and references (from ReferenceGraph)
- Import/export information (from DependencyGraph)
- Semantic chunks (from IncrementalIndexer)
- File state for incremental analysis

Architecture:
    CodeContextBuilder aggregates data from multiple sources:
    1. SafeTreeSitterIndexer → AST, content, language
    2. ReferenceGraph → symbol_defs, symbol_refs, call_graph
    3. DependencyGraph → imports, exports, alias_map
    4. IncrementalIndexer → chunked_content, file_state
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from src.infrastructure.indexing.tree_sitter import SafeTreeSitterIndexer
    from src.infrastructure.indexing.reference_graph import ReferenceGraph
    from src.infrastructure.indexing.dependency_graph import DependencyGraph

# ─── Location Types ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class DefLocation:
    """Location of a symbol definition."""
    file_path: str
    line: int
    column: int
    end_line: int
    symbol_type: str  # "function", "class", "struct", "enum", etc.
    node_type: str = ""
    signature: str = ""


@dataclass(frozen=True)
class RefLocation:
    """Location of a symbol reference."""
    file_path: str
    line: int
    column: int
    context: str  # Surrounding line text
    node_type: str = "identifier"
    is_call: bool = False


@dataclass(frozen=True)
class CallGraph:
    """Call graph edges for a function."""
    callers: list[RefLocation] = field(default_factory=list)
    callees: list[RefLocation] = field(default_factory=list)

    @property
    def is_leaf(self) -> bool:
        """True if this function calls no other functions."""
        return len(self.callees) == 0

    @property
    def is_root(self) -> bool:
        """True if no other functions call this one."""
        return len(self.callers) == 0


@dataclass(frozen=True)
class ImportInfo:
    """Information about an import statement."""
    module: str
    names: list[str]
    line: int
    is_wildcard: bool = False
    is_relative: bool = False
    alias: str = ""


@dataclass(frozen=True)
class ExportInfo:
    """Information about an exported symbol."""
    name: str
    line: int
    is_reexport: bool = False


@dataclass(frozen=True)
class CodeChunk:
    """A semantic chunk of code (function, class, block)."""
    start_line: int
    end_line: int
    chunk_type: str  # "function", "class", "if_block", "loop", etc.
    name: str = ""
    docstring: str = ""


@dataclass(frozen=True)
class FileState:
    """File state for incremental analysis."""
    mtime: float
    content_hash: str
    size_bytes: int
    line_count: int


@dataclass(frozen=True)
class CallContext:
    """Context around a function call site."""
    caller: str  # Function name calling the target
    call_line: int
    args: list[str] = field(default_factory=list)
    keyword_args: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SymbolDef:
    """A symbol definition with full information."""
    name: str
    location: DefLocation
    references: list[RefLocation] = field(default_factory=list)
    call_graph: CallGraph = field(default_factory=CallGraph)


# ─── Main Context Class ───────────────────────────────────────────────────────


@dataclass
class CodeContext:
    """Unified context object passed to ALL detectors.

    This dataclass aggregates all information needed by any detector:
    - File content and AST (from SafeTreeSitterIndexer)
    - Symbol definitions and references (from ReferenceGraph)
    - Import/export information (from DependencyGraph)
    - Semantic chunks (from IncrementalIndexer)

    Detectors should prefer this context over collecting their own data.
    """
    file_path: Path
    content: str
    ast_root: Optional[Any]  # tree-sitter AST root node
    language: str

    # From ReferenceGraph
    symbol_defs: dict[str, DefLocation] = field(default_factory=dict)
    symbol_refs: dict[str, list[RefLocation]] = field(default_factory=dict)
    call_graph: dict[str, CallGraph] = field(default_factory=dict)

    # From DependencyGraph
    imports: list[ImportInfo] = field(default_factory=list)
    exports: list[str] = field(default_factory=list)
    alias_map: dict[str, str] = field(default_factory=dict)

    # From IncrementalIndexer
    chunked_content: list[CodeChunk] = field(default_factory=list)
    file_state: Optional[FileState] = None

    # Cached helpers
    _lines: list[str] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        """Cache lines for efficient access."""
        if not self._lines:
            object.__setattr__(self, "_lines", self.content.split("\n"))

    @property
    def lines(self) -> list[str]:
        """Get file lines (cached)."""
        return self._lines

    def get_symbol_around(self, line: int, col: int) -> Optional[str]:
        """Find symbol name at or near given position.

        Args:
            line: 1-based line number
            col: 0-based column

        Returns:
            Symbol name if found, None otherwise
        """
        if not (1 <= line <= len(self._lines)):
            return None

        line_text = self._lines[line - 1]

        # Match word at position
        pattern = r'\b([a-zA-Z_][a-zA-Z0-9_]*)\b'
        for match in re.finditer(pattern, line_text):
            if match.start() <= col < match.end():
                return match.group(1)

        # Try previous word if at end
        words = re.findall(pattern, line_text)
        for word in reversed(words):
            word_pos = line_text.rfind(word)
            if word_pos + len(word) <= col:
                return word

        return None

    def get_call_context(self, line: int, symbol: str) -> Optional[CallContext]:
        """Get context around a function call.

        Args:
            line: Line number of the call
            symbol: Function being called

        Returns:
            CallContext with caller info, or None if not a call
        """
        if not (1 <= line <= len(self._lines)):
            return None

        # Find enclosing function
        caller = self.get_function_containing(line)
        if not caller:
            return None

        # Extract call arguments
        call_line = self._lines[line - 1]
        args = self._extract_call_args(call_line, symbol)

        return CallContext(
            caller=caller.name if caller else "",
            call_line=line,
            args=args.args,
            keyword_args=args.kwargs,
        )

    def _extract_call_args(
        self, line: str, symbol: str
    ) -> tuple[list[str], dict[str, str]]:
        """Extract positional and keyword arguments from a call.

        Args:
            line: The line containing the call
            symbol: The function being called

        Returns:
            Tuple of (positional_args, keyword_args)
        """
        # Find the call pattern
        pattern = rf'\b{symbol}\s*\((.*)\)\s*;?\s*$'
        match = re.search(pattern, line)

        if not match:
            return [], {}

        args_str = match.group(1)
        if not args_str.strip():
            return [], {}

        args: list[str] = []
        kwargs: dict[str, str] = {}

        # Split by comma, handling nested parens/brackets
        depth = 0
        current = ""
        for char in args_str:
            if char in "([{":
                depth += 1
            elif char in ")]}":
                depth -= 1
            elif char == "," and depth == 0:
                if "=" in current:
                    key, val = current.split("=", 1)
                    kwargs[key.strip()] = val.strip()
                else:
                    args.append(current.strip())
                current = ""
                continue
            current += char

        if current.strip():
            if "=" in current:
                key, val = current.split("=", 1)
                kwargs[key.strip()] = val.strip()
            else:
                args.append(current.strip())

        return args, kwargs

    def resolve_alias(self, name: str) -> Optional[str]:
        """Resolve an import alias to its original name.

        Args:
            name: Possibly-aliased name (e.g., "HC" from "import HeavyClass as HC")

        Returns:
            Original name if found, None otherwise
        """
        return self.alias_map.get(name)

    def get_surrounding_code(self, line: int, radius: int = 5) -> str:
        """Get lines around a position.

        Args:
            line: Center line (1-based)
            radius: Number of lines before and after

        Returns:
            String with line numbers and content
        """
        start = max(1, line - radius)
        end = min(len(self._lines), line + radius)

        result_lines = []
        for i in range(start, end + 1):
            prefix = ">>>" if i == line else "   "
            result_lines.append(f"{prefix} {i:4d}│ {self._lines[i - 1]}")

        return "\n".join(result_lines)

    def get_function_containing(self, line: int) -> Optional[SymbolDef]:
        """Find the function that contains the given line.

        Args:
            line: 1-based line number

        Returns:
            SymbolDef of containing function, or None
        """
        for name, def_loc in self.symbol_defs.items():
            if def_loc.symbol_type == "function":
                if def_loc.line <= line <= def_loc.end_line:
                    return SymbolDef(
                        name=name,
                        location=def_loc,
                        references=self.symbol_refs.get(name, []),
                        call_graph=self.call_graph.get(name, CallGraph()),
                    )
        return None

    def get_chunk_at(self, line: int) -> Optional[CodeChunk]:
        """Get the semantic chunk containing the given line.

        Args:
            line: 1-based line number

        Returns:
            CodeChunk if found, None otherwise
        """
        for chunk in self.chunked_content:
            if chunk.start_line <= line <= chunk.end_line:
                return chunk
        return None

    def get_imports_of_module(self, module: str) -> list[ImportInfo]:
        """Get all imports from a specific module.

        Args:
            module: Module name (e.g., "os.path")

        Returns:
            List of ImportInfo objects
        """
        return [imp for imp in self.imports if imp.module == module]

    def is_symbol_exported(self, name: str) -> bool:
        """Check if a symbol is exported (in __all__ or explicit exports).

        Args:
            name: Symbol name to check

        Returns:
            True if exported
        """
        return name in self.exports


# ─── Context Builder ─────────────────────────────────────────────────────────


@dataclass
class DetectorConfig:
    """Configuration for a detector."""
    enabled: bool = True
    focus_areas: list[str] = field(default_factory=list)
    severity_filter: list[str] = field(default_factory=list)
    confidence_threshold: float = 0.5


@dataclass
class CodeContextBuilder:
    """Builds CodeContext from multiple data sources.

    Aggregates data from:
    1. SafeTreeSitterIndexer
    2. ReferenceGraph
    3. DependencyGraph
    4. IncrementalIndexer (if available)

    Usage:
        builder = CodeContextBuilder(indexer, ref_graph, dep_graph)
        context = await builder.build(file_path)
    """

    indexer: "SafeTreeSitterIndexer"
    ref_graph: "ReferenceGraph"
    dep_graph: "DependencyGraph"

    def __init__(
        self,
        indexer: "SafeTreeSitterIndexer",
        ref_graph: "ReferenceGraph",
        dep_graph: "DependencyGraph",
    ) -> None:
        self.indexer = indexer
        self.ref_graph = ref_graph
        self.dep_graph = dep_graph

    async def build(self, file_path: Path) -> CodeContext:
        """Build complete CodeContext for a file.

        Args:
            file_path: Path to the source file

        Returns:
            Complete CodeContext with all information
        """
        # Read file content
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            raise ValueError(f"Cannot read file {file_path}: {e}")

        # Get language from extension
        language = self._detect_language(file_path)

        # Parse with tree-sitter
        ast_root = await self._parse_ast(file_path, content, language)

        # Build reference info
        symbol_defs, symbol_refs, call_graph = await self._build_reference_info(
            file_path, content, language
        )

        # Build dependency info
        imports, exports, alias_map = await self._build_dependency_info(file_path)

        # Build semantic chunks
        chunks = self._build_chunks(ast_root, content, language)

        # Build file state
        file_state = self._build_file_state(file_path, content)

        return CodeContext(
            file_path=file_path,
            content=content,
            ast_root=ast_root,
            language=language,
            symbol_defs=symbol_defs,
            symbol_refs=symbol_refs,
            call_graph=call_graph,
            imports=imports,
            exports=exports,
            alias_map=alias_map,
            chunked_content=chunks,
            file_state=file_state,
        )

    async def _parse_ast(
        self,
        file_path: Path,
        content: str,
        language: str,
    ) -> Optional[Any]:
        """Parse file content into tree-sitter AST."""
        try:
            result = await self.indexer.index_file(str(file_path), content)
            if result.get("status") == "success":
                # FIX: Return actual AST root node, not symbols list
                ast_root = result.get("ast_root")
                if ast_root is not None:
                    self.ast_root = ast_root
                    return ast_root
                # Fallback: try to get tree object from parser
                parser = self.indexer._parser_cache.get(language)
                if parser is not None:
                    import tree_sitter_languages
                    tree = parser.parse(content.encode("utf-8", errors="replace"))
                    self.ast_root = tree.root_node
                    return tree.root_node
        except Exception:
            pass
        return None

    async def _build_reference_info(
        self,
        file_path: Path,
        content: str,
        language: str,
    ) -> tuple[dict[str, DefLocation], dict[str, list[RefLocation]], dict[str, CallGraph]]:
        """Build symbol definitions, references, and call graph."""
        symbol_defs: dict[str, DefLocation] = {}
        symbol_refs: dict[str, list[RefLocation]] = {}
        call_graph: dict[str, CallGraph] = {}

        # Index the file in reference graph
        await self.ref_graph.index_file(str(file_path))

        # Collect definitions and references
        for name, defn in self.ref_graph._defs.items():
            if defn.file_path == str(file_path):
                symbol_defs[name] = DefLocation(
                    file_path=defn.file_path,
                    line=defn.line,
                    column=defn.column,
                    end_line=defn.end_line,
                    symbol_type=defn.symbol_type,
                    node_type=defn.node_type,
                    signature=defn.signature,
                )

        # Collect references
        for name, refs in self.ref_graph._refs.items():
            file_refs = [
                RefLocation(
                    file_path=r.file_path,
                    line=r.line,
                    column=r.column,
                    context=r.context,
                    node_type=r.node_type,
                    is_call=r.is_call,
                )
                for r in refs
                if r.file_path == str(file_path)
            ]
            if file_refs:
                symbol_refs[name] = file_refs

        # Build call graphs
        for name in symbol_defs:
            callers = [
                RefLocation(
                    file_path=r.file_path,
                    line=r.line,
                    column=r.column,
                    context=r.context,
                    node_type=r.node_type,
                    is_call=True,
                )
                for r in self.ref_graph._callers.get(name, [])
                if r.file_path == str(file_path)
            ]
            callees = [
                RefLocation(
                    file_path=r.file_path,
                    line=r.line,
                    column=r.column,
                    context=r.context,
                    node_type=r.node_type,
                    is_call=True,
                )
                for r in self.ref_graph._callees.get(name, [])
                if r.file_path == str(file_path)
            ]
            call_graph[name] = CallGraph(callers=callers, callees=callees)

        return symbol_defs, symbol_refs, call_graph

    async def _build_dependency_info(
        self,
        file_path: Path,
    ) -> tuple[list[ImportInfo], list[str], dict[str, str]]:
        """Build import/export information."""
        imports: list[ImportInfo] = []
        exports: list[str] = []
        alias_map: dict[str, str] = {}

        # Index the file in dependency graph (await to avoid race condition)
        await self.dep_graph.index_file(str(file_path))

        # Collect imports
        module_name = self.dep_graph._path_to_module.get(str(file_path), "")
        if module_name:
            node = self.dep_graph._modules.get(module_name)
            if node:
                for imp in node.imports:
                    imports.append(ImportInfo(
                        module=imp.module,
                        names=imp.names,
                        line=imp.line,
                        is_wildcard=imp.is_wildcard,
                        is_relative=imp.is_relative,
                        alias=imp.alias,
                    ))
                    # Build alias map
                    if imp.alias:
                        alias_map[imp.alias] = imp.names[0] if imp.names else imp.module
                    elif imp.names:
                        for name in imp.names:
                            if name != imp.module:
                                alias_map[name] = name

                # Collect exports
                exports = [e.name for e in node.exports]

        return imports, exports, alias_map

    def _build_chunks(
        self,
        ast_root: Optional[Any],
        content: str,
        language: str,
    ) -> list[CodeChunk]:
        """Build semantic code chunks from AST."""
        chunks: list[CodeChunk] = []
        lines = content.split("\n")

        # Build chunks from symbol definitions
        if isinstance(ast_root, list):
            for sym in ast_root:
                name = sym.get("name", "")
                sym_type = sym.get("type", "symbol")
                start = sym.get("line", 1)
                end = sym.get("end_line", start)

                chunk_type = "function" if "function" in sym_type else sym_type

                # Extract docstring if available
                docstring = ""
                if start > 1 and start <= len(lines):
                    # Check for docstring on next line(s)
                    doc_lines = []
                    for i in range(start, min(start + 5, len(lines) + 1)):
                        line = lines[i - 1].strip()
                        if line.startswith('"""') or line.startswith("'''"):
                            doc_lines.append(line.strip('"\'').strip())
                        elif doc_lines and not line:
                            break
                        elif doc_lines:
                            doc_lines.append(line)
                    docstring = " ".join(doc_lines[:3])

                chunks.append(CodeChunk(
                    start_line=start,
                    end_line=end,
                    chunk_type=chunk_type,
                    name=name,
                    docstring=docstring,
                ))

        return chunks

    def _build_file_state(self, file_path: Path, content: str) -> FileState:
        """Build file state for incremental analysis."""
        stat = file_path.stat()
        import hashlib
        content_hash = hashlib.md5(content.encode()).hexdigest()

        return FileState(
            mtime=stat.st_mtime,
            content_hash=content_hash,
            size_bytes=stat.st_size,
            line_count=len(content.splitlines()),
        )

    @staticmethod
    def _detect_language(path: Path) -> str:
        """Detect language from file extension."""
        ext = path.suffix.lower()
        mapping = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".jsx": "javascript",
            ".tsx": "typescript",
            ".c": "c",
            ".cpp": "cpp",
            ".cc": "cpp",
            ".h": "c",
            ".hpp": "cpp",
            ".rs": "rust",
            ".go": "go",
            ".java": "java",
        }
        return mapping.get(ext, "text")
