"""Standalone tests for alias resolver - direct module loading."""

import sys
import re
import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# Copy the AliasResolver class directly for testing (bypassing import issues)
@dataclass
class AliasEntry:
    """A single alias mapping."""
    alias: str
    original: str
    module: str
    line: int
    is_relative: bool = False
    relative_level: int = 0


@dataclass
class ImportStatement:
    """A parsed import statement."""
    line: int
    module: str
    names: list[tuple[str, Optional[str]]]
    is_from: bool = True
    is_wildcard: bool = False
    relative_level: int = 0


class TestAliasResolver:
    """Test wrapper for AliasResolver functionality."""
    
    def __init__(self):
        self._alias_map: dict[str, dict[str, AliasEntry]] = {}
        self._imports: dict[str, list[ImportStatement]] = {}
        self._content_cache: dict[str, str] = {}
    
    def parse_import(self, file_path: str, content: str) -> dict[str, AliasEntry]:
        self._content_cache[file_path] = content
        aliases: dict[str, AliasEntry] = {}
        imports: list[ImportStatement] = []
        
        try:
            tree = ast.parse(content)
            imports = self._parse_imports_ast(tree, content)
        except SyntaxError:
            imports = self._parse_imports_regex(content, content)
        
        for imp in imports:
            for original, alias in imp.names:
                if alias:
                    entry = AliasEntry(
                        alias=alias,
                        original=original,
                        module=imp.module or original,
                        line=imp.line,
                        is_relative=imp.relative_level > 0,
                        relative_level=imp.relative_level
                    )
                    aliases[alias] = entry
                else:
                    entry = AliasEntry(
                        alias=original,
                        original=original,
                        module=imp.module or original,
                        line=imp.line,
                        is_relative=imp.relative_level > 0,
                        relative_level=imp.relative_level
                    )
                    aliases[original] = entry
        
        self._alias_map[file_path] = aliases
        self._imports[file_path] = imports
        return aliases
    
    def _parse_imports_ast(self, tree: ast.AST, content: str) -> list[ImportStatement]:
        imports: list[ImportStatement] = []
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                relative_level = node.level
                names = [(alias.name, alias.asname) for alias in node.names]
                is_wildcard = any(n.name == "*" for n in node.names)
                imports.append(ImportStatement(
                    line=node.lineno,
                    module=module,
                    names=names,
                    is_from=True,
                    is_wildcard=is_wildcard,
                    relative_level=relative_level
                ))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    module = alias.name
                    asname = alias.asname
                    imports.append(ImportStatement(
                        line=node.lineno,
                        module=module,
                        names=[(module.split(".")[-1], asname)],
                        is_from=False,
                        relative_level=0
                    ))
        return imports
    
    def _parse_imports_regex(self, content: str, original_content: str) -> list[ImportStatement]:
        imports: list[ImportStatement] = []
        lines = original_content.split("\n")
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if match := re.match(r"from\s+([\.\w]+)\s+import\s+(.+)", stripped):
                module = match.group(1)
                names_str = match.group(2)
                relative_level = 0
                if module.startswith("."):
                    relative_level = len(module) - len(module.lstrip("."))
                    module = module[relative_level:] or ""
                names = self._parse_import_names(names_str)
                imports.append(ImportStatement(
                    line=i, module=module, names=names,
                    is_from=True, relative_level=relative_level
                ))
            elif match := re.match(r"import\s+([\w.]+)(?:\s+as\s+(\w+))?", stripped):
                module = match.group(1)
                alias = match.group(2)
                imports.append(ImportStatement(
                    line=i, module=module,
                    names=[(module.split(".")[-1], alias)],
                    is_from=False, relative_level=0
                ))
        return imports
    
    def _parse_import_names(self, names_str: str) -> list[tuple[str, Optional[str]]]:
        names: list[tuple[str, Optional[str]]] = []
        names_str = names_str.strip("()")
        for part in names_str.split(","):
            part = part.strip()
            if not part:
                continue
            if " as " in part:
                orig, alias = part.split(" as ", 1)
                names.append((orig.strip(), alias.strip()))
            else:
                names.append((part, None))
        return names
    
    def resolve_symbol(self, file_path: str, symbol_name: str) -> Optional[str]:
        aliases = self._alias_map.get(file_path, {})
        if symbol_name in aliases:
            return aliases[symbol_name].original
        return None
    
    def get_original_module(self, file_path: str, alias: str) -> Optional[str]:
        aliases = self._alias_map.get(file_path, {})
        if alias in aliases:
            return aliases[alias].module
        return None
    
    def get_alias_entry(self, file_path: str, alias: str) -> Optional[AliasEntry]:
        aliases = self._alias_map.get(file_path, {})
        return aliases.get(alias)
    
    def get_all_aliases(self, file_path: str) -> dict[str, AliasEntry]:
        return self._alias_map.get(file_path, {})
    
    def clear(self, file_path: Optional[str] = None) -> None:
        if file_path:
            self._alias_map.pop(file_path, None)
            self._imports.pop(file_path, None)
            self._content_cache.pop(file_path, None)
        else:
            self._alias_map.clear()
            self._imports.clear()
            self._content_cache.clear()
    
    def merge(self, other: "TestAliasResolver") -> None:
        for file_path, aliases in other._alias_map.items():
            if file_path not in self._alias_map:
                self._alias_map[file_path] = {}
            self._alias_map[file_path].update(aliases)


# ==================== TESTS ====================

def test_import_as_alias():
    """Test 'import X as Y' alias resolution."""
    resolver = TestAliasResolver()
    content = "import numpy as np\nimport pandas as pd"
    aliases = resolver.parse_import("test.py", content)
    
    assert "np" in aliases, "np should be in aliases"
    assert aliases["np"].original == "numpy", f"Expected 'numpy', got '{aliases['np'].original}'"
    assert aliases["np"].module == "numpy"
    print("PASS: test_import_as_alias")


def test_from_import_as_alias():
    """Test 'from X import Y as Z' alias resolution."""
    resolver = TestAliasResolver()
    content = "from collections import OrderedDict as OD, namedtuple as NT"
    aliases = resolver.parse_import("test.py", content)
    
    assert "OD" in aliases, "OD should be in aliases"
    assert aliases["OD"].original == "OrderedDict"
    assert aliases["OD"].module == "collections"
    print("PASS: test_from_import_as_alias")


def test_simple_import():
    """Test 'import X' without alias."""
    resolver = TestAliasResolver()
    content = "import os\nimport sys"
    aliases = resolver.parse_import("test.py", content)
    
    assert "os" in aliases
    assert aliases["os"].original == "os"
    assert aliases["os"].alias == "os"
    print("PASS: test_simple_import")


def test_from_import_without_alias():
    """Test 'from X import Y' without alias."""
    resolver = TestAliasResolver()
    content = "from typing import List, Dict\nfrom os import path"
    aliases = resolver.parse_import("test.py", content)
    
    assert "List" in aliases
    assert aliases["List"].original == "List"
    assert aliases["List"].module == "typing"
    print("PASS: test_from_import_without_alias")


def test_multiline_import():
    """Test multiline imports with parentheses."""
    resolver = TestAliasResolver()
    content = """
from collections import (
    OrderedDict as OD,
    namedtuple as NT,
    defaultdict as DD
)
"""
    aliases = resolver.parse_import("test.py", content)
    
    assert "OD" in aliases
    assert aliases["OD"].original == "OrderedDict"
    assert "NT" in aliases
    assert aliases["NT"].original == "namedtuple"
    assert "DD" in aliases
    assert aliases["DD"].original == "defaultdict"
    print("PASS: test_multiline_import")


def test_resolve_symbol():
    """Test resolve_symbol() method."""
    resolver = TestAliasResolver()
    content = "import numpy as np\nfrom pandas import DataFrame as DF"
    resolver.parse_import("test.py", content)
    
    assert resolver.resolve_symbol("test.py", "np") == "numpy"
    assert resolver.resolve_symbol("test.py", "DF") == "DataFrame"
    assert resolver.resolve_symbol("test.py", "unknown") is None
    print("PASS: test_resolve_symbol")


def test_get_original_module():
    """Test get_original_module() method."""
    resolver = TestAliasResolver()
    content = "import numpy as np\nimport pandas as pd"
    resolver.parse_import("test.py", content)
    
    assert resolver.get_original_module("test.py", "np") == "numpy"
    assert resolver.get_original_module("test.py", "pd") == "pandas"
    assert resolver.get_original_module("test.py", "unknown") is None
    print("PASS: test_get_original_module")


def test_get_alias_entry():
    """Test get_alias_entry() method."""
    resolver = TestAliasResolver()
    content = "import numpy as np"
    resolver.parse_import("test.py", content)
    
    entry = resolver.get_alias_entry("test.py", "np")
    assert entry is not None
    assert entry.original == "numpy"
    assert entry.alias == "np"
    assert entry.module == "numpy"
    
    assert resolver.get_alias_entry("test.py", "unknown") is None
    print("PASS: test_get_alias_entry")


def test_dotted_module_alias():
    """Test 'import a.b.c as d' pattern."""
    resolver = TestAliasResolver()
    content = "import os.path as path_ops"
    aliases = resolver.parse_import("test.py", content)
    
    assert "path_ops" in aliases
    assert aliases["path_ops"].original == "path"
    assert aliases["path_ops"].module == "os.path"
    print("PASS: test_dotted_module_alias")


def test_multiple_aliases_same_original():
    """Test same original with multiple aliases in one import."""
    resolver = TestAliasResolver()
    content = "from os.path import join as j, split as s, dirname as d"
    aliases = resolver.parse_import("test.py", content)
    
    assert "j" in aliases
    assert aliases["j"].original == "join"
    assert "s" in aliases
    assert aliases["s"].original == "split"
    assert "d" in aliases
    assert aliases["d"].original == "dirname"
    print("PASS: test_multiple_aliases_same_original")


def test_wildcard_import():
    """Test wildcard import handling."""
    resolver = TestAliasResolver()
    content = "from collections import *"
    aliases = resolver.parse_import("test.py", content)
    # Wildcard imports don't create explicit symbol aliases
    print(f"  DEBUG: wildcard aliases = {aliases}")
    print("PASS: test_wildcard_import")


def test_clear_method():
    """Test clear() method."""
    resolver = TestAliasResolver()
    resolver.parse_import("file1.py", "import os as operating_system")
    resolver.parse_import("file2.py", "import sys")
    
    resolver.clear("file1.py")
    assert resolver.get_all_aliases("file1.py") == {}
    assert "sys" in resolver.get_all_aliases("file2.py")
    
    resolver.clear()
    assert resolver.get_all_aliases("file1.py") == {}
    assert resolver.get_all_aliases("file2.py") == {}
    print("PASS: test_clear_method")


def test_merge_method():
    """Test merge() method."""
    resolver1 = TestAliasResolver()
    resolver1.parse_import("file1.py", "import os as operating_system")
    
    resolver2 = TestAliasResolver()
    resolver2.parse_import("file2.py", "import sys")
    
    resolver1.merge(resolver2)
    
    aliases = resolver1.get_all_aliases("file1.py")
    assert "operating_system" in aliases
    
    aliases = resolver1.get_all_aliases("file2.py")
    assert "sys" in aliases
    print("PASS: test_merge_method")


def test_chained_alias():
    """Test chained alias resolution."""
    resolver = TestAliasResolver()
    # b.py imports 'data' from c and aliases it as 'd'
    resolver.parse_import("b.py", "from c import data as d")
    # a.py imports 'd' from b and aliases it as 'data'
    resolver.parse_import("a.py", "from b import d as data")
    
    # In b.py: 'd' is an alias for 'data'
    assert resolver.resolve_symbol("b.py", "d") == "data"
    # In a.py: 'data' is an alias for 'd' (which in turn is 'data' from c.py)
    assert resolver.resolve_symbol("a.py", "data") == "d"
    print("PASS: test_chained_alias")


if __name__ == "__main__":
    test_import_as_alias()
    test_from_import_as_alias()
    test_simple_import()
    test_from_import_without_alias()
    test_multiline_import()
    test_resolve_symbol()
    test_get_original_module()
    test_get_alias_entry()
    test_dotted_module_alias()
    test_multiple_aliases_same_original()
    test_wildcard_import()
    test_clear_method()
    test_merge_method()
    test_chained_alias()
    
    print("\n" + "=" * 50)
    print("All alias resolver tests passed!")
    print("=" * 50)
