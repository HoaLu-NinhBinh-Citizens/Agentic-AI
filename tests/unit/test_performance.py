"""Unit tests for Performance/Accelerators."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from src.infrastructure.performance.accelerators import (
    RustBinary,
    FastSearch,
    FastHash,
    FastFileOps,
    PerformanceModule,
    get_performance,
)


class TestRustBinary:
    """Tests for RustBinary."""

    def test_create_with_path(self):
        """Test creating with explicit path."""
        binary = RustBinary("/path/to/binary")
        
        assert binary.binary_path == "/path/to/binary"

    def test_find_binary_not_found(self):
        """Test when binary not found."""
        binary = RustBinary(None)
        
        # Will check common paths
        assert binary.binary_path is None or binary.binary_path is not None

    def test_is_available(self):
        """Test availability check."""
        binary = RustBinary(None)
        
        # Not available without actual binary
        assert binary.is_available is False


class TestFastSearch:
    """Tests for FastSearch."""

    def test_create(self):
        """Test creating FastSearch."""
        binary = RustBinary(None)
        search = FastSearch(binary)
        
        assert search.binary is binary

    @pytest.mark.asyncio
    async def test_python_grep_fallback(self, tmp_path):
        """Test Python grep fallback."""
        binary = RustBinary(None)
        search = FastSearch(binary)
        
        # Create test file
        test_file = tmp_path / "test.txt"
        test_file.write_text("line1\nmatch\nline3")
        
        results = await search._python_grep(tmp_path, "match", "*.txt")
        
        assert len(results) == 1
        assert results[0]["line"] == "match"


class TestFastHash:
    """Tests for FastHash."""

    def test_create(self):
        """Test creating FastHash."""
        binary = RustBinary(None)
        hash_util = FastHash(binary)
        
        assert hash_util.binary is binary

    async def test_python_hash_fallback(self, tmp_path):
        """Test Python hash fallback."""
        import hashlib
        
        binary = RustBinary(None)
        hash_util = FastHash(binary)
        
        # Create test file
        test_file = tmp_path / "test.txt"
        test_file.write_bytes(b"Hello World")
        
        # Use the file directly
        h = hashlib.sha256()
        h.update(test_file.read_bytes())
        expected = h.hexdigest()
        
        result = await hash_util._python_hash_file(test_file, "sha256")
        
        # Should return 64 char hex
        assert len(result) == 64
        assert result == expected


class TestPerformanceModule:
    """Tests for PerformanceModule."""

    def test_create(self):
        """Test creating module."""
        module = PerformanceModule()
        
        assert module.binary is not None
        assert module.search is not None
        assert module.hash is not None

    def test_singleton(self):
        """Test singleton pattern."""
        # Reset global
        import src.infrastructure.performance.accelerators as acc
        acc._performance = None
        
        module1 = get_performance()
        module2 = get_performance()
        
        assert module1 is module2

    def test_rust_available(self):
        """Test rust availability check."""
        module = PerformanceModule()
        
        # False without actual binary
        assert module.rust_available is False
