import pytest
from pathlib import Path
from src.infrastructure.analysis.type_resolver import TypeResolver, TypeInfo, ImportInfo


class TestTypeResolver:
    """Tests for TypeResolver."""

    def test_parse_simple_import(self):
        """Test parsing 'import numpy as np'."""
        code = "import numpy as np"
        resolver = TypeResolver()
        imports = resolver.parse_imports(code)
        assert len(imports) == 1
        assert imports[0].names == [("numpy", "np")]

    def test_parse_from_import(self):
        """Test parsing 'from sklearn.model_selection import train_test_split'."""
        code = "from sklearn.model_selection import train_test_split"
        resolver = TypeResolver()
        imports = resolver.parse_imports(code)
        assert len(imports) == 1
        assert imports[0].module == "sklearn.model_selection"
        assert imports[0].names == [("train_test_split", None)]

    def test_parse_multiple_from_import(self):
        """Test parsing multiple imports with aliases."""
        code = "from os import path, makedirs as mkdtemp, getcwd"
        resolver = TypeResolver()
        imports = resolver.parse_imports(code)
        assert imports[0].names == [
            ("path", None),
            ("makedirs", "mkdtemp"),
            ("getcwd", None)
        ]

    def test_parse_import_with_parens(self):
        """Test parsing import with parentheses."""
        code = "from os import (\n    path,\n    getcwd\n)"
        resolver = TypeResolver()
        imports = resolver.parse_imports(code)
        assert len(imports) == 1
        assert ("path", None) in imports[0].names
        assert ("getcwd", None) in imports[0].names

    def test_parse_multiple_imports(self):
        """Test parsing multiple separate import statements."""
        code = "import numpy as np\nimport pandas as pd"
        resolver = TypeResolver()
        imports = resolver.parse_imports(code)
        assert len(imports) == 2
        assert imports[0].names == [("numpy", "np")]
        assert imports[1].names == [("pandas", "pd")]

    def test_parse_dotted_import(self):
        """Test parsing 'import a.b.c'."""
        code = "import os.path"
        resolver = TypeResolver()
        imports = resolver.parse_imports(code)
        assert len(imports) == 1
        assert imports[0].module == "os.path"
        assert imports[0].names == [("path", None)]

    def test_resolve_alias(self):
        """Test resolving import alias to original name."""
        code = "import numpy as np"
        resolver = TypeResolver()
        imports = resolver.parse_imports(code)
        alias_map = resolver.build_alias_map(imports)
        assert alias_map["np"] == "numpy"

    def test_resolve_no_alias(self):
        """Test that non-aliased imports map to themselves."""
        code = "import numpy"
        resolver = TypeResolver()
        imports = resolver.parse_imports(code)
        alias_map = resolver.build_alias_map(imports)
        assert alias_map["numpy"] == "numpy"

    def test_resolve_builtin(self):
        """Test resolving built-in types."""
        code = "x = 5"
        resolver = TypeResolver()
        result = resolver.resolve_name("int", code, 1)
        assert result is not None
        assert result.is_builtin
        assert result.name == "int"

    def test_resolve_imported_name(self):
        """Test resolving an imported name."""
        code = "import numpy as np\nx = np.array([1, 2, 3])"
        resolver = TypeResolver()
        result = resolver.resolve_name("np", code, 2)
        assert result is not None
        assert result.name == "numpy"
        assert result.module == "numpy"
        assert result.confidence == 0.95

    def test_resolve_unknown_name(self):
        """Test that unknown names return None."""
        code = "x = unknown_variable"
        resolver = TypeResolver()
        result = resolver.resolve_name("unknown_variable", code, 1)
        assert result is None

    def test_resolve_qualified_name(self):
        """Test resolving qualified names like 'module.Class'."""
        code = "import numpy as np"
        resolver = TypeResolver()
        result = resolver.resolve_qualified_name("numpy.ndarray", code)
        assert result is not None
        assert result.name == "ndarray"
        assert result.module == "numpy"
        assert result.full_name == "numpy.ndarray"

    def test_resolve_torch_qualified(self):
        """Test resolving torch.nn.Module style names."""
        code = "import torch"
        resolver = TypeResolver()
        result = resolver.resolve_qualified_name("torch.nn.Module", code)
        assert result is not None
        assert result.name == "Module"
        assert result.module == "torch.nn"

    def test_get_imported_symbols(self):
        """Test getting all importable symbols from imports."""
        code = "from os import path, getcwd\nimport numpy as np"
        resolver = TypeResolver()
        imports = resolver.parse_imports(code)
        symbols = resolver.get_imported_symbols(imports)
        assert "path" in symbols
        assert "getcwd" in symbols
        assert "np" in symbols

    def test_infer_int_type(self):
        """Test type inference for integer assignment."""
        code = "x = 5"
        resolver = TypeResolver()
        result = resolver.infer_type_from_context("x", code, 1)
        assert result is not None
        assert result.name == "int"
        assert result.is_builtin

    def test_infer_float_type(self):
        """Test type inference for float assignment."""
        code = "x = 1.5"
        resolver = TypeResolver()
        result = resolver.infer_type_from_context("x", code, 1)
        assert result is not None
        assert result.name == "float"

    def test_infer_str_type(self):
        """Test type inference for string assignment."""
        code = 'x = "hello"'
        resolver = TypeResolver()
        result = resolver.infer_type_from_context("x", code, 1)
        assert result is not None
        assert result.name == "str"

    def test_infer_list_type(self):
        """Test type inference for empty list."""
        code = "x = []"
        resolver = TypeResolver()
        result = resolver.infer_type_from_context("x", code, 1)
        assert result is not None
        assert result.name == "list"

    def test_skip_comments(self):
        """Test that comments are not parsed as imports."""
        code = "# import commented\nx = 5"
        resolver = TypeResolver()
        imports = resolver.parse_imports(code)
        assert len(imports) == 0

    def test_import_info_dataclass(self):
        """Test ImportInfo dataclass structure."""
        info = ImportInfo(
            line=1,
            names=[("numpy", "np")],
            module="numpy"
        )
        assert info.line == 1
        assert info.names == [("numpy", "np")]
        assert info.module == "numpy"

    def test_type_info_dataclass(self):
        """Test TypeInfo dataclass structure."""
        info = TypeInfo(
            name="ndarray",
            full_name="numpy.ndarray",
            module="numpy",
            is_builtin=False,
            confidence=0.95
        )
        assert info.name == "ndarray"
        assert info.full_name == "numpy.ndarray"
        assert info.module == "numpy"
        assert not info.is_builtin
        assert info.confidence == 0.95
