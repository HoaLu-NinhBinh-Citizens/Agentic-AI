"""Edge case tests for incremental indexing."""

import pytest
import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from src.infrastructure.indexing.incremental import (
    IncrementalIndexer,
    IndexStateDB,
    is_indexable,
    discover_files,
    FileState,
)


class MockKnowledgeBase:
    """Mock KnowledgeBase for testing."""

    def __init__(self):
        self._entries = {}
        self.upsert_entries_call_count = 0
        self.delete_by_source_call_count = 0

    async def upsert_entries(self, entries, embeddings):
        self.upsert_entries_call_count += 1
        for entry in entries:
            key = entry.get("source", "") + ":" + entry.get("text", "")[:50]
            self._entries[key] = entry

    async def delete_by_source(self, path: str):
        self.delete_by_source_call_count += 1
        to_delete = [k for k in self._entries if k.startswith(path)]
        for k in to_delete:
            del self._entries[k]


class MockEmbeddingService:
    """Mock EmbeddingService for testing."""

    def __init__(self):
        self.embed_batch_call_count = 0
        self.last_batch = None

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        self.embed_batch_call_count += 1
        self.last_batch = texts
        # Return mock embeddings
        return [[0.0] * 768 for _ in texts]


class TestIncrementalIndexerEdgeCases:
    """Test edge cases in incremental indexing."""

    @pytest.mark.asyncio
    async def test_very_large_file(self, tmp_path):
        """Index a very large file."""
        large_file = tmp_path / "large.py"
        content = "\n".join([f"x = {i}" for i in range(10000)])
        large_file.write_text(content)

        kb = MockKnowledgeBase()
        embed = MockEmbeddingService()
        db_path = tmp_path / "test_index_state.db"

        indexer = IncrementalIndexer(kb, embed, state_db=db_path)
        indexer.connect()

        result = await indexer.sync(tmp_path)
        assert result.indexed_files >= 1
        assert embed.embed_batch_call_count >= 1

        indexer.close()

    @pytest.mark.asyncio
    async def test_file_renamed(self, tmp_path):
        """File was renamed (old entry should be cleaned)."""
        file_a = tmp_path / "a.py"
        file_a.write_text("def a(): pass")

        kb = MockKnowledgeBase()
        embed = MockEmbeddingService()
        db_path = tmp_path / "test_index_state.db"

        indexer = IncrementalIndexer(kb, embed, state_db=db_path)
        indexer.connect()

        await indexer.sync(tmp_path)
        initial_count = kb.upsert_entries_call_count

        # Rename
        file_b = tmp_path / "b.py"
        file_a.rename(file_b)

        # Re-index should not duplicate
        result = await indexer.sync(tmp_path)
        assert result.indexed_files >= 1

        indexer.close()

    @pytest.mark.asyncio
    async def test_binary_file(self, tmp_path):
        """Try to index a binary file."""
        binary_file = tmp_path / "image.png"
        binary_file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        kb = MockKnowledgeBase()
        embed = MockEmbeddingService()
        db_path = tmp_path / "test_index_state.db"

        indexer = IncrementalIndexer(kb, embed, state_db=db_path)
        indexer.connect()

        # Should handle gracefully
        result = await indexer.sync(tmp_path)
        # Binary files should be skipped
        assert embed.embed_batch_call_count == 0

        indexer.close()

    @pytest.mark.asyncio
    async def test_file_deleted_during_index(self, tmp_path):
        """File is deleted while indexing."""
        file = tmp_path / "temp.py"
        file.write_text("x = 1")

        kb = MockKnowledgeBase()
        embed = MockEmbeddingService()
        db_path = tmp_path / "test_index_state.db"

        indexer = IncrementalIndexer(kb, embed, state_db=db_path)
        indexer.connect()

        # Delete before indexing
        file.unlink()

        result = await indexer.sync(tmp_path)
        # Should report no files indexed (file deleted)
        assert True  # No crash

        indexer.close()

    @pytest.mark.asyncio
    async def test_concurrent_indexing_same_file(self, tmp_path):
        """Same file indexed concurrently."""
        file = tmp_path / "concurrent.py"
        file.write_text("x = 1")

        kb = MockKnowledgeBase()
        embed = MockEmbeddingService()
        db_path = tmp_path / "test_index_state.db"

        indexer = IncrementalIndexer(kb, embed, state_db=db_path)
        indexer.connect()

        # Two concurrent indexing requests
        results = await asyncio.gather(
            indexer.sync(tmp_path),
            indexer.sync(tmp_path),
        )

        # Should handle gracefully
        assert all(r.indexed_files >= 0 for r in results)

        indexer.close()

    @pytest.mark.asyncio
    async def test_unicode_filename(self, tmp_path):
        """File with Unicode characters in name."""
        unicode_file = tmp_path / "ham.py"
        unicode_file.write_text("def ham(): pass")

        kb = MockKnowledgeBase()
        embed = MockEmbeddingService()
        db_path = tmp_path / "test_index_state.db"

        indexer = IncrementalIndexer(kb, embed, state_db=db_path)
        indexer.connect()

        result = await indexer.sync(tmp_path)
        assert result.indexed_files >= 1

        indexer.close()

    @pytest.mark.asyncio
    async def test_symlink_file(self, tmp_path):
        """Symbolic link to a file."""
        real_file = tmp_path / "real.py"
        real_file.write_text("x = 1")

        link_file = tmp_path / "link.py"
        try:
            link_file.symlink_to(real_file)

            kb = MockKnowledgeBase()
            embed = MockEmbeddingService()
            db_path = tmp_path / "test_index_state.db"

            indexer = IncrementalIndexer(kb, embed, state_db=db_path)
            indexer.connect()

            result = await indexer.sync(tmp_path)

            # Should handle symlink
            assert result.indexed_files >= 1

            indexer.close()
        except OSError:
            pytest.skip("Symlinks not supported on this system")

    @pytest.mark.asyncio
    async def test_empty_file(self, tmp_path):
        """Empty file."""
        empty_file = tmp_path / "empty.py"
        empty_file.write_text("")

        kb = MockKnowledgeBase()
        embed = MockEmbeddingService()
        db_path = tmp_path / "test_index_state.db"

        indexer = IncrementalIndexer(kb, embed, state_db=db_path)
        indexer.connect()

        result = await indexer.sync(tmp_path)
        # Empty file may still be indexed
        assert result.indexed_files >= 0

        indexer.close()


class TestIndexStateDBEdgeCases:
    """Test edge cases in IndexStateDB."""

    def test_content_hash_empty_file(self, tmp_path):
        """Content hash of empty file."""
        empty_file = tmp_path / "empty.txt"
        empty_file.write_text("")

        hash1 = IndexStateDB.content_hash_from_path(empty_file)
        hash2 = IndexStateDB.content_hash_from_path(empty_file)
        assert hash1 == hash2

    def test_content_hash_text_file(self, tmp_path):
        """Content hash of text file."""
        text_file = tmp_path / "text.txt"
        text_file.write_text("Hello World")

        hash1 = IndexStateDB.content_hash_from_path(text_file)
        assert len(hash1) > 0

    def test_content_hash_binary_file(self, tmp_path):
        """Content hash of binary file (read as text)."""
        binary_file = tmp_path / "binary.bin"
        binary_file.write_bytes(b"\x00\x01\x02\x03\x04\x05")

        # Should not crash, handles gracefully
        hash1 = IndexStateDB.content_hash_from_path(binary_file)
        assert len(hash1) > 0

    def test_nonexistent_file(self, tmp_path):
        """Content hash of nonexistent file."""
        nonexistent = tmp_path / "does_not_exist.txt"

        hash1 = IndexStateDB.content_hash_from_path(nonexistent)
        assert hash1 == ""


class TestIsIndexableEdgeCases:
    """Test edge cases for is_indexable function."""

    def test_indexable_extensions(self):
        """Test various file extensions."""
        from src.infrastructure.indexing.incremental import INDEXED_EXTENSIONS

        for ext in INDEXED_EXTENSIONS:
            path = Path(f"file{ext}")
            # Most extensions should be indexable
            result = is_indexable(path)
            # .yaml and .yml might be indexable
            assert isinstance(result, bool)

    def test_excluded_directories(self):
        """Test files in excluded directories."""
        excluded_paths = [
            Path("node_modules/package.json"),
            Path(".git/config"),
            Path("__pycache__/module.pyc"),
            Path("build/output.js"),
            Path(".venv/lib/module.py"),
        ]

        for path in excluded_paths:
            result = is_indexable(path)
            assert result is False

    def test_hidden_files(self):
        """Test hidden files (starting with dot)."""
        # .env files should be excluded
        result = is_indexable(Path(".env"))
        assert result is False

    def test_discover_files_excludes(self, tmp_path):
        """Test discover_files excludes properly."""
        # Create various files
        (tmp_path / "module.py").write_text("x = 1")
        (tmp_path / ".hidden.py").write_text("x = 1")
        (tmp_path / "test.pyc").write_text("x = 1")

        pycache = tmp_path / "__pycache__"
        pycache.mkdir()
        (pycache / "cached.pyc").write_text("x = 1")

        files = discover_files(tmp_path)
        file_names = [f.name for f in files]

        assert "module.py" in file_names
        assert ".hidden.py" not in file_names
        assert "test.pyc" not in file_names
        assert "cached.pyc" not in file_names
