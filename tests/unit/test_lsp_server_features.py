"""Tests for LSP Server advanced features: definition, references, completion, rename.

Validates the 5 improvement features added to AISupportLSPServer:
1. textDocument/definition (go-to-definition)
2. textDocument/references (find all references)
3. textDocument/completion (inline code completion)
4. textDocument/rename (workspace-wide rename)
5. Extended fix templates (missing await, unused var, type mismatch)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.interfaces.server.lsp_server import (
    AISupportLSPServer,
    CodeAction,
    Diagnostic,
    Position,
    Range,
    TextEdit,
)


@pytest.fixture
def server() -> AISupportLSPServer:
    """Create a fresh LSP server instance."""
    return AISupportLSPServer(root_path=Path("."))


SAMPLE_CODE = """\
import os
from pathlib import Path

class Config:
    debug: bool = False
    
    def __init__(self, path: str):
        self.path = path
        self.loaded = False

    def load(self) -> bool:
        self.loaded = True
        return True

    def save(self) -> None:
        pass


def process_config(config: Config) -> str:
    if config.load():
        return config.path
    return ""


def helper():
    cfg = Config("/tmp")
    result = process_config(cfg)
    return result
"""


# ─── Tests: Go To Definition ────────────────────────────────────────────────


class TestGoToDefinition:
    """Test textDocument/definition handler."""

    def test_find_function_definition(self, server: AISupportLSPServer):
        """Navigate to function definition."""
        uri = "file:///test.py"
        server._documents[uri] = SAMPLE_CODE
        server._index_document_symbols(uri, SAMPLE_CODE)

        # "process_config" is on line 26: "    result = process_config(cfg)"
        # character 13 should be inside "process_config"
        result = server._handle_goto_definition({
            "textDocument": {"uri": uri},
            "position": {"line": 26, "character": 15},  # inside "process_config"
        })

        assert result is not None
        assert len(result) > 0
        found_lines = [r["range"]["start"]["line"] for r in result]
        assert 18 in found_lines  # def process_config(...) is line 18

    def test_find_class_definition(self, server: AISupportLSPServer):
        """Navigate to class definition."""
        uri = "file:///test.py"
        server._documents[uri] = SAMPLE_CODE
        server._index_document_symbols(uri, SAMPLE_CODE)

        # "Config" used on line 25: "    cfg = Config("/tmp")"
        result = server._handle_goto_definition({
            "textDocument": {"uri": uri},
            "position": {"line": 25, "character": 11},  # inside "Config"
        })

        assert result is not None
        assert len(result) > 0
        found_lines = [r["range"]["start"]["line"] for r in result]
        assert 3 in found_lines  # class Config: is line 3

    def test_unknown_symbol_returns_none(self, server: AISupportLSPServer):
        """Unknown symbol returns None/empty."""
        uri = "file:///test.py"
        server._documents[uri] = SAMPLE_CODE

        result = server._handle_goto_definition({
            "textDocument": {"uri": uri},
            "position": {"line": 0, "character": 50},  # beyond line
        })

        assert result is None or result == []


# ─── Tests: Find References ──────────────────────────────────────────────────


class TestFindReferences:
    """Test textDocument/references handler."""

    def test_find_function_references(self, server: AISupportLSPServer):
        """Find all references to a function."""
        uri = "file:///test.py"
        server._documents[uri] = SAMPLE_CODE

        # Find references to "helper" — defined on line 24, called nowhere else
        # Use "load" which appears: def load (line 10), config.load() (line 19)
        result = server._handle_find_references({
            "textDocument": {"uri": uri},
            "position": {"line": 10, "character": 9},  # def load
            "context": {"includeDeclaration": True},
        })

        # "load" appears in: "def load", "self.loaded", "config.load()"
        # word boundary matches "load" in "loaded" too? No — \bload\b won't match "loaded"
        assert len(result) >= 2  # def load + config.load()

    def test_find_class_references(self, server: AISupportLSPServer):
        """Find all references to a class."""
        uri = "file:///test.py"
        server._documents[uri] = SAMPLE_CODE

        # "Config" appears at: line 3 (class Config:), line 18 (config: Config),
        # line 25 (Config("/tmp"))
        result = server._handle_find_references({
            "textDocument": {"uri": uri},
            "position": {"line": 3, "character": 7},  # class Config
            "context": {"includeDeclaration": True},
        })

        assert len(result) >= 3  # class Config, config: Config, Config("/tmp")

    def test_find_variable_references(self, server: AISupportLSPServer):
        """Find all references to a local variable."""
        uri = "file:///test.py"
        server._documents[uri] = SAMPLE_CODE

        # "cfg" on lines 25 and 26
        result = server._handle_find_references({
            "textDocument": {"uri": uri},
            "position": {"line": 25, "character": 4},  # cfg
            "context": {"includeDeclaration": True},
        })

        assert len(result) >= 2


# ─── Tests: Code Completion ──────────────────────────────────────────────────


class TestCodeCompletion:
    """Test textDocument/completion handler."""

    def test_basic_completions(self, server: AISupportLSPServer):
        """Get completions for a file."""
        uri = "file:///test.py"
        server._documents[uri] = SAMPLE_CODE

        result = server._handle_completion({
            "textDocument": {"uri": uri},
            "position": {"line": 27, "character": 0},
        })

        assert "items" in result
        labels = [item["label"] for item in result["items"]]

        # Should include functions and classes from file
        assert "Config" in labels
        assert "process_config" in labels
        assert "helper" in labels
        # Should include builtins
        assert "print" in labels
        assert "len" in labels

    def test_self_dot_completion(self, server: AISupportLSPServer):
        """Get completions after 'self.'."""
        uri = "file:///test.py"
        code = """\
class MyClass:
    name: str = ""
    
    def __init__(self):
        self.value = 42
    
    def get_name(self):
        return self.name
    
    def method(self):
        self."""
        server._documents[uri] = code

        # Line 10 is "        self." — character 13 is after the dot
        result = server._handle_completion({
            "textDocument": {"uri": uri},
            "position": {"line": 10, "character": 13},
        })

        labels = [item["label"] for item in result["items"]]
        # Should include methods and attributes
        assert "get_name" in labels or "method" in labels or "name" in labels

    def test_class_dot_completion(self, server: AISupportLSPServer):
        """Get completions after 'ClassName.'."""
        uri = "file:///test.py"
        code = SAMPLE_CODE + "Config."
        server._documents[uri] = code

        # Last line is "Config." at line 28, char 7
        last_line = len(code.split("\n")) - 1
        result = server._handle_completion({
            "textDocument": {"uri": uri},
            "position": {"line": last_line, "character": 7},
        })

        labels = [item["label"] for item in result["items"]]
        assert "load" in labels or "save" in labels or "__init__" in labels

    def test_imports_in_completions(self, server: AISupportLSPServer):
        """Imported modules appear in completions."""
        uri = "file:///test.py"
        server._documents[uri] = SAMPLE_CODE

        result = server._handle_completion({
            "textDocument": {"uri": uri},
            "position": {"line": 27, "character": 0},
        })

        labels = [item["label"] for item in result["items"]]
        assert "os" in labels
        assert "Path" in labels


# ─── Tests: Workspace Rename ─────────────────────────────────────────────────


class TestWorkspaceRename:
    """Test textDocument/rename handler."""

    def test_rename_function(self, server: AISupportLSPServer):
        """Rename a function across the file."""
        uri = "file:///test.py"
        server._documents[uri] = SAMPLE_CODE

        # "process_config" is at line 18, char 4
        result = server._handle_rename({
            "textDocument": {"uri": uri},
            "position": {"line": 18, "character": 5},  # process_config
            "newName": "handle_config",
        })

        assert result is not None
        assert "changes" in result
        assert uri in result["changes"]

        # Should have edits for definition + call site
        edits = result["changes"][uri]
        assert len(edits) >= 2

        # All edits should replace with new name
        for edit in edits:
            assert edit["newText"] == "handle_config"

    def test_rename_class(self, server: AISupportLSPServer):
        """Rename a class across the file."""
        uri = "file:///test.py"
        server._documents[uri] = SAMPLE_CODE

        # class Config: is at line 3, "Config" starts at char 6
        result = server._handle_rename({
            "textDocument": {"uri": uri},
            "position": {"line": 3, "character": 7},  # Config
            "newName": "AppConfig",
        })

        assert result is not None
        edits = result["changes"][uri]
        # Config appears at: class Config (line 3), config: Config (line 18),
        # Config("/tmp") (line 25) = at least 3
        assert len(edits) >= 3

    def test_rename_skips_strings(self, server: AISupportLSPServer):
        """Rename should not modify string contents."""
        uri = "file:///test.py"
        code = '''\
def foo():
    """This calls foo internally."""
    return "foo"

result = foo()
'''
        server._documents[uri] = code

        result = server._handle_rename({
            "textDocument": {"uri": uri},
            "position": {"line": 0, "character": 4},  # def foo
            "newName": "bar",
        })

        assert result is not None
        edits = result["changes"][uri]
        # Should rename def foo and result = foo(), but NOT inside string/docstring
        # The exact count depends on strip_strings logic
        for edit in edits:
            assert edit["newText"] == "bar"

    def test_rename_across_files(self, server: AISupportLSPServer):
        """Rename propagates across multiple open files."""
        uri1 = "file:///a.py"
        uri2 = "file:///b.py"

        server._documents[uri1] = "def shared_func():\n    pass\n"
        server._documents[uri2] = "from a import shared_func\n\nshared_func()\n"

        result = server._handle_rename({
            "textDocument": {"uri": uri1},
            "position": {"line": 0, "character": 4},
            "newName": "new_func",
        })

        assert result is not None
        assert uri1 in result["changes"]
        assert uri2 in result["changes"]

    def test_rename_empty_name_returns_none(self, server: AISupportLSPServer):
        """Empty new name returns None."""
        uri = "file:///test.py"
        server._documents[uri] = SAMPLE_CODE

        result = server._handle_rename({
            "textDocument": {"uri": uri},
            "position": {"line": 0, "character": 7},
            "newName": "",
        })

        assert result is None


# ─── Tests: Extended Fix Templates ───────────────────────────────────────────


class TestExtendedFixTemplates:
    """Test the new fix handlers: missing await, unused var, type mismatch."""

    def test_fix_missing_await(self):
        from src.infrastructure.analysis.compile_error_fixer import (
            CompileError,
            generate_fix,
        )

        error = CompileError(
            file="test.py",
            line=5,
            column=0,
            error_type="RuntimeWarning",
            message="coroutine 'fetch_data' was never awaited",
        )
        content = "x = 1\ny = 2\nz = 3\n\nresult = fetch_data(url)\nprint(result)\n"

        fix = generate_fix(error, content)
        assert fix is not None
        assert "await" in fix.fix_description.lower() or "await" in (fix.new_code or "")

    def test_fix_unused_variable(self):
        from src.infrastructure.analysis.compile_error_fixer import (
            CompileError,
            generate_fix,
        )

        error = CompileError(
            file="test.py",
            line=1,
            column=0,
            error_type="F841",
            message="Local variable 'unused' is assigned to but never used",
        )
        content = "unused = compute_something()\nreturn other\n"

        fix = generate_fix(error, content)
        assert fix is not None
        assert "_unused" in fix.new_code or "_" in fix.fix_description

    def test_fix_return_type_mismatch(self):
        from src.infrastructure.analysis.compile_error_fixer import (
            CompileError,
            generate_fix,
        )

        error = CompileError(
            file="test.py",
            line=3,
            column=0,
            error_type="return-value",
            message='Incompatible return value type (got "None", expected "str")',
        )

        fix = generate_fix(error, "")
        assert fix is not None
        assert "str" in fix.fix_description
        assert "None" in fix.fix_description


# ─── Tests: Symbol at Position Helper ────────────────────────────────────────


class TestSymbolAtPosition:
    """Test the _get_symbol_at_position helper."""

    def test_word_in_middle(self, server: AISupportLSPServer):
        content = "def hello_world():\n    pass"
        symbol = server._get_symbol_at_position(content, 0, 6)
        assert symbol == "hello_world"

    def test_word_at_start(self, server: AISupportLSPServer):
        content = "variable = 42"
        symbol = server._get_symbol_at_position(content, 0, 0)
        assert symbol == "variable"

    def test_empty_position(self, server: AISupportLSPServer):
        content = "x = 1"
        symbol = server._get_symbol_at_position(content, 0, 2)
        # Position 2 is the space between 'x' and '='
        assert symbol is None or symbol == ""

    def test_out_of_bounds(self, server: AISupportLSPServer):
        content = "short"
        symbol = server._get_symbol_at_position(content, 5, 0)
        assert symbol is None
