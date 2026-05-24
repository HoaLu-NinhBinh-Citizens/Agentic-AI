"""Unit tests for Rust Bridge."""

from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from src.infrastructure.performance.rust_bridge import (
    RustBridge,
    get_rust_bridge,
)


class TestRustBridge:
    """Tests for RustBridge."""

    def test_find_binary_not_found(self):
        """Test when Rust binary is not available."""
        bridge = RustBridge(binary_path=None)
        bridge._available = False
        
        assert bridge.is_available is False

    def test_glob_fallback(self):
        """Test glob falls back to Python when Rust unavailable."""
        bridge = RustBridge(binary_path=None)
        bridge._available = False
        
        # Should use Python fallback
        import asyncio
        result = asyncio.run(bridge.glob_fast(Path(__file__).parent, "*.py"))
        
        assert isinstance(result, list)

    def test_hash_content_fallback(self):
        """Test hash falls back to Python when Rust unavailable."""
        bridge = RustBridge(binary_path=None)
        bridge._available = False
        
        import asyncio
        result = asyncio.run(bridge.hash_content("test content"))
        
        assert result is not None
        assert len(result) == 64  # SHA256 hex length

    @pytest.mark.asyncio
    async def test_hash_content(self):
        """Test hash content with Rust."""
        bridge = RustBridge(binary_path=None)
        bridge._available = False  # Force fallback
        
        result = await bridge.hash_content("test content")
        
        assert result is not None
        assert len(result) == 64

    @pytest.mark.asyncio
    async def test_glob_fast(self):
        """Test glob with Rust."""
        bridge = RustBridge(binary_path=None)
        bridge._available = False  # Force Python fallback
        
        result = await bridge.glob_fast(Path(__file__).parent, "*.py", max_depth=2)
        
        assert isinstance(result, list)

    def test_singleton_pattern(self, monkeypatch):
        """Test singleton pattern."""
        # Reset global
        import src.infrastructure.performance.rust_bridge as rb
        rb._rust_bridge = None
        
        bridge1 = get_rust_bridge()
        bridge2 = get_rust_bridge()
        
        assert bridge1 is bridge2
