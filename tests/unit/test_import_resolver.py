"""Tests for dynamic import/alias handling."""

from __future__ import annotations

import pytest

from src.infrastructure.analysis.import_resolver import (
    AliasRegistry,
    ImportExtractor,
    AllExtractor,
    extract_imports_standalone,
    resolve_alias,
    ImportInfo,
)


class TestAliasRegistry:
    """Tests for the AliasRegistry class."""

    def test_add_module_alias(self):
        """Test registering a module alias."""
        registry = AliasRegistry()
        registry.add_module_alias("numpy", "np", 10, "test.py")

        assert registry.module_aliases["numpy"] == "np"
        assert registry.alias_to_original["np"] == "numpy"
        assert registry.is_alias("np")
        assert registry.is_alias("numpy") is False

    def test_add_name_alias(self):
        """Test registering a name alias."""
        registry = AliasRegistry()
        registry.add_name_alias("some_function", "sf", "mymodule", 20, "test.py")

        assert registry.name_aliases["some_function"] == ("mymodule", "sf")
        assert registry.alias_to_original["sf"] == "some_function"

    def test_resolve_module(self):
        """Test resolving a module name."""
        registry = AliasRegistry()
        registry.add_module_alias("pandas", "pd", 10, "test.py")

        assert registry.resolve_module("pd") == "pandas"
        assert registry.resolve_module("pandas") == "pandas"

    def test_resolve_name(self):
        """Test resolving a name."""
        registry = AliasRegistry()
        registry.add_name_alias("get_data", "gd", "mymodule", 10, "test.py")

        result = registry.resolve_name("gd")
        assert result == ("mymodule", "gd")

    def test_get_original(self):
        """Test getting original name from alias."""
        registry = AliasRegistry()
        registry.add_module_alias("collections", "col", 10, "test.py")

        assert registry.get_original("col") == "collections"
        assert registry.get_original("unknown") is None


class TestImportExtractor:
    """Tests for the ImportExtractor class."""

    def test_simple_import(self):
        """Test extracting simple import."""
        content = 'import numpy\n'

        imports, aliases = extract_imports_standalone(content, "python", "test.py")

        assert len(imports) == 1
        assert imports[0].raw_module == "numpy"
        assert imports[0].resolved_name == "numpy"

    def test_alias_import(self):
        """Test extracting import with alias."""
        content = 'import numpy as np\n'

        imports, aliases = extract_imports_standalone(content, "python", "test.py")

        assert len(imports) == 1
        assert imports[0].raw_module == "numpy"
        assert imports[0].resolved_name == "np"
        assert imports[0].alias == "np"
        assert aliases.is_alias("np")

    def test_from_import(self):
        """Test extracting from...import."""
        content = 'from os import path\n'

        imports, aliases = extract_imports_standalone(content, "python", "test.py")

        assert len(imports) == 1
        assert imports[0].raw_module == "os"
        assert imports[0].raw_name == "path"
        assert imports[0].resolved_name == "path"

    def test_from_import_with_alias(self):
        """Test extracting from...import...as."""
        content = 'from os.path import join as path_join\n'

        imports, aliases = extract_imports_standalone(content, "python", "test.py")

        assert len(imports) == 1
        assert imports[0].raw_module == "os.path"
        assert imports[0].raw_name == "join"
        assert imports[0].resolved_name == "path_join"
        assert imports[0].alias == "path_join"

    def test_multiple_imports(self):
        """Test extracting multiple imports."""
        content = 'import os, sys, json\n'

        imports, _ = extract_imports_standalone(content, "python", "test.py")

        assert len(imports) == 3
        module_names = {imp.resolved_name for imp in imports}
        assert module_names == {"os", "sys", "json"}

    def test_from_import_multiple(self):
        """Test extracting multiple from imports."""
        content = 'from collections import OrderedDict, defaultdict, namedtuple\n'

        imports, _ = extract_imports_standalone(content, "python", "test.py")

        assert len(imports) == 3
        names = {imp.resolved_name for imp in imports}
        assert names == {"OrderedDict", "defaultdict", "namedtuple"}

    def test_star_import(self):
        """Test extracting star import."""
        content = 'from dataclasses import *\n'

        imports, _ = extract_imports_standalone(content, "python", "test.py")

        # Star imports don't give us specific names
        assert len(imports) == 0  # No specific names extracted

    def test_relative_import(self):
        """Test extracting relative imports."""
        content = 'from . import utils\nfrom .. import config\n'

        imports, _ = extract_imports_standalone(content, "python", "test.py")

        # Relative imports should be handled
        assert len(imports) >= 1

    def test_future_import(self):
        """Test extracting __future__ imports."""
        content = 'from __future__ import annotations\n'

        imports, _ = extract_imports_standalone(content, "python", "test.py")

        # __future__ imports are tracked
        assert any(imp.raw_module == "__future__" for imp in imports)


class TestAllExtractor:
    """Tests for the AllExtractor class."""

    def test_extract_simple_all(self):
        """Test extracting simple __all__ list."""
        content = '''
__all__ = ["func1", "func2", "MyClass"]
'''

        try:
            import tree_sitter_languages
            parser = tree_sitter_languages.get_parser("python")
            tree = parser.parse(content.encode("utf-8"))
            root = tree.root_node

            extractor = AllExtractor()
            exports = extractor.extract(root, content.encode("utf-8"))

            assert extractor.has_all
            assert "func1" in exports
            assert "func2" in exports
            assert "MyClass" in exports

        except ImportError:
            pytest.skip("tree-sitter not available")

    def test_extract_no_all(self):
        """Test when no __all__ is defined."""
        content = '''
def func1():
    pass

class MyClass:
    pass
'''

        try:
            import tree_sitter_languages
            parser = tree_sitter_languages.get_parser("python")
            tree = parser.parse(content.encode("utf-8"))
            root = tree.root_node

            extractor = AllExtractor()
            exports = extractor.extract(root, content.encode("utf-8"))

            assert not extractor.has_all
            assert exports == []

        except ImportError:
            pytest.skip("tree-sitter not available")


class TestResolveAlias:
    """Tests for the resolve_alias function."""

    def test_resolve_aliased_name(self):
        """Test resolving an aliased name returns the alias."""
        registry = AliasRegistry()
        registry.add_module_alias("numpy", "np", 1, "test.py")

        imports = [
            ImportInfo(
                raw_module="numpy",
                raw_name="numpy",
                resolved_name="np",
                alias="np",
                line=1,
            )
        ]

        resolved = resolve_alias("np", imports, registry)
        assert resolved == "np"  # Alias is returned as-is

    def test_resolve_unaliased_name(self):
        """Test resolving an unaliased name."""
        registry = AliasRegistry()
        imports = [
            ImportInfo(
                raw_module="os",
                raw_name="path",
                resolved_name="path",
                line=1,
            )
        ]

        resolved = resolve_alias("path", imports, registry)
        assert resolved == "path"


class TestRealWorldPatterns:
    """Tests for real-world import patterns."""

    def test_tensorflow_aliases(self):
        """Test common TensorFlow import aliases."""
        content = '''
import tensorflow as tf
from tensorflow import keras
from tensorflow.keras.layers import Dense, Conv2D
from tensorflow.keras import layers as KL
'''

        imports, aliases = extract_imports_standalone(content, "python", "test.py")

        # Check main imports
        assert any(imp.resolved_name == "tf" for imp in imports)
        assert any(imp.resolved_name == "keras" for imp in imports)

        # Check aliased import
        keras_aliases = [imp for imp in imports if imp.alias == "KL"]
        assert len(keras_aliases) >= 1

    def test_numpy_pandas_patterns(self):
        """Test common NumPy/pandas import patterns."""
        content = '''
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pandas import DataFrame as DF
'''

        imports, aliases = extract_imports_standalone(content, "python", "test.py")

        resolved_names = {imp.resolved_name for imp in imports}
        assert "np" in resolved_names
        assert "pd" in resolved_names
        assert "plt" in resolved_names
        assert "DF" in resolved_names

    def test_typing_patterns(self):
        """Test typing module imports."""
        content = '''
from typing import List, Dict, Optional, Union
from typing import Callable as Fn
from collections.abc import Iterable, Generator
'''

        imports, _ = extract_imports_standalone(content, "python", "test.py")

        names = {imp.resolved_name for imp in imports}
        assert "List" in names
        assert "Dict" in names
        assert "Optional" in names
        assert "Fn" in names
        assert "Iterable" in names


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
