"""Unit tests for background worker."""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from src.core.memory.compression.worker import CompressionWorker, RateLimiter
from src.core.memory.compression.engine import CompressionEngine
from src.core.memory.compression.config import CompressionConfig, WorkerConfig


class TestRateLimiter:
    """Test suite for RateLimiter."""
    
    @pytest.fixture
    def limiter(self) -> RateLimiter:
        """Create a rate limiter."""
        return RateLimiter(items_per_second=10.0, burst_size=5)
    
    @pytest.mark.asyncio
    async def test_initial_tokens(self, limiter: RateLimiter):
        """Test initial token count."""
        acquired = 0
        for _ in range(5):
            if await limiter.try_acquire():
                acquired += 1
        
        assert acquired == 5
    
    @pytest.mark.asyncio
    async def test_burst_limit(self, limiter: RateLimiter):
        """Test burst limit enforcement."""
        acquired = 0
        for _ in range(10):
            if await limiter.try_acquire():
                acquired += 1
        
        assert acquired == 5
    
    @pytest.mark.asyncio
    async def test_acquire_with_wait(self, limiter: RateLimiter):
        """Test acquire with waiting."""
        limiter._tokens = 0
        limiter._rate = 100
        
        acquired = await limiter.acquire(timeout=0.2)
        
        assert acquired is True
    
    @pytest.mark.asyncio
    async def test_acquire_timeout(self, limiter: RateLimiter):
        """Test acquire timeout."""
        limiter._tokens = 0
        limiter._rate = 0.1
        
        acquired = await limiter.acquire(timeout=0.05)
        
        assert acquired is False


class TestCompressionWorker:
    """Test suite for CompressionWorker."""
    
    @pytest.fixture
    def mock_engine(self) -> MagicMock:
        """Create mock compression engine."""
        engine = MagicMock(spec=CompressionEngine)
        engine._config = CompressionConfig()
        engine._db = MagicMock()
        engine._stats = MagicMock()
        engine._stats.to_dict.return_value = {}
        engine._stats.items_skipped_version_mismatch = 0
        engine.last_error = None
        return engine
    
    @pytest.fixture
    def worker(self, mock_engine: MagicMock) -> CompressionWorker:
        """Create compression worker."""
        config = WorkerConfig(
            interval_seconds=1,
            batch_size=10,
            rate_limit_items_per_second=100,
        )
        return CompressionWorker(engine=mock_engine, config=config)
    
    @pytest.mark.asyncio
    async def test_worker_initialization(self, worker: CompressionWorker):
        """Test worker initialization."""
        assert worker._config is not None
        assert worker._rate_limiter is not None
        assert not worker.is_running
    
    @pytest.mark.asyncio
    async def test_start_stop(self, worker: CompressionWorker):
        """Test starting and stopping worker."""
        await worker.start()
        assert worker.is_running
        
        await worker.stop()
        assert not worker.is_running
    
    @pytest.mark.asyncio
    async def test_run_once(self, worker: CompressionWorker, mock_engine: MagicMock):
        """Test running one compression cycle."""
        mock_engine._db.query_many = AsyncMock(return_value=[])
        
        count = await worker.run_once()
        
        assert count == 0
    
    @pytest.mark.asyncio
    async def test_get_stats(self, worker: CompressionWorker):
        """Test getting worker stats."""
        stats = worker.get_stats()
        
        assert "running" in stats
        assert "items_processed" in stats
        assert "config" in stats
        assert "engine_stats" in stats
    
    @pytest.mark.asyncio
    async def test_shutdown_during_run(self, worker: CompressionWorker):
        """Test shutdown during run."""
        await worker.start()
        
        worker._shutdown = True
        
        await worker.stop()
        
        assert not worker.is_running


class TestCompressionWorkerScan:
    """Test suite for worker scanning."""
    
    @pytest.fixture
    def mock_engine(self) -> MagicMock:
        """Create mock engine with DB."""
        engine = MagicMock(spec=CompressionEngine)
        engine._config = CompressionConfig()
        engine._db = MagicMock()
        engine._stats = MagicMock()
        engine._stats.to_dict.return_value = {}
        engine._stats.items_skipped_version_mismatch = 0
        engine.last_error = "VERSION_MISMATCH"
        engine.compress_item = AsyncMock(return_value=False)
        return engine
    
    @pytest.mark.asyncio
    async def test_scan_finds_items(
        self, mock_engine: MagicMock
    ):
        """Test scanning finds compressible items."""
        items = [
            {"id": "item1", "session_id": "s1", "content": "test"},
            {"id": "item2", "session_id": "s1", "content": "test2"},
        ]
        mock_engine._db.query_many = AsyncMock(return_value=items)
        
        config = WorkerConfig(batch_size=10)
        worker = CompressionWorker(engine=mock_engine, config=config)
        
        await worker._scan_and_compress()
        
        assert mock_engine._db.query_many.called
    
    @pytest.mark.asyncio
    async def test_version_mismatch_tracking(
        self, mock_engine: MagicMock
    ):
        """Test version mismatch tracking."""
        mock_engine._db.query_many = AsyncMock(return_value=[])
        
        config = WorkerConfig()
        worker = CompressionWorker(engine=mock_engine, config=config)
        
        await worker.run_once()
        
        assert mock_engine._stats.items_skipped_version_mismatch == 0
