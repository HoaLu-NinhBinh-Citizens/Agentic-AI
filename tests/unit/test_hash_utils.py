"""Unit tests for hash utilities."""
import pytest

from src.infrastructure.indexing.hash_utils import (
    compute_content_hash,
    compute_file_hash,
    compute_short_hash,
)


class TestComputeContentHash:
    def test_same_content_same_hash(self):
        content = "def foo():\n    pass\n"
        h1 = compute_content_hash(content)
        h2 = compute_content_hash(content)
        assert h1 == h2

    def test_different_content_different_hash(self):
        h1 = compute_content_hash("def foo():\n    pass\n")
        h2 = compute_content_hash("def bar():\n    pass\n")
        assert h1 != h2

    def test_hash_length(self):
        h = compute_content_hash("test")
        assert len(h) == 64  # SHA256 produces 64 hex chars

    def test_empty_content(self):
        h = compute_content_hash("")
        assert len(h) == 64

    def test_unicode_content(self):
        h = compute_content_hash("def 日本語():\n    pass\n")
        assert len(h) == 64


class TestComputeShortHash:
    def test_same_content_same_hash(self):
        content = "def foo():\n    pass\n"
        h1 = compute_short_hash(content)
        h2 = compute_short_hash(content)
        assert h1 == h2

    def test_different_content_different_hash(self):
        h1 = compute_short_hash("def foo():\n    pass\n")
        h2 = compute_short_hash("def bar():\n    pass\n")
        assert h1 != h2

    def test_hash_length(self):
        h = compute_short_hash("test")
        assert len(h) == 24  # Short hash is 24 chars


class TestComputeFileHash:
    def test_nonexistent_file_returns_empty(self):
        h = compute_file_hash("/nonexistent/file/12345.py")
        assert h == ""

    def test_existing_file(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("def foo():\n    pass\n", encoding="utf-8")
        h = compute_file_hash(str(f))
        assert len(h) == 64
        assert h != ""

    def test_file_hash_matches_content_hash(self, tmp_path):
        content = "def foo():\n    pass\n"
        f = tmp_path / "test.py"
        f.write_text(content, encoding="utf-8")
        # File hash should match content hash of what was written
        file_hash = compute_file_hash(str(f))
        assert file_hash == compute_content_hash(content)
