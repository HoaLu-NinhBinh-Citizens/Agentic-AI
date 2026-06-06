"""Cross-language semantic linker for multi-language projects.

Links symbols and contracts across language boundaries:
- Python ↔ TypeScript (API contracts, shared schemas)
- Python ↔ C (ctypes, CFFI bindings)
- Config files (YAML, JSON) → code that consumes them
- OpenAPI/GraphQL specs → implementation code

This enables understanding of multi-language codebases
where a change in one language can affect another.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ─── Data Types ──────────────────────────────────────────────────────────────


@dataclass
class CrossLanguageSymbol:
    """A symbol that exists across language boundaries."""

    name: str
    language: str  # "python", "typescript", "c", "yaml", "json"
    file_path: str
    line: int
    kind: str  # "function", "class", "type", "config_key", "api_endpoint"
    signature: str = ""
    doc: str = ""


@dataclass
class CrossLanguageLink:
    """A semantic link between symbols in different languages."""

    source: CrossLanguageSymbol
    target: CrossLanguageSymbol
    link_type: str  # "implements", "calls", "consumes", "defines", "mirrors"
    confidence: float = 0.8
    evidence: str = ""  # Why this link was established


@dataclass
class ConfigReference:
    """A reference from code to a configuration key."""

    config_file: str
    config_key: str
    code_file: str
    code_line: int
    language: str
    access_pattern: str  # e.g., "config['key']", "os.environ['KEY']"


@dataclass
class APIContract:
    """An API contract (endpoint, schema) shared between languages."""

    path: str  # e.g., "/api/users"
    method: str  # "GET", "POST", etc.
    request_schema: dict = field(default_factory=dict)
    response_schema: dict = field(default_factory=dict)
    defined_in: str = ""  # File where the contract is defined
    implemented_in: list[str] = field(default_factory=list)


# ─── Linker Engine ───────────────────────────────────────────────────────────


class CrossLanguageLinker:
    """Discover and maintain semantic links across language boundaries.

    Scans a multi-language project to find:
    1. Shared type definitions (TypeScript interfaces → Python dataclasses)
    2. FFI bindings (ctypes/CFFI → C functions)
    3. Config consumption (YAML/JSON keys → code references)
    4. API contracts (OpenAPI → server/client implementations)
    """

    # Patterns for detecting cross-language references
    CTYPES_PATTERN = re.compile(
        r'(?:cdll|windll|CDLL)\s*[\.\(]\s*["\']([^"\']+)["\']'
    )
    CFFI_PATTERN = re.compile(
        r'ffi\.(?:dlopen|cdef)\s*\(\s*["\']([^"\']+)["\']'
    )
    CONFIG_ACCESS_PATTERNS = {
        "python": [
            re.compile(r'config\[[\"\'](\w[\w\.]*)[\"\']\]'),
            re.compile(r'config\.get\(["\'](\w[\w\.]*)["\']'),
            re.compile(r'os\.environ\[[\"\'](\w+)[\"\']\]'),
            re.compile(r'os\.getenv\(["\'](\w+)["\']'),
            re.compile(r'settings\.(\w+)'),
        ],
        "typescript": [
            re.compile(r'process\.env\.(\w+)'),
            re.compile(r'config\[[\"\'](\w[\w\.]*)[\"\']\]'),
            re.compile(r'config\.(\w+)'),
        ],
    }

    def __init__(self) -> None:
        self._symbols: dict[str, list[CrossLanguageSymbol]] = {}
        self._links: list[CrossLanguageLink] = []
        self._config_refs: list[ConfigReference] = []
        self._api_contracts: list[APIContract] = []
        self._indexed_files: set[str] = set()

    @property
    def links(self) -> list[CrossLanguageLink]:
        """All discovered cross-language links."""
        return self._links

    @property
    def config_references(self) -> list[ConfigReference]:
        """All config key references found in code."""
        return self._config_refs

    def index_file(self, file_path: Path, content: str) -> None:
        """Index a file for cross-language symbols.

        Args:
            file_path: Path to the source file
            content: File content
        """
        file_str = str(file_path)
        lang = self._detect_language(file_path)

        if lang == "python":
            self._index_python_file(file_path, content)
        elif lang == "typescript":
            self._index_typescript_file(file_path, content)
        elif lang == "c":
            self._index_c_file(file_path, content)
        elif lang in ("yaml", "json"):
            self._index_config_file(file_path, content, lang)

        self._indexed_files.add(file_str)

    def index_directory(self, root: Path, extensions: set[str] | None = None) -> int:
        """Index all relevant files in a directory tree.

        Args:
            root: Root directory to scan
            extensions: File extensions to include (None = all supported)

        Returns:
            Number of files indexed
        """
        supported = extensions or {
            ".py", ".ts", ".tsx", ".js", ".c", ".h",
            ".yaml", ".yml", ".json",
        }
        count = 0

        for path in root.rglob("*"):
            if path.suffix in supported and path.is_file():
                # Skip node_modules, __pycache__, .git
                parts = path.parts
                if any(p in ("node_modules", "__pycache__", ".git", "venv") for p in parts):
                    continue
                try:
                    content = path.read_text(encoding="utf-8", errors="replace")
                    self.index_file(path, content)
                    count += 1
                except (OSError, UnicodeDecodeError):
                    continue

        return count

    def find_links(self) -> list[CrossLanguageLink]:
        """Discover all cross-language links from indexed symbols.

        Runs matching algorithms to find:
        - Name-based matches (same symbol name across languages)
        - FFI bindings (Python ctypes → C functions)
        - Type mirrors (TS interface → Python dataclass)
        - Config consumers (code → config keys)

        Returns:
            List of discovered links
        """
        self._links = []

        self._link_by_name_matching()
        self._link_ffi_bindings()
        self._link_config_references()

        return self._links

    def get_links_for_symbol(self, name: str) -> list[CrossLanguageLink]:
        """Get all cross-language links involving a symbol name.

        Args:
            name: Symbol name to search for

        Returns:
            Links where this symbol is source or target
        """
        return [
            link for link in self._links
            if link.source.name == name or link.target.name == name
        ]

    def get_config_consumers(self, config_key: str) -> list[ConfigReference]:
        """Find all code locations that consume a config key.

        Args:
            config_key: The configuration key to search for

        Returns:
            List of ConfigReference objects
        """
        return [ref for ref in self._config_refs if ref.config_key == config_key]

    def get_symbols_in_file(self, file_path: str) -> list[CrossLanguageSymbol]:
        """Get all cross-language symbols defined in a file."""
        return self._symbols.get(file_path, [])

    # ─── Private: Indexing ───────────────────────────────────────────────────

    def _index_python_file(self, file_path: Path, content: str) -> None:
        """Index Python file for exportable symbols and FFI references."""
        import ast as _ast

        file_str = str(file_path)
        symbols: list[CrossLanguageSymbol] = []

        try:
            tree = _ast.parse(content)
        except SyntaxError:
            return

        for node in _ast.walk(tree):
            if isinstance(node, _ast.ClassDef):
                symbols.append(CrossLanguageSymbol(
                    name=node.name,
                    language="python",
                    file_path=file_str,
                    line=node.lineno,
                    kind="class",
                    signature=self._python_class_signature(node),
                ))
            elif isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                # Only top-level or exported functions
                symbols.append(CrossLanguageSymbol(
                    name=node.name,
                    language="python",
                    file_path=file_str,
                    line=node.lineno,
                    kind="function",
                    signature=self._python_func_signature(node),
                ))

        # Find ctypes/cffi references
        for match in self.CTYPES_PATTERN.finditer(content):
            symbols.append(CrossLanguageSymbol(
                name=match.group(1),
                language="python",
                file_path=file_str,
                line=content[:match.start()].count("\n") + 1,
                kind="ffi_library",
            ))

        for match in self.CFFI_PATTERN.finditer(content):
            symbols.append(CrossLanguageSymbol(
                name=match.group(1),
                language="python",
                file_path=file_str,
                line=content[:match.start()].count("\n") + 1,
                kind="ffi_library",
            ))

        # Find config access patterns
        self._extract_config_refs(file_path, content, "python")

        self._symbols[file_str] = symbols

    def _index_typescript_file(self, file_path: Path, content: str) -> None:
        """Index TypeScript file for interfaces, types, and exports."""
        file_str = str(file_path)
        symbols: list[CrossLanguageSymbol] = []

        # Interface definitions
        for match in re.finditer(
            r'(?:export\s+)?interface\s+(\w+)\s*(?:extends\s+[\w,\s]+)?\s*\{',
            content,
        ):
            line = content[:match.start()].count("\n") + 1
            symbols.append(CrossLanguageSymbol(
                name=match.group(1),
                language="typescript",
                file_path=file_str,
                line=line,
                kind="interface",
            ))

        # Type aliases
        for match in re.finditer(
            r'(?:export\s+)?type\s+(\w+)\s*=',
            content,
        ):
            line = content[:match.start()].count("\n") + 1
            symbols.append(CrossLanguageSymbol(
                name=match.group(1),
                language="typescript",
                file_path=file_str,
                line=line,
                kind="type",
            ))

        # Exported functions
        for match in re.finditer(
            r'(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(',
            content,
        ):
            line = content[:match.start()].count("\n") + 1
            symbols.append(CrossLanguageSymbol(
                name=match.group(1),
                language="typescript",
                file_path=file_str,
                line=line,
                kind="function",
            ))

        # API route definitions (Express/Fastify style)
        for match in re.finditer(
            r'(?:app|router)\.(get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)["\']',
            content,
        ):
            line = content[:match.start()].count("\n") + 1
            method = match.group(1).upper()
            path = match.group(2)
            symbols.append(CrossLanguageSymbol(
                name=f"{method} {path}",
                language="typescript",
                file_path=file_str,
                line=line,
                kind="api_endpoint",
            ))

        self._extract_config_refs(file_path, content, "typescript")
        self._symbols[file_str] = symbols

    def _index_c_file(self, file_path: Path, content: str) -> None:
        """Index C/C++ file for function declarations."""
        file_str = str(file_path)
        symbols: list[CrossLanguageSymbol] = []

        # Function declarations/definitions
        # Pattern: return_type function_name(params)
        func_pattern = re.compile(
            r'^(?:extern\s+)?(?:static\s+)?'
            r'(?:inline\s+)?'
            r'(\w[\w\s\*]*?)\s+(\w+)\s*\(([^)]*)\)\s*[{;]',
            re.MULTILINE,
        )

        for match in func_pattern.finditer(content):
            return_type = match.group(1).strip()
            name = match.group(2)
            params = match.group(3).strip()
            line = content[:match.start()].count("\n") + 1

            # Skip common macros and keywords
            if name in ("if", "while", "for", "switch", "return"):
                continue

            symbols.append(CrossLanguageSymbol(
                name=name,
                language="c",
                file_path=file_str,
                line=line,
                kind="function",
                signature=f"{return_type} {name}({params})",
            ))

        # Struct/enum definitions
        for match in re.finditer(
            r'typedef\s+(?:struct|enum)\s*(?:\w+\s*)?\{[^}]*\}\s*(\w+)\s*;',
            content,
            re.DOTALL,
        ):
            line = content[:match.start()].count("\n") + 1
            symbols.append(CrossLanguageSymbol(
                name=match.group(1),
                language="c",
                file_path=file_str,
                line=line,
                kind="type",
            ))

        self._symbols[file_str] = symbols

    def _index_config_file(
        self, file_path: Path, content: str, lang: str
    ) -> None:
        """Index config file (YAML/JSON) keys as symbols."""
        file_str = str(file_path)
        symbols: list[CrossLanguageSymbol] = []

        if lang == "json":
            try:
                data = json.loads(content)
                self._extract_json_keys(data, "", file_str, symbols)
            except json.JSONDecodeError:
                pass
        elif lang == "yaml":
            # Simple YAML key extraction without pyyaml dependency
            self._extract_yaml_keys(content, file_str, symbols)

        self._symbols[file_str] = symbols

    def _extract_json_keys(
        self,
        data: dict | list,
        prefix: str,
        file_str: str,
        symbols: list[CrossLanguageSymbol],
        depth: int = 0,
    ) -> None:
        """Recursively extract JSON keys as symbols."""
        if depth > 5:
            return

        if isinstance(data, dict):
            for key, value in data.items():
                full_key = f"{prefix}.{key}" if prefix else key
                symbols.append(CrossLanguageSymbol(
                    name=full_key,
                    language="json",
                    file_path=file_str,
                    line=0,
                    kind="config_key",
                ))
                if isinstance(value, (dict, list)):
                    self._extract_json_keys(value, full_key, file_str, symbols, depth + 1)

    def _extract_yaml_keys(
        self, content: str, file_str: str, symbols: list[CrossLanguageSymbol]
    ) -> None:
        """Extract top-level YAML keys (simple parser without pyyaml)."""
        for i, line in enumerate(content.split("\n"), 1):
            # Match unindented keys: "key:" or "key: value"
            match = re.match(r'^(\w[\w\-]*)\s*:', line)
            if match:
                symbols.append(CrossLanguageSymbol(
                    name=match.group(1),
                    language="yaml",
                    file_path=file_str,
                    line=i,
                    kind="config_key",
                ))

    def _extract_config_refs(
        self, file_path: Path, content: str, language: str
    ) -> None:
        """Find config key references in source code."""
        patterns = self.CONFIG_ACCESS_PATTERNS.get(language, [])

        for pattern in patterns:
            for match in pattern.finditer(content):
                line = content[:match.start()].count("\n") + 1
                self._config_refs.append(ConfigReference(
                    config_file="",  # Resolved during linking
                    config_key=match.group(1),
                    code_file=str(file_path),
                    code_line=line,
                    language=language,
                    access_pattern=match.group(0),
                ))

    # ─── Private: Linking ────────────────────────────────────────────────────

    def _link_by_name_matching(self) -> None:
        """Link symbols with the same name across languages."""
        # Group symbols by name
        name_index: dict[str, list[CrossLanguageSymbol]] = {}
        for symbols in self._symbols.values():
            for sym in symbols:
                # Normalize name for matching
                normalized = self._normalize_name(sym.name)
                if normalized not in name_index:
                    name_index[normalized] = []
                name_index[normalized].append(sym)

        # Find cross-language matches
        for name, symbols in name_index.items():
            languages = set(s.language for s in symbols)
            if len(languages) > 1:
                # Cross-language match found
                for i, src in enumerate(symbols):
                    for tgt in symbols[i + 1:]:
                        if src.language != tgt.language:
                            link_type = self._determine_link_type(src, tgt)
                            self._links.append(CrossLanguageLink(
                                source=src,
                                target=tgt,
                                link_type=link_type,
                                confidence=0.7,
                                evidence=f"Name match: '{src.name}' ({src.language}) ↔ '{tgt.name}' ({tgt.language})",
                            ))

    def _link_ffi_bindings(self) -> None:
        """Link Python FFI references to C function definitions."""
        # Collect all C functions
        c_functions: dict[str, CrossLanguageSymbol] = {}
        for symbols in self._symbols.values():
            for sym in symbols:
                if sym.language == "c" and sym.kind == "function":
                    c_functions[sym.name] = sym

        # Find Python FFI references and link to C
        for symbols in self._symbols.values():
            for sym in symbols:
                if sym.language == "python" and sym.kind == "ffi_library":
                    # The library name might match C file names
                    lib_name = Path(sym.name).stem
                    for c_name, c_sym in c_functions.items():
                        if lib_name in c_sym.file_path:
                            self._links.append(CrossLanguageLink(
                                source=sym,
                                target=c_sym,
                                link_type="calls",
                                confidence=0.75,
                                evidence=f"FFI library '{sym.name}' likely contains '{c_name}'",
                            ))

    def _link_config_references(self) -> None:
        """Link config references in code to config file definitions."""
        # Collect all config keys from config files
        config_keys: dict[str, CrossLanguageSymbol] = {}
        for symbols in self._symbols.values():
            for sym in symbols:
                if sym.kind == "config_key":
                    config_keys[sym.name] = sym

        # Match code references to config definitions
        for ref in self._config_refs:
            if ref.config_key in config_keys:
                cfg_sym = config_keys[ref.config_key]
                ref.config_file = cfg_sym.file_path

                code_sym = CrossLanguageSymbol(
                    name=ref.config_key,
                    language=ref.language,
                    file_path=ref.code_file,
                    line=ref.code_line,
                    kind="config_consumer",
                )

                self._links.append(CrossLanguageLink(
                    source=code_sym,
                    target=cfg_sym,
                    link_type="consumes",
                    confidence=0.9,
                    evidence=f"Code accesses config key '{ref.config_key}' via '{ref.access_pattern}'",
                ))

    # ─── Private: Utilities ──────────────────────────────────────────────────

    def _detect_language(self, file_path: Path) -> str:
        """Detect language from file extension."""
        ext_map = {
            ".py": "python",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".js": "javascript",
            ".jsx": "javascript",
            ".c": "c",
            ".h": "c",
            ".cpp": "c",
            ".hpp": "c",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".json": "json",
        }
        return ext_map.get(file_path.suffix.lower(), "unknown")

    def _normalize_name(self, name: str) -> str:
        """Normalize symbol name for cross-language matching.

        Converts PascalCase, camelCase, snake_case to a common form.
        """
        # Convert camelCase/PascalCase to snake_case
        s1 = re.sub(r'(.)([A-Z][a-z]+)', r'\1_\2', name)
        result = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', s1).lower()
        # Remove common prefixes/suffixes
        result = re.sub(r'^(i_|t_|e_)', '', result)
        return result

    def _determine_link_type(
        self, src: CrossLanguageSymbol, tgt: CrossLanguageSymbol
    ) -> str:
        """Determine the relationship type between two symbols."""
        # TypeScript interface → Python class = "mirrors"
        if (
            (src.kind == "interface" and tgt.kind == "class")
            or (src.kind == "class" and tgt.kind == "interface")
        ):
            return "mirrors"

        # Same kind across languages = "mirrors"
        if src.kind == tgt.kind:
            return "mirrors"

        # One is a type, other is implementation
        if src.kind == "type" or tgt.kind == "type":
            return "defines"

        return "related"

    def _python_class_signature(self, node) -> str:
        """Get a brief class signature."""
        import ast as _ast
        bases = []
        for base in node.bases:
            if isinstance(base, _ast.Name):
                bases.append(base.id)
        if bases:
            return f"class {node.name}({', '.join(bases)})"
        return f"class {node.name}"

    def _python_func_signature(self, node) -> str:
        """Get a brief function signature."""
        import ast as _ast
        args = [arg.arg for arg in node.args.args]
        return f"def {node.name}({', '.join(args)})"
