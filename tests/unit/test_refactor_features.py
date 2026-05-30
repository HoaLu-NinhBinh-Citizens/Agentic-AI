"""Unit tests for refactoring, snippets, and search features."""
import pytest
import asyncio
from src.interfaces.tui.refactor_panel import (
    RefactorEdit, RefactorKind, RefactorPanel, RefactorPreview,
    RefactorTarget, RenameProvider, ExtractProvider, InlineProvider,
)
from src.interfaces.tui.snippet_system import (
    Snippet, SnippetSystem, TabStop, SnippetVariable,
)
from src.interfaces.tui.search_panel import (
    SearchPanel, SearchQuery, SearchResult,
)


# ─── Refactoring Tests ────────────────────────────────────────────────────────

class TestRefactorTarget:
    def test_creation(self):
        target = RefactorTarget(name="my_func", kind="function", file_path="test.py", line=5, col=0, end_line=5, end_col=8)
        assert target.name == "my_func"
        assert target.kind == "function"


class TestRefactorEdit:
    def test_creation(self):
        edit = RefactorEdit(file_path="test.py", range=(5, 0, 5, 10), old_text="old", new_text="new")
        assert edit.old_text == "old"


class TestRefactorPreview:
    def test_creation(self):
        preview = RefactorPreview(kind=RefactorKind.RENAME, new_name="new_name")
        assert preview.kind == RefactorKind.RENAME
        assert not preview.applied


class TestRenameProvider:
    def setup_method(self):
        self.provider = RenameProvider()

    def test_find_symbol_variable(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("x = 1\ny = x + 1\n", encoding="utf-8")
        # col=0 points to start of "x"
        symbol = self.provider._find_symbol(str(f), 0, 0)
        assert symbol is not None
        assert symbol.name == "x"
        assert symbol.kind == "variable"


class TestRefactorPanel:
    def setup_method(self):
        self.panel = RefactorPanel()

    def test_initial_stats(self):
        stats = self.panel.get_stats()
        assert stats["renames"] == 0
        assert stats["extracts"] == 0

    @pytest.mark.asyncio
    async def test_execute_rename_no_file(self):
        preview = await self.panel.execute_refactor(RefactorKind.RENAME, "nonexistent.py", 0, 0, new_name="new")
        assert preview.error


# ─── Snippet Tests ───────────────────────────────────────────────────────────

class TestTabStop:
    def test_creation(self):
        ts = TabStop(index=1, default="value")
        assert ts.index == 1
        assert ts.default == "value"
        assert ts.choices == []


class TestSnippetVariable:
    def test_creation(self):
        v = SnippetVariable(name="TM_FILENAME", default="test.py")
        assert v.name == "TM_FILENAME"


class TestSnippet:
    def test_parse_tabstops(self):
        s = Snippet(id="t1", prefix="test", body="if $1:\n    $2")
        assert len(s.tabstops) >= 2
        assert s.tabstops[0].index == 1

    def test_parse_tabstops_with_default(self):
        s = Snippet(id="t1", prefix="test", body="def $1($2):\n    $3")
        assert len(s.tabstops) >= 3

    def test_expand_simple(self):
        s = Snippet(id="t1", prefix="test", body="$1 + $2")
        result = s.expand(user_input={1: "a", 2: "b"})
        assert result == "a + b"

    def test_expand_with_default(self):
        s = Snippet(id="t1", prefix="test", body="def ${1:name}(): pass")
        result = s.expand(user_input={})
        assert "name" in result

    def test_expand_no_input(self):
        s = Snippet(id="t1", prefix="test", body="hello $1")
        result = s.expand(user_input={})
        assert "hello" in result


class TestSnippetSystem:
    def setup_method(self):
        self.system = SnippetSystem()

    def test_builtin_snippets(self):
        assert len(self.system._snippets) >= 20

    def test_find_snippet_python(self):
        results = self.system.find_snippet("def", scope="python")
        assert len(results) >= 1

    def test_find_snippet_js(self):
        results = self.system.find_snippet("func", scope="javascript")
        assert len(results) >= 1

    def test_expand_snippet(self):
        result = self.system.expand_snippet("py-def", user_input={1: "my_func"})
        assert "my_func" in result

    def test_stats(self):
        stats = self.system.get_stats()
        assert stats["total_snippets"] >= 20
        assert "python" in stats["by_scope"]


# ─── Search Tests ─────────────────────────────────────────────────────────────

class TestSearchQuery:
    def test_creation(self):
        q = SearchQuery(pattern="test", is_regex=True)
        assert q.pattern == "test"
        assert q.is_regex is True


class TestSearchResult:
    def test_creation(self):
        r = SearchResult(file_path="test.py", line=5, col=0, end_col=4, line_content="test line", match_text="test")
        assert r.file_path == "test.py"
        assert r.line == 5


class TestSearchPanel:
    def setup_method(self):
        self.panel = SearchPanel()

    def test_get_history(self):
        assert isinstance(self.panel.get_history(), list)

    def test_stats(self):
        stats = self.panel.get_stats()
        assert "searches" in stats
        assert "results_found" in stats

    @pytest.mark.asyncio
    async def test_search_in_file(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("def test():\n    pass\n", encoding="utf-8")
        query = SearchQuery(pattern="test")
        results = await self.panel.search(query, paths=[str(tmp_path)])
        assert len(results) >= 1
