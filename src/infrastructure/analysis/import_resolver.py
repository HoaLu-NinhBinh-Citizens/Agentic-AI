"""Extended symbol extractor with dynamic import/alias handling.

Handles:
- import ... as ... (aliasing)
- from ... import ... as ... (selective aliasing)
- __all__ list for star imports
- Dynamic symbol resolution
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ImportInfo:
    """Information about an import statement."""

    # Raw import string
    raw_module: str
    raw_name: str

    # Resolved name (what the module/symbol is actually called)
    resolved_name: str

    # Alias (if used)
    alias: str | None = None

    # Import type
    import_type: str = "module"  # "module", "function", "class", "constant"

    # Source location
    line: int = 0
    file_path: str = ""


@dataclass
class AliasRegistry:
    """Registry for tracking import aliases."""

    # Module alias: original -> alias
    module_aliases: dict[str, str] = field(default_factory=dict)

    # Name alias: original_name -> (module, alias)
    name_aliases: dict[str, tuple[str, str]] = field(default_factory=dict)

    # Reverse lookup: alias -> original
    alias_to_original: dict[str, str] = field(default_factory=dict)

    def add_module_alias(self, original: str, alias: str, line: int = 0, file_path: str = "") -> None:
        """Register a module alias (import X as Y)."""
        self.module_aliases[original] = alias
        self.alias_to_original[alias] = original

    def add_name_alias(
        self,
        original: str,
        alias: str,
        module: str = "",
        line: int = 0,
        file_path: str = "",
    ) -> None:
        """Register a name alias (from X import Y as Z)."""
        self.name_aliases[original] = (module, alias)
        self.alias_to_original[alias] = original

    def resolve_module(self, name: str) -> str:
        """Resolve a module name, handling aliases."""
        if name in self.alias_to_original:
            return self.alias_to_original[name]
        if name in self.module_aliases:
            return name
        return name

    def resolve_name(self, name: str) -> tuple[str, str] | None:
        """Resolve a name, returning (module, resolved_name) or None."""
        if name in self.alias_to_original:
            original = self.alias_to_original[name]
            # Find the module this alias came from
            for module, alias in list(self.name_aliases.values()):
                if alias == name:
                    return (module, name)
            return ("", name)
        if name in self.name_aliases:
            module, alias = self.name_aliases[name]
            return (module, alias)
        return None

    def is_alias(self, name: str) -> bool:
        """Check if a name is an alias."""
        return name in self.alias_to_original

    def get_original(self, alias: str) -> str | None:
        """Get the original name for an alias."""
        return self.alias_to_original.get(alias)


class ImportExtractor:
    """Extract import information from source code."""

    def __init__(self, language: str = "python"):
        self.language = language
        self.aliases = AliasRegistry()
        self.imports: list[ImportInfo] = []
        self._star_import_modules: list[str] = []

    def reset(self) -> None:
        """Reset the extractor state."""
        self.aliases = AliasRegistry()
        self.imports = []
        self._star_import_modules = []

    def extract_imports(self, root: Any, source_bytes: bytes, file_path: str = "") -> list[ImportInfo]:
        """Extract import statements from AST.

        Handles:
        - import X
        - import X as Y
        - import X, Y
        - import X as Y, Z as W
        - from X import Y
        - from X import Y as Z
        - from X import *
        """
        self.reset()
        self._file_path = file_path
        self._extract_recursive(root, source_bytes)
        return self.imports

    def _extract_recursive(self, node: Any, source_bytes: bytes) -> None:
        """Recursively extract imports from AST."""
        if node is None:
            return

        node_type = node.type

        if node_type == "import_statement":
            self._handle_import_statement(node, source_bytes)
        elif node_type == "import_from_statement":
            self._handle_import_from_statement(node, source_bytes)
        elif node_type == "future_import_statement":
            self._handle_future_import(node, source_bytes)
        else:
            for child in node.children:
                self._extract_recursive(child, source_bytes)

    def _handle_import_statement(self, node: Any, source_bytes: bytes) -> None:
        """Handle: import X [as Y], ... statements."""
        line_no = node.start_point[0] + 1

        # Find all aliased_import nodes (import X as Y)
        for child in node.children:
            if child.type == "aliased_import":
                # Get module name from dotted_name
                dotted_name = None
                alias = None
                
                for subchild in child.children:
                    if subchild.type == "dotted_name":
                        dotted_name = subchild.text.decode("utf-8")
                    elif subchild.type == "identifier" and subchild.text.decode("utf-8") != "as":
                        if dotted_name is None:
                            dotted_name = subchild.text.decode("utf-8")
                        else:
                            alias = subchild.text.decode("utf-8")
                    elif subchild.type == "as":
                        # 'as' keyword, actual alias comes next
                        pass
                
                if dotted_name:
                    if alias:
                        self.aliases.add_module_alias(dotted_name, alias, line_no, self._file_path)

                    import_info = ImportInfo(
                        raw_module=dotted_name,
                        raw_name=dotted_name,
                        resolved_name=alias or dotted_name,
                        alias=alias,
                        import_type="module",
                        line=line_no,
                        file_path=self._file_path,
                    )
                    self.imports.append(import_info)
            
            elif child.type == "dotted_name":
                # Simple import without alias (e.g., "import os.path")
                original_name = child.text.decode("utf-8")
                import_info = ImportInfo(
                    raw_module=original_name,
                    raw_name=original_name,
                    resolved_name=original_name,
                    alias=None,
                    import_type="module",
                    line=line_no,
                    file_path=self._file_path,
                )
                self.imports.append(import_info)

    def _handle_import_from_statement(self, node: Any, source_bytes: bytes) -> None:
        """Handle: from X import Y [as Z], ... statements."""
        line_no = node.start_point[0] + 1

        # Get the source module
        module_name = ""
        for child in node.children:
            if child.type == "dotted_name":
                # This can be either the source module (in import_from_statement)
                # or the imported name
                # Check if we already found 'from' and 'import' keywords
                prev_siblings = node.children[:node.children.index(child)]
                if any(c.type == "import" for c in prev_siblings):
                    # This is the imported name (for simple from X import Y)
                    original_name = child.text.decode("utf-8")
                    import_info = ImportInfo(
                        raw_module=module_name,
                        raw_name=original_name,
                        resolved_name=original_name,
                        alias=None,
                        import_type=self._guess_import_type(original_name),
                        line=line_no,
                        file_path=self._file_path,
                    )
                    self.imports.append(import_info)
                else:
                    # This is the source module
                    module_name = child.text.decode("utf-8")
            elif child.type == "aliased_import":
                # from X import Y as Z
                original_name = ""
                alias = None
                
                for subchild in child.children:
                    if subchild.type == "dotted_name":
                        original_name = subchild.text.decode("utf-8")
                    elif subchild.type == "identifier" and subchild.text.decode("utf-8") != "as":
                        if not original_name:
                            original_name = subchild.text.decode("utf-8")
                        else:
                            alias = subchild.text.decode("utf-8")
                
                if original_name:
                    if alias:
                        self.aliases.add_name_alias(
                            original_name, alias, module_name, line_no, self._file_path
                        )

                    import_info = ImportInfo(
                        raw_module=module_name,
                        raw_name=original_name,
                        resolved_name=alias or original_name,
                        alias=alias,
                        import_type=self._guess_import_type(original_name),
                        line=line_no,
                        file_path=self._file_path,
                    )
                    self.imports.append(import_info)
                    
            elif child.type == "identifier" and child.text.decode("utf-8") != "from" and child.text.decode("utf-8") != "import":
                # Fallback: handle bare identifiers
                original_name = child.text.decode("utf-8")
                import_info = ImportInfo(
                    raw_module=module_name,
                    raw_name=original_name,
                    resolved_name=original_name,
                    alias=None,
                    import_type=self._guess_import_type(original_name),
                    line=line_no,
                    file_path=self._file_path,
                )
                self.imports.append(import_info)
            elif child.type == "wildcard_import":
                # from X import *
                self._star_import_modules.append(module_name)

    def _process_import_as_name(
        self, node: Any, module_name: str, line_no: int
    ) -> None:
        """Process an import_as_name node."""
        original_name = None
        alias = None

        for child in node.children:
            if child.type == "identifier":
                if original_name is None:
                    original_name = child.text.decode("utf-8")
                else:
                    # This shouldn't happen in a simple import
                    pass
            elif child.type == "dotted_name":
                if original_name is None:
                    original_name = child.text.decode("utf-8")
            elif child.type == "alias":
                alias_text = child.text.decode("utf-8")
                if " as " in alias_text:
                    parts = alias_text.split(" as ")
                    original_name = parts[0].strip()
                    alias = parts[1].strip()
                else:
                    alias = alias_text

        if original_name:
            if alias:
                self.aliases.add_name_alias(
                    original_name, alias, module_name, line_no, self._file_path
                )

            import_info = ImportInfo(
                raw_module=module_name,
                raw_name=original_name,
                resolved_name=alias or original_name,
                alias=alias,
                import_type=self._guess_import_type(original_name),
                line=line_no,
                file_path=self._file_path,
            )
            self.imports.append(import_info)

    def _handle_future_import(self, node: Any, source_bytes: bytes) -> None:
        """Handle: from __future__ import ... statements."""
        line_no = node.start_point[0] + 1

        # In future_import_statement, the structure is:
        # from __future__ import <name>
        # We need to find the identifier after 'import'
        found_import = False
        for child in node.children:
            if child.type == "import":
                found_import = True
            elif found_import and child.type in ("identifier", "dotted_name"):
                name = child.text.decode("utf-8")
                import_info = ImportInfo(
                    raw_module="__future__",
                    raw_name=name,
                    resolved_name=name,
                    import_type="future",
                    line=line_no,
                    file_path=self._file_path,
                )
                self.imports.append(import_info)
                break

    def _guess_import_type(self, name: str) -> str:
        """Guess the type of an imported name based on naming conventions."""
        # CamelCase -> likely class
        if name[0].isupper() and "_" not in name:
            return "class"
        # SCREAMING_CASE -> likely constant
        if name.isupper() and "_" in name:
            return "constant"
        # snake_case -> likely function or module
        return "function"


class AllExtractor:
    """Extract __all__ list for understanding star imports."""

    def __init__(self):
        self.exports: list[str] = []
        self._has_all = False

    def extract(self, root: Any, source_bytes: bytes) -> list[str]:
        """Extract __all__ exports from AST."""
        self.exports = []
        self._has_all = False
        self._search_recursive(root)
        return self.exports

    def _search_recursive(self, node: Any) -> None:
        """Search for __all__ assignment."""
        if node is None:
            return

        # Check for assignment to __all__
        if node.type == "assignment":
            left = node.child_by_field_name("left")
            if left and left.type == "identifier":
                name = left.text.decode("utf-8")
                if name == "__all__":
                    self._has_all = True
                    right = node.child_by_field_name("right")
                    if right:
                        self.exports = self._extract_list_items(right)

        # Continue searching
        for child in node.children:
            self._search_recursive(child)

    def _extract_list_items(self, node: Any) -> list[str]:
        """Extract string items from a list literal."""
        items = []

        def traverse(n: Any) -> None:
            if n.type == "string":
                text = n.text.decode("utf-8")
                # Remove quotes
                if text.startswith(("'", '"')):
                    text = text[1:-1]
                items.append(text)
            elif n.type == "list":
                for child in n.children:
                    traverse(child)
            elif n.type == "list_splat":
                # Skip list unpacking (e.g., __all__ = [..., *other])
                pass
            else:
                for child in n.children:
                    traverse(child)

        traverse(node)
        return items

    @property
    def has_all(self) -> bool:
        """Return True if __all__ was found in the file."""
        return self._has_all


def resolve_alias(
    symbol_name: str,
    imports: list[ImportInfo],
    aliases: AliasRegistry,
) -> str:
    """Resolve a symbol name considering aliases.

    Args:
        symbol_name: The symbol name as used in the code
        imports: List of import information
        aliases: Registry of aliases

    Returns:
        The resolved name (the name used in the code after aliasing)
    """
    # Check if it's an alias (we want to return the alias, not the original)
    if aliases.is_alias(symbol_name):
        # Return the alias as-is since that's what the code uses
        return symbol_name

    # Check name aliases - if symbol_name is an alias, return it
    resolved = aliases.resolve_name(symbol_name)
    if resolved:
        module, aliased_name = resolved
        return aliased_name

    return symbol_name


def build_import_graph(imports: list[ImportInfo]) -> dict[str, list[str]]:
    """Build a simple import graph from import information.

    Returns:
        Dict mapping file paths to lists of imported modules
    """
    graph: dict[str, list[str]] = {}

    for imp in imports:
        if imp.file_path:
            if imp.file_path not in graph:
                graph[imp.file_path] = []
            if imp.raw_module and imp.raw_module not in graph[imp.file_path]:
                graph[imp.file_path].append(imp.raw_module)

    return graph


# Standalone extraction functions for use without class instances


def extract_imports_standalone(
    content: str,
    language: str = "python",
    file_path: str = "",
) -> tuple[list[ImportInfo], AliasRegistry]:
    """Extract imports and build alias registry from source code.

    Args:
        content: Source code content
        language: Programming language
        file_path: Path to the source file

    Returns:
        Tuple of (import_info_list, alias_registry)
    """
    if language != "python":
        return [], AliasRegistry()

    try:
        import tree_sitter_languages

        parser = tree_sitter_languages.get_parser("python")
        source_bytes = content.encode("utf-8")
        tree = parser.parse(source_bytes)
        root = tree.root_node

        extractor = ImportExtractor(language)
        imports = extractor.extract_imports(root, source_bytes, file_path)

        return imports, extractor.aliases

    except ImportError:
        # Fallback: regex-based extraction
        return _extract_imports_regex(content), AliasRegistry()
    except Exception:
        return [], AliasRegistry()


def _extract_imports_regex(content: str) -> list[ImportInfo]:
    """Regex fallback for import extraction."""
    imports = []
    import re

    lines = content.split("\n")
    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        # import X as Y
        match = re.match(r"import\s+([\w.]+)(?:\s+as\s+(\w+))?", stripped)
        if match:
            original = match.group(1)
            alias = match.group(2)
            imports.append(ImportInfo(
                raw_module=original,
                raw_name=original,
                resolved_name=alias or original,
                alias=alias,
                import_type="module",
                line=i,
            ))

        # from X import Y [as Z]
        match = re.match(r"from\s+([\w.]+)\s+import\s+(.+)", stripped)
        if match:
            module = match.group(1)
            names_str = match.group(2)

            # Parse individual names
            for name_match in re.finditer(r"(\w+)(?:\s+as\s+(\w+))?", names_str):
                name = name_match.group(1)
                alias = name_match.group(2)
                imports.append(ImportInfo(
                    raw_module=module,
                    raw_name=name,
                    resolved_name=alias or name,
                    alias=alias,
                    import_type="function",
                    line=i,
                ))

    return imports
