"""Unit tests for compression engine."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from src.core.memory.compression.engine import CompressionEngine, DatabaseAdapter
from src.core.memory.compression.config import CompressionConfig
from src.core.memory.compression.types import MemoryItem


class MockDatabase(DatabaseAdapter):
    """Mock database for testing."""
    
    def __init__(self):
        super().__init__()
        self._data = {}
        self._version = {}
    
    async def query(self, query: str, params: tuple = ()) -> dict | None:
        item_id = params[0]
        return self._data.get(item_id)
    
    async def query_many(self, query: str, params: tuple = ()) -> list[dict]:
        return list(self._data.values())
    
    async def execute(self, query: str, params: tuple = ()) -> int:
        if "UPDATE" in query and "no_compress = true" in query:
            item_id = params[0]
            if item_id in self._data:
                self._data[item_id]["no_compress"] = True
                return 1
            return 0
        
        if "UPDATE" in query and "compressed = true" in query:
            item_id = params[-2]
            expected_version = params[-1]
            
            if item_id in self._data:
                if self._version.get(item_id, 1) == expected_version:
                    self._version[item_id] = expected_version + 1
                    return 1
            return 0
        return 0
    
    def set_item(self, item: MemoryItem):
        self._data[item.id] = item.to_dict()
        self._version[item.id] = item.version


class TestCompressionEngine:
    """Test suite for CompressionEngine."""
    
    @pytest.fixture
    def engine(self) -> CompressionEngine:
        """Create a compression engine."""
        config = CompressionConfig()
        return CompressionEngine(config=config)
    
    @pytest.fixture
    def engine_with_db(self) -> tuple[CompressionEngine, MockDatabase]:
        """Create engine with mock database."""
        config = CompressionConfig()
        db = MockDatabase()
        engine = CompressionEngine(db=db, config=config)
        return engine, db
    
    @pytest.mark.asyncio
    async def test_initialization(self, engine: CompressionEngine):
        """Test engine initialization."""
        assert engine._config is not None
        assert "truncation" in engine._strategies
        assert "extractive" in engine._strategies
        assert "kv_compact" in engine._strategies
        assert "adaptive_prune" in engine._strategies
    
    @pytest.mark.asyncio
    async def test_get_strategy(self, engine: CompressionEngine):
        """Test getting registered strategy."""
        strategy = engine.get_strategy("truncation")
        assert strategy is not None
        assert strategy.name == "truncation"
    
    @pytest.mark.asyncio
    async def test_get_unknown_strategy(self, engine: CompressionEngine):
        """Test getting unknown strategy raises error."""
        from src.core.memory.compression.strategies.base import StrategyNotFoundError
        
        with pytest.raises(StrategyNotFoundError):
            engine.get_strategy("unknown_strategy")
    
    @pytest.mark.asyncio
    async def test_register_strategy(self, engine: CompressionEngine):
        """Test registering a new strategy."""
        mock_strategy = MagicMock()
        mock_strategy.name = "custom_strategy"
        
        await engine.register_strategy("custom", mock_strategy)
        
        assert "custom" in engine._strategies
        assert engine.get_strategy("custom") == mock_strategy
    
    @pytest.mark.asyncio
    async def test_compress_item_not_found(
        self, engine_with_db: tuple[CompressionEngine, MockDatabase]
    ):
        """Test compress item when not found."""
        engine, _ = engine_with_db
        result = await engine.compress_item("nonexistent", "memory")
        
        assert result is False
        assert engine.last_error == "ITEM_NOT_FOUND"
    
    @pytest.mark.asyncio
    async def test_compress_item_no_compress_flag(
        self, engine_with_db: tuple[CompressionEngine, MockDatabase]
    ):
        """Test compress item with no_compress flag."""
        engine, db = engine_with_db
        
        item = MemoryItem(
            id="test_no_compress",
            type="conversation",
            content="Protected content",
            session_id="session_1",
            no_compress=True,
        )
        db.set_item(item)
        
        result = await engine.compress_item("test_no_compress", "memory")
        
        assert result is False
        assert engine.last_error == "NO_COMPRESS_FLAG"
    
    @pytest.mark.asyncio
    async def test_compress_item_already_compressed(
        self, engine_with_db: tuple[CompressionEngine, MockDatabase]
    ):
        """Test compress already compressed item."""
        engine, db = engine_with_db
        
        item = MemoryItem(
            id="test_compressed",
            type="conversation",
            content="Already compressed",
            session_id="session_1",
            compressed=True,
        )
        db.set_item(item)
        
        result = await engine.compress_item("test_compressed", "memory")
        
        assert result is False
        assert engine.last_error == "ALREADY_COMPRESSED"
    
    @pytest.mark.asyncio
    async def test_mark_no_compress(
        self, engine_with_db: tuple[CompressionEngine, MockDatabase]
    ):
        """Test marking item as no_compress."""
        engine, db = engine_with_db
        
        item = MemoryItem(
            id="test_mark",
            type="conversation",
            content="Content",
            session_id="session_1",
        )
        db.set_item(item)
        
        await engine.mark_no_compress("test_mark", "memory")
        
        updated = db._data.get("test_mark")
        assert updated is not None
    
    @pytest.mark.asyncio
    async def test_get_stats(self, engine: CompressionEngine):
        """Test getting statistics."""
        stats = await engine.get_stats()
        
        assert "items_compressed" in stats
        assert "compression_ratio_avg" in stats
        assert "semantic_similarity_avg" in stats
    
    @pytest.mark.asyncio
    async def test_decompress_item_not_found(
        self, engine_with_db: tuple[CompressionEngine, MockDatabase]
    ):
        """Test decompress item not found."""
        engine, _ = engine_with_db
        
        result = await engine.decompress_item("nonexistent", "memory")
        
        assert result is None


class TestCompressionEngineBatch:
    """Test suite for batch compression."""
    
    @pytest.fixture
    def engine_with_db(self) -> tuple[CompressionEngine, MockDatabase]:
        config = CompressionConfig()
        db = MockDatabase()
        engine = CompressionEngine(db=db, config=config)
        return engine, db
    
    @pytest.mark.asyncio
    async def test_compress_batch_no_db(
        self, engine_with_db: tuple[CompressionEngine, MockDatabase]
    ):
        """Test batch compression with no database."""
        engine, _ = engine_with_db
        engine._db = None
        
        count = await engine.compress_batch("memory")
        
        assert count == 0
