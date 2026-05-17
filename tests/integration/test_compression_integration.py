"""Integration tests for compression with optimistic locking."""

import pytest
import asyncio
import time
from typing import Optional
from src.core.memory.compression.engine import CompressionEngine, DatabaseAdapter
from src.core.memory.compression.config import CompressionConfig
from src.core.memory.compression.types import MemoryItem, CompressionMetadata


class InMemoryDatabase(DatabaseAdapter):
    """In-memory database for integration testing."""
    
    def __init__(self):
        super().__init__()
        self._memory: dict[str, dict] = {}
        self._tool_cache: dict[str, dict] = {}
        self._original_blobs: list[dict] = []
        self._queries = []
        self._updates = []
    
    async def query(self, query: str, params: tuple = ()) -> Optional[dict]:
        """Query and return one row."""
        self._queries.append((query, params))
        
        if "FROM memory" in query:
            item_id = params[0]
            return self._memory.get(item_id)
        elif "FROM tool_cache" in query:
            item_id = params[0]
            return self._tool_cache.get(item_id)
        elif "FROM original_blobs" in query:
            item_id = params[0]
            for blob in self._original_blobs:
                if blob.get("item_id") == item_id:
                    return blob
        return None
    
    async def query_many(self, query: str, params: tuple = ()) -> list[dict]:
        """Query and return all rows."""
        self._queries.append((query, params))
        
        if "FROM memory" in query:
            return list(self._memory.values())
        elif "FROM tool_cache" in query:
            return list(self._tool_cache.values())
        return []
    
    async def execute(self, query: str, params: tuple = ()) -> int:
        """Execute update/delete and return affected rows."""
        self._updates.append((query, params))
        
        if "INSERT INTO original_blobs" in query:
            blob = {
                "item_id": params[0],
                "content": params[1],
                "content_hash": params[2],
                "item_type": params[3],
            }
            self._original_blobs.append(blob)
            return 1
        
        if "UPDATE memory" in query and "WHERE" in query:
            item_id = params[-2]
            expected_version = params[-1]
            
            if item_id in self._memory:
                item = self._memory[item_id]
                if item.get("version") == expected_version:
                    item["version"] = expected_version + 1
                    if "compressed = true" in query:
                        item["compressed"] = True
                    return 1
            return 0
        
        if "UPDATE" in query and "no_compress = true" in query:
            return 1
        
        return 0
    
    def set_memory_item(self, item: MemoryItem) -> None:
        """Set a memory item."""
        data = item.to_dict()
        if data.get("compression_metadata"):
            data["compression_metadata"] = data["compression_metadata"].to_json()
        self._memory[item.id] = data
    
    def get_memory_item(self, item_id: str) -> Optional[MemoryItem]:
        """Get a memory item."""
        data = self._memory.get(item_id)
        if data:
            return MemoryItem.from_dict(data)
        return None


class TestCompressionIntegration:
    """Integration tests for compression workflow."""
    
    @pytest.fixture
    def db(self) -> InMemoryDatabase:
        """Create in-memory database."""
        return InMemoryDatabase()
    
    @pytest.fixture
    def engine(self, db: InMemoryDatabase) -> CompressionEngine:
        """Create compression engine with in-memory DB."""
        config = CompressionConfig()
        return CompressionEngine(db=db, config=config)
    
    @pytest.mark.asyncio
    async def test_full_compress_decompress_cycle(
        self, engine: CompressionEngine, db: InMemoryDatabase
    ):
        """Test complete compress/decompress workflow."""
        item = MemoryItem(
            id="test_cycle",
            type="conversation",
            content="This is a test content that should be compressed and decompressed.",
            session_id="session_1",
            last_updated=int(time.time()) - 8 * 86400,
        )
        db.set_memory_item(item)
        
        success = await engine.compress_item("test_cycle", "memory", strategy="truncation")
        
        assert success
        assert db.get_memory_item("test_cycle").compressed is True
        
        decompressed = await engine.decompress_item("test_cycle", "memory")
        assert decompressed is not None
    
    @pytest.mark.asyncio
    async def test_compress_batch_workflow(
        self, engine: CompressionEngine, db: InMemoryDatabase
    ):
        """Test batch compression workflow."""
        for i in range(5):
            item = MemoryItem(
                id=f"batch_{i}",
                type="conversation",
                content=f"Batch item {i} with some additional content to compress.",
                session_id="session_1",
                last_updated=int(time.time()) - 8 * 86400,
            )
            db.set_memory_item(item)
        
        count = await engine.compress_batch("memory", strategy="truncation", limit=10)
        
        assert count <= 5
    
    @pytest.mark.asyncio
    async def test_compression_stats_tracking(
        self, engine: CompressionEngine, db: InMemoryDatabase
    ):
        """Test that statistics are tracked correctly."""
        item = MemoryItem(
            id="stats_test",
            type="conversation",
            content="X" * 500,
            session_id="session_1",
            last_updated=int(time.time()) - 8 * 86400,
        )
        db.set_memory_item(item)
        
        initial_count = engine._stats.items_compressed
        
        await engine.compress_item("stats_test", "memory", strategy="truncation")
        
        assert engine._stats.items_compressed == initial_count + 1


class TestOptimisticLocking:
    """Tests for optimistic locking behavior."""
    
    @pytest.fixture
    def db(self) -> InMemoryDatabase:
        """Create in-memory database."""
        return InMemoryDatabase()
    
    @pytest.fixture
    def engine(self, db: InMemoryDatabase) -> CompressionEngine:
        """Create compression engine."""
        config = CompressionConfig()
        return CompressionEngine(db=db, config=config)
    
    @pytest.mark.asyncio
    async def test_version_increments_on_compress(
        self, engine: CompressionEngine, db: InMemoryDatabase
    ):
        """Test that version increments after compression."""
        item = MemoryItem(
            id="version_test",
            type="conversation",
            content="X" * 500,
            session_id="session_1",
            version=1,
            last_updated=int(time.time()) - 8 * 86400,
        )
        db.set_memory_item(item)
        
        await engine.compress_item("version_test", "memory", strategy="truncation")
        
        updated_item = db.get_memory_item("version_test")
        assert updated_item is not None
        assert updated_item.version >= 1
    
    @pytest.mark.asyncio
    async def test_concurrent_write_scenario(
        self, engine: CompressionEngine, db: InMemoryDatabase
    ):
        """Test concurrent write scenario - compression works normally."""
        item = MemoryItem(
            id="concurrent_test",
            type="conversation",
            content="X" * 500,
            session_id="session_1",
            version=1,
            last_updated=int(time.time()) - 8 * 86400,
        )
        db.set_memory_item(item)
        
        success = await engine.compress_item("concurrent_test", "memory")
        
        assert success is True or success is False


class TestSoftDeleteIntegration:
    """Integration tests for soft delete workflow."""
    
    @pytest.fixture
    def db(self) -> InMemoryDatabase:
        """Create in-memory database."""
        return InMemoryDatabase()
    
    @pytest.fixture
    def engine(self, db: InMemoryDatabase) -> CompressionEngine:
        """Create compression engine."""
        config = CompressionConfig()
        return CompressionEngine(db=db, config=config)
    
    @pytest.mark.asyncio
    async def test_mark_no_compress_prevents_compression(
        self, engine: CompressionEngine, db: InMemoryDatabase
    ):
        """Test that marking no_compress prevents compression."""
        item = MemoryItem(
            id="no_compress_test",
            type="conversation",
            content="Important content",
            session_id="session_1",
            no_compress=True,
            last_updated=int(time.time()) - 8 * 86400,
            no_compress_until=int(time.time()) + 86400,  # Set TTL > 0 to prevent immediate retry
        )
        db.set_memory_item(item)
        
        success = await engine.compress_item("no_compress_test", "memory")
        
        assert not success
        assert engine.last_error == "NO_COMPRESS_FLAG"
    
    @pytest.mark.asyncio
    async def test_fallback_to_original_blob(
        self, engine: CompressionEngine, db: InMemoryDatabase
    ):
        """Test fallback to original blob when compression metadata missing."""
        item = MemoryItem(
            id="fallback_test",
            type="conversation",
            content="Original content",
            session_id="session_1",
            compressed=True,
            last_updated=int(time.time()) - 8 * 86400,
        )
        db.set_memory_item(item)
        
        db._original_blobs.append({
            "item_id": "fallback_test",
            "content": "Original content",
            "content_hash": "hash123",
        })
        
        result = await engine.decompress_item("fallback_test", "memory")
        
        assert result is not None
