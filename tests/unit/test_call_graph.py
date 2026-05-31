"""Tests for CallGraph module.

Tests AST-based call graph construction.
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock

from src.core.cognition.call_graph import (
    CallGraph,
    CallSite,
    FunctionDef,
    build_call_graph,
    _CallSiteVisitor,
)


class TestCallGraph:
    """Test suite for CallGraph."""

    def test_build_simple(self, tmp_path):
        """Test building call graph from simple Python file."""
        test_file = tmp_path / "test.py"
        test_file.write_text("""
def foo():
    bar()

def bar():
    pass

class MyClass:
    def method(self):
        foo()
""")

        indexed_files = {
            str(test_file): [
                {"name": "foo", "kind": "function", "line": 2},
                {"name": "bar", "kind": "function", "line": 5},
                {"name": "method", "kind": "method", "line": 8},
            ]
        }

        graph = CallGraph(tmp_path)
        graph.build(indexed_files)

        assert graph._is_built
        assert graph.stats["files"] == 1

    def test_find_references(self, tmp_path):
        """Test finding function references."""
        test_file = tmp_path / "test.py"
        test_file.write_text("""
def foo():
    bar()
    bar()

def bar():
    pass
""")

        indexed_files = {
            str(test_file): [
                {"name": "foo", "kind": "function", "line": 2},
                {"name": "bar", "kind": "function", "line": 5},
            ]
        }

        graph = CallGraph(tmp_path)
        graph.build(indexed_files)

        # Add call sites manually for testing
        graph._call_sites = [
            CallSite("foo", "bar", str(test_file), 3),
            CallSite("foo", "bar", str(test_file), 4),
        ]

        refs = graph.find_references("bar")
        assert len(refs) == 2
        assert all(r.callee == "bar" for r in refs)

    def test_get_callers(self, tmp_path):
        """Test getting callers of a function."""
        test_file = tmp_path / "test.py"
        test_file.write_text("""
def foo():
    bar()

def bar():
    pass
""")

        indexed_files = {
            str(test_file): [
                {"name": "foo", "kind": "function", "line": 2},
                {"name": "bar", "kind": "function", "line": 5},
            ]
        }

        graph = CallGraph(tmp_path)
        graph.build(indexed_files)
        graph._call_sites = [
            CallSite("foo", "bar", str(test_file), 3),
        ]

        callers = graph.get_callers("bar")
        assert len(callers) == 1
        assert callers[0].caller == "foo"

    def test_get_callees(self, tmp_path):
        """Test getting callees of a function."""
        test_file = tmp_path / "test.py"
        test_file.write_text("""
def foo():
    bar()
    baz()

def bar():
    pass

def baz():
    pass
""")

        indexed_files = {
            str(test_file): [
                {"name": "foo", "kind": "function", "line": 2},
                {"name": "bar", "kind": "function", "line": 5},
                {"name": "baz", "kind": "function", "line": 8},
            ]
        }

        graph = CallGraph(tmp_path)
        graph.build(indexed_files)
        graph._call_sites = [
            CallSite("foo", "bar", str(test_file), 3),
            CallSite("foo", "baz", str(test_file), 4),
        ]

        callees = graph.get_callees("foo")
        assert len(callees) == 2
        assert {"bar", "baz"} == {c.callee for c in callees}

    def test_find_cycles(self, tmp_path):
        """Test finding circular dependencies."""
        test_file = tmp_path / "test.py"
        test_file.write_text("""
def a():
    b()

def b():
    c()

def c():
    a()
""")

        indexed_files = {
            str(test_file): [
                {"name": "a", "kind": "function", "line": 2},
                {"name": "b", "kind": "function", "line": 5},
                {"name": "c", "kind": "function", "line": 8},
            ]
        }

        graph = CallGraph(tmp_path)
        graph.build(indexed_files)
        graph._call_sites = [
            CallSite("a", "b", str(test_file), 3),
            CallSite("b", "c", str(test_file), 6),
            CallSite("c", "a", str(test_file), 9),
        ]

        cycles = graph.find_cycles()
        # Should find at least one cycle
        assert len(cycles) > 0

    def test_to_dict(self, tmp_path):
        """Test serialization to dictionary."""
        test_file = tmp_path / "test.py"
        test_file.write_text("""
def foo():
    bar()

def bar():
    pass
""")

        indexed_files = {
            str(test_file): [
                {"name": "foo", "kind": "function", "line": 2},
                {"name": "bar", "kind": "function", "line": 5},
            ]
        }

        graph = CallGraph(tmp_path)
        graph.build(indexed_files)
        graph._call_sites = [
            CallSite("foo", "bar", str(test_file), 3),
        ]

        result = graph.to_dict()
        assert "stats" in result
        assert "functions" in result
        assert "call_sites" in result

    def test_get_function(self, tmp_path):
        """Test getting function definitions by name."""
        test_file = tmp_path / "test.py"
        test_file.write_text("""
def foo():
    pass

def bar():
    pass
""")

        indexed_files = {
            str(test_file): [
                {"name": "foo", "kind": "function", "line": 2},
                {"name": "bar", "kind": "function", "line": 5},
            ]
        }

        graph = CallGraph(tmp_path)
        graph.build(indexed_files)

        funcs = graph.get_function("foo")
        assert funcs is not None
        assert len(funcs) == 1
        assert funcs[0].name == "foo"


class TestCallSiteVisitor:
    """Test suite for _CallSiteVisitor AST visitor."""

    def test_visit_call(self):
        """Test visiting function calls."""
        import ast

        code = """
def foo():
    bar()
    baz()
"""
        tree = ast.parse(code)
        visitor = _CallSiteVisitor("test.py")
        visitor.visit(tree)

        assert len(visitor.call_sites) >= 2
        callees = {s.callee for s in visitor.call_sites}
        assert "bar" in callees
        assert "baz" in callees

    def test_visit_import(self):
        """Test visiting import statements."""
        import ast

        code = """
import os
from pathlib import Path
"""
        tree = ast.parse(code)
        visitor = _CallSiteVisitor("test.py")
        visitor.visit(tree)

        assert len(visitor.imports) == 2

    def test_visit_class(self):
        """Test visiting class methods."""
        import ast

        code = """
class MyClass:
    def method(self):
        obj.method()
"""
        tree = ast.parse(code)
        visitor = _CallSiteVisitor("test.py")
        visitor.visit(tree)

        # Check that we detected the method call
        assert len(visitor.call_sites) >= 1
        # Find the method call
        method_calls = [s for s in visitor.call_sites if s.is_method]
        assert len(method_calls) == 1
        assert method_calls[0].callee == "method"

    def test_skip_builtins(self):
        """Test that built-in functions are skipped."""
        import ast

        code = """
def foo():
    print("hello")
    len("test")
"""
        tree = ast.parse(code)
        visitor = _CallSiteVisitor("test.py")
        visitor.visit(tree)

        # print and len should be skipped as they're builtins
        callees = {s.callee for s in visitor.call_sites}
        assert "print" not in callees
        assert "len" not in callees


class TestBuildCallGraph:
    """Test suite for build_call_graph function."""

    def test_build_with_indexed_files(self, tmp_path):
        """Test building call graph with pre-indexed files."""
        test_file = tmp_path / "test.py"
        test_file.write_text("""
def foo():
    bar()

def bar():
    pass
""")

        indexed_files = {
            str(test_file): [
                {"name": "foo", "kind": "function", "line": 2},
                {"name": "bar", "kind": "function", "line": 5},
            ]
        }

        graph = build_call_graph(tmp_path, indexed_files)
        assert graph._is_built

    def test_build_from_directory(self, tmp_path):
        """Test building call graph from directory."""
        test_file = tmp_path / "test.py"
        test_file.write_text("""
def foo():
    pass
""")

        graph = build_call_graph(tmp_path)
        assert graph._is_built
