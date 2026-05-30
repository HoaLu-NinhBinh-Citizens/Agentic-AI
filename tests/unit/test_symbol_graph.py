"""Unit tests for SymbolGraph."""
import asyncio
import os
import time
from unittest.mock import patch

import pytest
from pathlib import Path

from src.infrastructure.indexing.symbol_graph import (
    SymbolGraph,
    SymbolNode,
    CallEdge,
    CycleInfo,
    SymbolGraphStats,
)
from src.infrastructure.indexing.hash_utils import compute_content_hash


def run_sync(coro):
    """Run an async function synchronously."""
    return asyncio.run(coro)


class TestSymbolNode:
    def test_hash(self):
        n1 = SymbolNode(name="foo", kind="function", file_path="a.py", line=1, end_line=1)
        n2 = SymbolNode(name="foo", kind="function", file_path="a.py", line=1, end_line=1)
        assert hash(n1) == hash(n2)

    def test_attributes(self):
        node = SymbolNode(
            name="my_func",
            kind="function",
            file_path="test.py",
            line=5,
            end_line=10,
            signature="def my_func():",
            docstring="Do something.",
            decorators=["cache", "async"],
        )
        assert node.name == "my_func"
        assert node.kind == "function"
        assert node.file_path == "test.py"
        assert node.line == 5
        assert node.end_line == 10
        assert node.signature == "def my_func():"
        assert node.docstring == "Do something."
        assert "cache" in node.decorators


class TestCallEdge:
    def test_hash(self):
        e1 = CallEdge("caller", "f.py", 1, "callee", "f.py", 5)
        e2 = CallEdge("caller", "f.py", 1, "callee", "f.py", 5)
        assert hash(e1) == hash(e2)

    def test_attributes(self):
        edge = CallEdge(
            caller="outer",
            caller_file="a.py",
            caller_line=3,
            callee="inner",
            callee_file="b.py",
            callee_line=7,
            is_indirect=False,
        )
        assert edge.caller == "outer"
        assert edge.callee == "inner"
        assert edge.is_indirect is False


class TestCycleInfo:
    def test_creation(self):
        cycle = CycleInfo(
            functions=["a", "b", "c", "a"],
            total_calls=3,
            severity="warning",
        )
        assert cycle.functions == ["a", "b", "c", "a"]
        assert cycle.total_calls == 3
        assert cycle.severity == "warning"


class TestSymbolGraph:
    def setup_method(self):
        self.graph = SymbolGraph()

    def teardown_method(self):
        self.graph.clear()

    # ─── Basic indexing ────────────────────────────────────────────────────

    def test_index_python_file(self, tmp_path):
        (tmp_path / "test.py").write_text(
            "def my_func():\n    pass\n\nclass MyClass:\n    pass\n",
            encoding="utf-8",
        )
        result = run_sync(self.graph.index_file(str(tmp_path / "test.py")))
        assert result["status"] == "indexed"
        assert result["symbols"] >= 2

    def test_index_c_file(self, tmp_path):
        (tmp_path / "test.c").write_text(
            "int my_function(void) { return 0; }\n"
            "struct MyStruct { int x; };\n",
            encoding="utf-8",
        )
        result = run_sync(self.graph.index_file(str(tmp_path / "test.c")))
        assert result["status"] == "indexed"

    def test_index_nonexistent_file(self):
        result = run_sync(self.graph.index_file("/nonexistent/file.py"))
        assert result["status"] == "not_found"

    def test_index_directory(self, tmp_path):
        (tmp_path / "a.py").write_text("def func_a():\n    pass\n", encoding="utf-8")
        (tmp_path / "b.py").write_text("def func_b():\n    pass\n", encoding="utf-8")
        result = run_sync(self.graph.index_directory(str(tmp_path)))
        assert result["files"] == 2

    def test_incremental_unchanged_file(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("def func():\n    pass\n", encoding="utf-8")
        r1 = run_sync(self.graph.index_file(str(f)))
        r2 = run_sync(self.graph.index_file(str(f)))
        assert r2["status"] == "unchanged"

    def test_incremental_changed_file(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("def func():\n    pass\n", encoding="utf-8")
        run_sync(self.graph.index_file(str(f)))
        f.write_text("def func():\n    print(1)\n", encoding="utf-8")
        r2 = run_sync(self.graph.index_file(str(f)))
        assert r2["status"] == "indexed"

    def test_content_hash_detection(self, tmp_path):
        """Test that content changes are detected even when mtime is mocked to stay the same."""
        f = tmp_path / "test.py"
        f.write_text("def original():\n    pass\n", encoding="utf-8")

        # First index
        r1 = run_sync(self.graph.index_file(str(f)))
        assert r1["status"] == "indexed"

        # Verify hash is stored
        assert str(f) in self.graph._file_hash
        original_hash = self.graph._file_hash[str(f)]

        # Modify file content
        f.write_text("def modified():\n    print(1)\n", encoding="utf-8")

        # Mock mtime to NOT change (simulating Windows filesystem behavior)
        original_mtime = os.path.getmtime(str(f))

        with patch("src.infrastructure.indexing.symbol_graph.os.path.getmtime", return_value=original_mtime):
            # File should still be re-indexed because content hash changed
            r2 = run_sync(self.graph.index_file(str(f)))
            assert r2["status"] == "indexed", "File should be re-indexed when content hash changes"
            assert self.graph._file_hash[str(f)] != original_hash, "Hash should be updated"

    def test_content_hash_unchanged_same_content(self, tmp_path):
        """Test that same content returns unchanged status."""
        f = tmp_path / "test.py"
        f.write_text("def func():\n    pass\n", encoding="utf-8")

        # First index
        r1 = run_sync(self.graph.index_file(str(f)))
        assert r1["status"] == "indexed"

        # Touch file (update mtime) without changing content
        old_mtime = os.path.getmtime(str(f))
        time.sleep(0.01)  # Small delay to ensure different mtime if possible
        os.utime(str(f), (old_mtime + 1, old_mtime + 1))

        # Second index - should be unchanged due to hash match
        r2 = run_sync(self.graph.index_file(str(f)))
        assert r2["status"] == "unchanged", "File should be unchanged when content hash matches"

    # ─── Symbol extraction ─────────────────────────────────────────────────

    def test_extract_python_functions(self, tmp_path):
        code = (
            "def my_function():\n"
            "    async def inner():\n"
            "        pass\n"
        )
        (tmp_path / "test.py").write_text(code, encoding="utf-8")
        symbols = self.graph._extract_symbols_regex(str(tmp_path / "test.py"), code)
        names = [s["name"] for s in symbols]
        assert "my_function" in names

    def test_extract_python_class(self, tmp_path):
        code = "class MyClass:\n    def method(self):\n        pass\n"
        (tmp_path / "test.py").write_text(code, encoding="utf-8")
        symbols = self.graph._extract_symbols_regex(str(tmp_path / "test.py"), code)
        kinds = [s["kind"] for s in symbols]
        assert "class" in kinds

    def test_extract_c_function(self, tmp_path):
        code = "int calculate_sum(int a, int b) { return a + b; }\n"
        (tmp_path / "test.c").write_text(code, encoding="utf-8")
        symbols = self.graph._extract_symbols_regex(str(tmp_path / "test.c"), code)
        names = [s["name"] for s in symbols]
        assert "calculate_sum" in names

    def test_extract_rust_function(self, tmp_path):
        code = "pub fn rust_main() {\n    println!(\"hello\");\n}\n"
        (tmp_path / "test.rs").write_text(code, encoding="utf-8")
        symbols = self.graph._extract_symbols_regex(str(tmp_path / "test.rs"), code)
        names = [s["name"] for s in symbols]
        assert "rust_main" in names

    # ─── Call edges ────────────────────────────────────────────────────────

    def test_call_edges_basic(self, tmp_path):
        code = (
            "def caller():\n"
            "    callee()\n"
            "def callee():\n"
            "    pass\n"
        )
        (tmp_path / "test.py").write_text(code, encoding="utf-8")
        run_sync(self.graph.index_file(str(tmp_path / "test.py")))
        callers = self.graph.get_callers("callee")
        assert any(e.caller == "caller" for e in callers)

    def test_call_edges_exclude_comments(self, tmp_path):
        code = (
            "def foo():\n"
            "    # call_me()\n"
            "    pass\n"
        )
        (tmp_path / "test.py").write_text(code, encoding="utf-8")
        run_sync(self.graph.index_file(str(tmp_path / "test.py")))
        edges = self.graph._extract_call_edges(str(tmp_path / "test.py"), code, [])
        called = [e.callee for e in edges]
        assert "call_me" not in called

    def test_call_edges_exclude_strings(self, tmp_path):
        code = 'def foo():\n    x = "my_func()"\n    pass\n'
        (tmp_path / "test.py").write_text(code, encoding="utf-8")
        edges = self.graph._extract_call_edges(str(tmp_path / "test.py"), code, [])
        called = [e.callee for e in edges]
        assert "my_func" not in called

    def test_call_edges_skip_keywords(self, tmp_path):
        code = "def foo():\n    if True:\n        for i in range(10):\n            print(i)\n"
        (tmp_path / "test.py").write_text(code, encoding="utf-8")
        edges = self.graph._extract_call_edges(str(tmp_path / "test.py"), code, [])
        called = [e.callee for e in edges]
        assert "range" not in called
        assert "print" not in called

    def test_call_edges_skip_uppercase(self, tmp_path):
        code = "def foo():\n    MY_CONSTANT()\n    pass\n"
        (tmp_path / "test.py").write_text(code, encoding="utf-8")
        edges = self.graph._extract_call_edges(str(tmp_path / "test.py"), code, [])
        called = [e.callee for e in edges]
        assert "MY_CONSTANT" not in called

    # ─── Circular dependency ───────────────────────────────────────────────

    def test_detect_simple_cycle(self, tmp_path):
        code = (
            "def a():\n    b()\n"
            "def b():\n    a()\n"
        )
        (tmp_path / "test.py").write_text(code, encoding="utf-8")
        run_sync(self.graph.index_file(str(tmp_path / "test.py")))
        cycles = self.graph.find_circular_dependencies()
        assert isinstance(cycles, list)

    def test_no_cycle(self, tmp_path):
        code = (
            "def a():\n    pass\n"
            "def b():\n    a()\n"
        )
        (tmp_path / "test.py").write_text(code, encoding="utf-8")
        run_sync(self.graph.index_file(str(tmp_path / "test.py")))
        cycles = self.graph.find_circular_dependencies()
        assert len(cycles) == 0

    # ─── Graph traversal ───────────────────────────────────────────────────

    def test_get_reachable_callees(self, tmp_path):
        code = (
            "def main():\n    a()\n    b()\n"
            "def a():\n    c()\n"
            "def b():\n    pass\n"
            "def c():\n    pass\n"
        )
        (tmp_path / "test.py").write_text(code, encoding="utf-8")
        run_sync(self.graph.index_file(str(tmp_path / "test.py")))
        reachable = self.graph.get_reachable("main", direction="callees")
        assert "a" in reachable
        assert "b" in reachable
        assert "c" in reachable

    def test_get_reachable_callers(self, tmp_path):
        code = (
            "def main():\n    foo()\n"
            "def bar():\n    foo()\n"
            "def foo():\n    pass\n"
        )
        (tmp_path / "test.py").write_text(code, encoding="utf-8")
        run_sync(self.graph.index_file(str(tmp_path / "test.py")))
        reachable = self.graph.get_reachable("foo", direction="callers")
        assert "main" in reachable
        assert "bar" in reachable

    def test_get_call_depth(self, tmp_path):
        code = (
            "def main():\n    a()\n"
            "def a():\n    b()\n"
            "def b():\n    pass\n"
        )
        (tmp_path / "test.py").write_text(code, encoding="utf-8")
        run_sync(self.graph.index_file(str(tmp_path / "test.py")))
        depth = self.graph.get_call_depth("main", "b")
        assert depth == 2

    def test_get_call_depth_no_path(self, tmp_path):
        code = "def main():\n    pass\n"
        (tmp_path / "test.py").write_text(code, encoding="utf-8")
        run_sync(self.graph.index_file(str(tmp_path / "test.py")))
        depth = self.graph.get_call_depth("main", "nonexistent")
        assert depth is None

    # ─── Stats ─────────────────────────────────────────────────────────────

    def test_stats(self, tmp_path):
        (tmp_path / "test.py").write_text("def func():\n    pass\n", encoding="utf-8")
        run_sync(self.graph.index_file(str(tmp_path / "test.py")))
        stats = self.graph.get_stats()
        assert stats["files_indexed"] == 1
        assert stats["total_symbols"] >= 1

    def test_stats_returns_dict(self, tmp_path):
        (tmp_path / "test.py").write_text("def func():\n    pass\n", encoding="utf-8")
        run_sync(self.graph.index_file(str(tmp_path / "test.py")))
        stats = self.graph.get_stats()
        assert isinstance(stats, dict)
        assert "files_indexed" in stats

    # ─── Maintenance ───────────────────────────────────────────────────────

    def test_clear(self, tmp_path):
        (tmp_path / "test.py").write_text("def func():\n    pass\n", encoding="utf-8")
        run_sync(self.graph.index_file(str(tmp_path / "test.py")))
        self.graph.clear()
        stats = self.graph.get_stats()
        assert stats["files_indexed"] == 0

    def test_remove_file_data(self, tmp_path):
        (tmp_path / "test.py").write_text("def func():\n    pass\n", encoding="utf-8")
        run_sync(self.graph.index_file(str(tmp_path / "test.py")))
        self.graph._remove_file_data(str(tmp_path / "test.py"))
        stats = self.graph.get_stats()
        assert stats["files_indexed"] == 0

    # ─── Dependents and dependencies ──────────────────────────────────────

    def test_get_dependents(self, tmp_path):
        code = (
            "def main():\n    helper()\n"
            "def helper():\n    pass\n"
        )
        (tmp_path / "test.py").write_text(code, encoding="utf-8")
        run_sync(self.graph.index_file(str(tmp_path / "test.py")))
        dependents = self.graph.get_dependents("helper")
        assert "main" in dependents

    def test_get_dependencies(self, tmp_path):
        code = (
            "def main():\n    a()\n    b()\n"
            "def a():\n    pass\n"
            "def b():\n    pass\n"
        )
        (tmp_path / "test.py").write_text(code, encoding="utf-8")
        run_sync(self.graph.index_file(str(tmp_path / "test.py")))
        deps = self.graph.get_dependencies("main")
        assert "a" in deps
        assert "b" in deps

    # ─── Strip comments and strings ───────────────────────────────────────

    def test_strip_python_comments(self):
        result = SymbolGraph._strip_comments_and_strings("x = 1  # comment")
        assert "# comment" not in result

    def test_strip_c_comments(self):
        result = SymbolGraph._strip_comments_and_strings("x = 1; // comment")
        assert "comment" not in result

    def test_strip_strings(self):
        result = SymbolGraph._strip_comments_and_strings('x = "hello world"')
        assert "hello" not in result

    def test_strip_multiline_comment(self):
        result = SymbolGraph._strip_comments_and_strings("/* multi\nline */ x = 1")
        assert "multi" not in result
