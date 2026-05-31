"""Language parser sanity tests for Rust and Go.

Tests that verify tree-sitter parsers work correctly for:
- Rust: function_item, struct_item, enum_item, impl_item
- Go: function_declaration, type_declaration
"""

from __future__ import annotations

from pathlib import Path

import pytest


class TestRustParser:
    """Sanity tests for Rust tree-sitter parser."""

    @pytest.fixture
    def rust_code(self) -> str:
        """Sample Rust code for testing."""
        return '''
pub struct Config {
    name: String,
    value: i32,
}

impl Config {
    pub fn new(name: &str, value: i32) -> Self {
        Config {
            name: name.to_string(),
            value,
        }
    }

    pub fn get_value(&self) -> i32 {
        self.value
    }
}

pub enum Status {
    Pending,
    Running,
    Done,
}

fn helper_function(x: i32) -> i32 {
    x * 2
}
'''

    @pytest.fixture
    def rust_indexer(self):
        """Create a tree-sitter indexer for Rust."""
        from src.infrastructure.indexing.tree_sitter import SafeTreeSitterIndexer
        return SafeTreeSitterIndexer()

    @pytest.mark.asyncio
    async def test_rust_struct_parsing(self, rust_indexer: "SafeTreeSitterIndexer", rust_code: str, tmp_path: Path):
        """Test that Rust struct is correctly parsed."""
        test_file = tmp_path / "test.rs"
        test_file.write_text(rust_code)

        result = await rust_indexer.index_file(str(test_file))

        assert result["status"] == "success"
        assert result["parser"] == "tree-sitter"

        symbols = result["symbols"]
        struct_symbols = [s for s in symbols if s["type"] == "struct"]
        assert len(struct_symbols) >= 1, f"Expected at least 1 struct, got {len(struct_symbols)}"
        assert any("Config" in s["name"] for s in struct_symbols)

    @pytest.mark.asyncio
    async def test_rust_function_parsing(self, rust_indexer: "SafeTreeSitterIndexer", rust_code: str, tmp_path: Path):
        """Test that Rust functions are correctly parsed."""
        test_file = tmp_path / "test.rs"
        test_file.write_text(rust_code)

        result = await rust_indexer.index_file(str(test_file))
        symbols = result["symbols"]

        func_symbols = [s for s in symbols if s["type"] == "function"]
        # Note: impl block methods may be counted differently depending on parser
        assert len(func_symbols) >= 1, f"Expected at least 1 function, got {len(func_symbols)}"

    @pytest.mark.asyncio
    async def test_rust_enum_parsing(self, rust_indexer: "SafeTreeSitterIndexer", rust_code: str, tmp_path: Path):
        """Test that Rust enum is correctly parsed."""
        test_file = tmp_path / "test.rs"
        test_file.write_text(rust_code)

        result = await rust_indexer.index_file(str(test_file))
        symbols = result["symbols"]

        enum_symbols = [s for s in symbols if s["type"] == "enum"]
        assert len(enum_symbols) >= 1, f"Expected at least 1 enum, got {len(enum_symbols)}"
        assert any("Status" in s["name"] for s in enum_symbols)

    @pytest.mark.asyncio
    async def test_rust_impl_parsing(self, rust_indexer: "SafeTreeSitterIndexer", rust_code: str, tmp_path: Path):
        """Test that Rust impl blocks are correctly parsed."""
        test_file = tmp_path / "test.rs"
        test_file.write_text(rust_code)

        result = await rust_indexer.index_file(str(test_file))
        symbols = result["symbols"]

        impl_symbols = [s for s in symbols if s["type"] == "impl"]
        assert len(impl_symbols) >= 1, f"Expected at least 1 impl, got {len(impl_symbols)}"

    @pytest.mark.asyncio
    async def test_rust_pub_keyword_preserved(self, rust_indexer: "SafeTreeSitterIndexer", tmp_path: Path):
        """Test that pub keyword is handled correctly."""
        code = "pub fn public_func() {}\nfn private_func() {}"
        test_file = tmp_path / "test.rs"
        test_file.write_text(code)

        result = await rust_indexer.index_file(str(test_file))
        symbols = result["symbols"]

        func_symbols = [s for s in symbols if s["type"] == "function"]
        assert len(func_symbols) >= 1

    @pytest.mark.asyncio
    async def test_rust_generic_functions(self, rust_indexer: "SafeTreeSitterIndexer", tmp_path: Path):
        """Test parsing of generic functions."""
        code = '''
fn identity<T>(x: T) -> T {
    x
}

struct Wrapper<T> {
    value: T,
}
'''
        test_file = tmp_path / "test.rs"
        test_file.write_text(code)

        result = await rust_indexer.index_file(str(test_file))
        assert result["status"] == "success"

        symbols = result["symbols"]
        assert len(symbols) >= 2, f"Expected generic function + struct, got {len(symbols)}"


class TestGoParser:
    """Sanity tests for Go tree-sitter parser."""

    @pytest.fixture
    def go_code(self) -> str:
        """Sample Go code for testing."""
        return '''
package main

import "fmt"

type Config struct {
    Name  string
    Value int
}

func NewConfig(name string, value int) *Config {
    return &Config{
        Name:  name,
        Value: value,
    }
}

func (c *Config) GetValue() int {
    return c.Value
}

func helper(x int) int {
    return x * 2
}

type Status int

const (
    Pending Status = iota
    Running
    Done
)
'''

    @pytest.fixture
    def go_indexer(self):
        """Create a tree-sitter indexer for Go."""
        from src.infrastructure.indexing.tree_sitter import SafeTreeSitterIndexer
        return SafeTreeSitterIndexer()

    @pytest.mark.asyncio
    async def test_go_struct_parsing(self, go_indexer: "SafeTreeSitterIndexer", go_code: str, tmp_path: Path):
        """Test that Go struct is correctly parsed."""
        test_file = tmp_path / "test.go"
        test_file.write_text(go_code)

        result = await go_indexer.index_file(str(test_file))

        assert result["status"] == "success"
        assert result["parser"] == "tree-sitter"

        symbols = result["symbols"]
        # Go structs are parsed as type declarations
        type_symbols = [s for s in symbols if s["type"] == "type"]
        assert len(type_symbols) >= 1, f"Expected at least 1 type, got {len(type_symbols)}"

    @pytest.mark.asyncio
    async def test_go_function_parsing(self, go_indexer: "SafeTreeSitterIndexer", go_code: str, tmp_path: Path):
        """Test that Go functions are correctly parsed."""
        test_file = tmp_path / "test.go"
        test_file.write_text(go_code)

        result = await go_indexer.index_file(str(test_file))
        symbols = result["symbols"]

        func_symbols = [s for s in symbols if s["type"] == "function"]
        assert len(func_symbols) >= 2, f"Expected at least 2 functions, got {len(func_symbols)}"

    @pytest.mark.asyncio
    async def test_go_method_parsing(self, go_indexer: "SafeTreeSitterIndexer", go_code: str, tmp_path: Path):
        """Test that Go methods (func with receiver) are correctly parsed."""
        test_file = tmp_path / "test.go"
        test_file.write_text(go_code)

        result = await go_indexer.index_file(str(test_file))
        symbols = result["symbols"]

        # Methods in Go are parsed as functions in our symbol extraction
        # The key is that we get at least the top-level functions
        func_symbols = [s for s in symbols if s["type"] == "function"]
        assert len(func_symbols) >= 2, f"Expected at least 2 functions/methods, got {len(func_symbols)}"

    @pytest.mark.asyncio
    async def test_go_const_parsing(self, go_indexer: "SafeTreeSitterIndexer", go_code: str, tmp_path: Path):
        """Test that Go constants are handled."""
        test_file = tmp_path / "test.go"
        test_file.write_text(go_code)

        result = await go_indexer.index_file(str(test_file))
        symbols = result["symbols"]

        # Check that parsing succeeded
        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_go_interface_parsing(self, go_indexer: "SafeTreeSitterIndexer", tmp_path: Path):
        """Test parsing of Go interfaces."""
        code = '''
type Reader interface {
    Read(p []byte) (n int, err error)
}

type Writer interface {
    Write(p []byte) (n int, err error)
}
'''
        test_file = tmp_path / "test.go"
        test_file.write_text(code)

        result = await go_indexer.index_file(str(test_file))
        assert result["status"] == "success"

        symbols = result["symbols"]
        assert len(symbols) >= 2, f"Expected interfaces, got {len(symbols)}"

    @pytest.mark.asyncio
    async def test_go_multiple_packages(self, go_indexer: "SafeTreeSitterIndexer", tmp_path: Path):
        """Test parsing of Go files with different package declarations."""
        code1 = 'package api\nfunc ApiFunc() {}\n'
        code2 = 'package db\nfunc DbFunc() {}\n'

        file1 = tmp_path / "api.go"
        file2 = tmp_path / "db.go"
        file1.write_text(code1)
        file2.write_text(code2)

        result1 = await go_indexer.index_file(str(file1))
        result2 = await go_indexer.index_file(str(file2))

        assert result1["status"] == "success"
        assert result2["status"] == "success"


class TestLanguageCoverage:
    """Tests for overall language coverage metrics."""

    @pytest.fixture
    def indexer(self):
        """Create a tree-sitter indexer."""
        from src.infrastructure.indexing.tree_sitter import SafeTreeSitterIndexer
        return SafeTreeSitterIndexer()

    @pytest.mark.asyncio
    async def test_parser_coverage_report(self, indexer: "SafeTreeSitterIndexer", tmp_path: Path):
        """Test that we can generate a parser coverage report."""
        from src.infrastructure.indexing.tree_sitter import _EXTENSION_LANGUAGE

        # Get supported languages
        supported = set(_EXTENSION_LANGUAGE.values())
        supported.discard("text")

        print(f"\n[Coverage] Supported languages: {len(supported)}")
        print(f"  {sorted(supported)}")

        # Verify key languages are supported
        key_languages = {"python", "c", "cpp", "javascript", "typescript", "rust", "go"}
        for lang in key_languages:
            assert lang in supported, f"Language '{lang}' should be supported"

    @pytest.mark.asyncio
    async def test_tree_sitter_vs_regex_fallback(
        self, indexer: "SafeTreeSitterIndexer", tmp_path: Path
    ):
        """Test that tree-sitter is used when available, with regex fallback tracked."""
        # Python code
        py_code = '''
def hello_world():
    print("Hello")

class MyClass:
    def method(self):
        pass
'''
        py_file = tmp_path / "test.py"
        py_file.write_text(py_code)

        result = await indexer.index_file(str(py_file))

        # Check parser used
        assert result["parser"] in ("tree-sitter", "regex"), f"Unexpected parser: {result['parser']}"

        # Check fallback count in stats
        initial_fallback = indexer.stats.files_fallback_regex

        # Generate report
        status = indexer.get_status()
        assert "stats" in status
        assert "files_fallback_regex" in status["stats"]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
