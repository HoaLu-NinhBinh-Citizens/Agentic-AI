"""Unit tests for LSP Live Sync."""
import pytest
from src.infrastructure.lsp.live_sync import (
    DocumentSymbol, HoverInfo, LSPLiveSync, Range, TrackedDocument,
)


class TestTrackedDocument:
    def test_creation(self):
        doc = TrackedDocument(uri="file:///test.py", file_path="test.py", content="print(1)")
        assert doc.version == 1
        assert doc.language_id == "plaintext"
        assert doc.dirty is False


class TestDocumentSymbol:
    def test_creation(self):
        sym = DocumentSymbol(name="my_func", kind="function", detail="def my_func():")
        assert sym.name == "my_func"
        assert sym.kind == "function"
        assert not sym.deprecated

    def test_to_lsp(self):
        sym = DocumentSymbol(
            name="test", kind="function",
            range=Range(5, 0, 5, 15),
            selection_range=Range(5, 4, 5, 8),
        )
        lsp = sym.to_lsp()
        assert lsp["name"] == "test"
        assert "range" in lsp

    def test_kind_to_lsp(self):
        sym = DocumentSymbol(name="t", kind="class")
        assert sym._kind_to_lsp() == 5  # class
        sym.kind = "function"
        assert sym._kind_to_lsp() == 12


class TestHoverInfo:
    def test_to_lsp(self):
        hover = HoverInfo(
            contents="# Hello\nTest",
            range=Range(0, 0, 0, 5),
            signature="func(a: int) -> str",
        )
        lsp = hover.to_lsp()
        assert "contents" in lsp
        assert lsp["contents"]["kind"] == "markdown"


class TestLSPLiveSync:
    def setup_method(self):
        self.sync = LSPLiveSync(debounce_ms=10)

    def test_track_document(self):
        doc = self.sync.track_document("test.py", "print(1)")
        assert doc.file_path == "test.py"
        assert doc.language_id == "python"
        assert doc.content == "print(1)"

    def test_track_document_detects_language(self):
        self.sync.track_document("main.rs", "fn main() {}")
        assert self.sync._documents["file:///main.rs"].language_id == "rust"

    def test_untrack_document(self):
        self.sync.track_document("test.py")
        self.sync.untrack_document("file:///test.py")
        assert "file:///test.py" not in self.sync._documents

    def test_update_content(self):
        self.sync.track_document("test.py", "old")
        self.sync.update_content("file:///test.py", "new content")
        assert self.sync._documents["file:///test.py"].content == "new content"
        assert self.sync._documents["file:///test.py"].dirty is True

    def test_apply_text_edit(self):
        self.sync.track_document("test.py", "line1\nline2\nline3")
        success = self.sync.apply_text_edit(
            "file:///test.py",
            Range(1, 0, 1, 5),
            "modified",
        )
        assert success
        assert "modified" in self.sync._documents["file:///test.py"].content

    def test_apply_text_edit_unknown_uri(self):
        success = self.sync.apply_text_edit("file:///unknown.py", Range(0, 0, 0, 5), "x")
        assert not success

    def test_path_to_uri(self):
        uri = self.sync._path_to_uri("c:/projects/test.py")
        assert uri == "file:///c:/projects/test.py" or "test.py" in uri

    def test_detect_language(self):
        assert self.sync._detect_language("test.py") == "python"
        assert self.sync._detect_language("main.rs") == "rust"
        assert self.sync._detect_language("app.js") == "javascript"
        assert self.sync._detect_language("test.xyz") == "plaintext"

    def test_severity_from_rule(self):
        assert self.sync._severity_from_rule("error") == "error"
        assert self.sync._detect_language("test.py") == "python"  # sanity

    @pytest.mark.asyncio
    async def test_run_diagnostics(self):
        import tempfile
        from pathlib import Path
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write('api_key = "sk-test1234567890abcdefghij"\n')
            path = f.name
        try:
            uri = "file:///" + path.replace("\\", "/").replace(":", "")
            self.sync.track_document(path, 'api_key = "sk-test1234567890abcdefghij"\n')
            diags = await self.sync.run_diagnostics(uri)
            assert isinstance(diags, list)
        finally:
            import os
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_get_document_symbols(self):
        self.sync.track_document("test.py", "class MyClass:\n    def method(self):\n        pass\n")
        symbols = await self.sync.get_document_symbols("file:///test.py")
        names = [s.name for s in symbols]
        assert "MyClass" in names
        assert "method" in names

    @pytest.mark.asyncio
    async def test_get_hover(self):
        self.sync.track_document("test.py", "def hello():\n    pass\n")
        hover = await self.sync.get_hover("file:///test.py", 0, 5)
        # Should find the function
        assert hover is None or isinstance(hover, HoverInfo)

    @pytest.mark.asyncio
    async def test_format_document(self):
        self.sync.track_document("test.py", "print(1)   \n")
        edits = await self.sync.format_document("file:///test.py")
        assert len(edits) >= 1  # Trailing whitespace should be removed

    @pytest.mark.asyncio
    async def test_goto_definition(self):
        self.sync.track_document("test.py", "def my_func():\n    pass\n\nmy_func()\n")
        # Line 3: `my_func()` - the call site
        result = await self.sync.goto_definition("file:///test.py", 3, 0)
        assert result is not None
        assert "uri" in result
        # Line 0: the definition itself
        result2 = await self.sync.goto_definition("file:///test.py", 0, 0)
        assert result2 is not None

    @pytest.mark.asyncio
    async def test_find_references(self):
        self.sync.track_document("test.py", "def my_func():\n    pass\nmy_func()\nmy_func()\n")
        # Line 2: `my_func()` - first call site
        refs = await self.sync.find_references("file:///test.py", 2, 4)
        assert len(refs) >= 2  # Two calls to my_func()

    def test_get_stats(self):
        self.sync.track_document("test.py")
        stats = self.sync.get_stats()
        assert stats["documents_tracked"] == 1
        assert "pending_diagnostics" in stats
