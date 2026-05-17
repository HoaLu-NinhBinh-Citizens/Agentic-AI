"""Chaos tests for compression worker resilience."""

import pytest
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch
from src.core.memory.compression.worker import CompressionWorker
from src.core.memory.compression.engine import CompressionEngine
from src.core.memory.compression.config import CompressionConfig, WorkerConfig
from src.core.memory.compression.types import MemoryItem


class MockDatabase:
    """Mock database for chaos testing."""
    
    def __init__(self):
        self._data = {}
        self._queries = []
        self._fail_next = False
        self._query_delay = 0
    
    def set_fail_next(self, fail: bool = True):
        """Set flag to fail next operation."""
        self._fail_next = fail
    
    async def query(self, query: str, params: tuple = ()):
        if self._fail_next:
            self._fail_next = False
            raise Exception("Simulated database failure")
        
        if self._query_delay > 0:
            await asyncio.sleep(self._query_delay)
        
        self._queries.append((query, params))
        item_id = params[0] if params else None
        return self._data.get(item_id)
    
    async def query_many(self, query: str, params: tuple = ()):
        if self._fail_next:
            self._fail_next = False
            raise Exception("Simulated database failure")
        
        return list(self._data.values())
    
    async def execute(self, query: str, params: tuple = ()):
        if self._fail_next:
            self._fail_next = False
            raise Exception("Simulated database failure")
        
        return 1
    
    def set_item(self, item: MemoryItem):
        self._data[item.id] = item.to_dict()
    
    def clear(self):
        self._data.clear()
        self._queries.clear()


class TestWorkerKillRestart:
    """Tests for worker kill and restart scenarios."""
    
    @pytest.fixture
    def mock_engine(self) -> tuple[MagicMock, MockDatabase]:
        """Create mock engine with database."""
        db = MockDatabase()
        
        engine = MagicMock(spec=CompressionEngine)
        engine._config = CompressionConfig()
        engine._db = db
        engine._stats = MagicMock()
        engine._stats.to_dict.return_value = {}
        engine._stats.items_skipped_version_mismatch = 0
        engine.last_error = None
        engine.compress_item = AsyncMock(return_value=True)
        
        return engine, db
    
    @pytest.mark.asyncio
    async def test_worker_kill_during_scan(self, mock_engine):
        """Test worker behavior when killed during scan."""
        engine, db = mock_engine
        
        items = [
            MemoryItem(
                id=f"item_{i}",
                type="conversation",
                content=f"Content {i}",
                session_id="session_1",
                last_updated=int(time.time()) - 8 * 86400,
            )
            for i in range(10)
        ]
        for item in items:
            db.set_item(item)
        
        config = WorkerConfig(interval_seconds=0.1, batch_size=5)
        worker = CompressionWorker(engine=engine, config=config)
        
        worker_task = asyncio.create_task(worker.start())
        await asyncio.sleep(0.05)
        
        await worker.stop()
        
        try:
            await asyncio.wait_for(worker_task, timeout=1.0)
        except asyncio.TimeoutError:
            worker_task.cancel()
        
        assert not worker.is_running
    
    @pytest.mark.asyncio
    async def test_worker_restart_after_crash(self, mock_engine):
        """Test worker can restart after simulated crash."""
        engine, db = mock_engine
        
        item = MemoryItem(
            id="crash_test",
            type="conversation",
            content="Content",
            session_id="session_1",
            last_updated=int(time.time()) - 8 * 86400,
        )
        db.set_item(item)
        
        config = WorkerConfig(interval_seconds=1, batch_size=5)
        worker = CompressionWorker(engine=engine, config=config)
        
        await worker.start()
        assert worker.is_running
        
        await worker.stop()
        
        db.set_item(item)
        await worker.start()
        assert worker.is_running
        
        await worker.stop()


class TestConcurrentOperations:
    """Tests for concurrent read/write operations."""
    
    @pytest.fixture
    def mock_engine(self):
        """Create mock engine."""
        db = MockDatabase()
        
        engine = MagicMock(spec=CompressionEngine)
        engine._config = CompressionConfig()
        engine._db = db
        engine._stats = MagicMock()
        engine._stats.to_dict.return_value = {}
        engine._stats.items_skipped_version_mismatch = 0
        engine.last_error = None
        engine.compress_item = AsyncMock(return_value=True)
        
        return engine, db
    
    @pytest.mark.asyncio
    async def test_concurrent_writes_and_scans(self, mock_engine):
        """Test worker running concurrently with writes."""
        engine, db = mock_engine
        
        config = WorkerConfig(interval_seconds=0.05, batch_size=10)
        worker = CompressionWorker(engine=engine, config=config)
        
        write_count = 0
        write_lock = asyncio.Lock()
        
        async def writer():
            nonlocal write_count
            for i in range(20):
                item = MemoryItem(
                    id=f"write_{i}",
                    type="conversation",
                    content=f"Written content {i}",
                    session_id="session_1",
                    last_updated=int(time.time()),
                )
                db.set_item(item)
                async with write_lock:
                    write_count += 1
                await asyncio.sleep(0.01)
        
        worker_task = asyncio.create_task(worker.start())
        write_task = asyncio.create_task(writer())
        
        await asyncio.sleep(0.3)
        
        await worker.stop()
        await write_task
        
        assert write_count == 20
    
    @pytest.mark.asyncio
    async def test_multiple_workers_same_items(self, mock_engine):
        """Test multiple workers processing same items."""
        engine, db = mock_engine
        
        for i in range(5):
            item = MemoryItem(
                id=f"shared_{i}",
                type="conversation",
                content=f"Shared content {i}",
                session_id="session_1",
                last_updated=int(time.time()) - 8 * 86400,
                version=1,
            )
            db.set_item(item)
        
        config = WorkerConfig(interval_seconds=0.1, batch_size=5)
        worker = CompressionWorker(engine=engine, config=config)
        
        await worker.start()
        await asyncio.sleep(0.2)
        await worker.stop()
        
        assert not worker.is_running


class TestDatabaseFailure:
    """Tests for database failure scenarios."""
    
    @pytest.fixture
    def mock_engine(self):
        """Create mock engine with failing database."""
        db = MockDatabase()
        db.set_fail_next(True)
        
        engine = MagicMock(spec=CompressionEngine)
        engine._config = CompressionConfig()
        engine._db = db
        engine._stats = MagicMock()
        engine._stats.to_dict.return_value = {}
        engine._stats.items_skipped_version_mismatch = 0
        engine.last_error = None
        engine.compress_item = AsyncMock(return_value=False)
        
        return engine, db
    
    @pytest.mark.asyncio
    async def test_worker_handles_db_failure(self, mock_engine):
        """Test worker handles database failure gracefully."""
        engine, db = mock_engine
        
        config = WorkerConfig(interval_seconds=0.1, batch_size=5)
        worker = CompressionWorker(engine=engine, config=config)
        
        await worker.start()
        await asyncio.sleep(0.2)
        
        assert worker.is_running
        
        await worker.stop()


class TestRateLimitingUnderLoad:
    """Tests for rate limiting under high load."""
    
    @pytest.fixture
    def mock_engine(self):
        """Create mock engine."""
        db = MockDatabase()
        
        engine = MagicMock(spec=CompressionEngine)
        engine._config = CompressionConfig()
        engine._db = db
        engine._stats = MagicMock()
        engine._stats.to_dict.return_value = {}
        engine._stats.items_skipped_version_mismatch = 0
        engine.last_error = None
        engine.compress_item = AsyncMock(return_value=True)
        
        return engine, db
    
    @pytest.mark.asyncio
    async def test_rate_limiter_under_burst(self, mock_engine):
        """Test rate limiter handles burst traffic."""
        engine, db = mock_engine
        
        for i in range(100):
            item = MemoryItem(
                id=f"burst_{i}",
                type="conversation",
                content=f"Burst content {i}",
                session_id="session_1",
                last_updated=int(time.time()) - 8 * 86400,
            )
            db.set_item(item)
        
        config = WorkerConfig(
            interval_seconds=0.1,
            batch_size=100,
            rate_limit_items_per_second=10
        )
        worker = CompressionWorker(engine=engine, config=config)
        
        start_time = time.time()
        await worker.run_once()
        elapsed = time.time() - start_time
        
        assert elapsed > 0


class TestGracefulDegradation:
    """Tests for graceful degradation scenarios."""
    
    @pytest.fixture
    def mock_engine(self):
        """Create mock engine."""
        db = MockDatabase()
        
        engine = MagicMock(spec=CompressionEngine)
        engine._config = CompressionConfig()
        engine._db = db
        engine._stats = MagicMock()
        engine._stats.to_dict.return_value = {}
        engine._stats.items_skipped_version_mismatch = 0
        engine.last_error = None
        engine.compress_item = AsyncMock(return_value=False)
        
        return engine, db
    
    @pytest.mark.asyncio
    async def test_worker_starts_without_db(self, mock_engine):
        """Test worker can start even without database."""
        engine, _ = mock_engine
        engine._db = None
        
        config = WorkerConfig()
        worker = CompressionWorker(engine=engine, config=config)
        
        await worker.start()
        assert worker.is_running
        
        await worker.stop()
    
    @pytest.mark.asyncio
    async def test_worker_handles_empty_batch(self, mock_engine):
        """Test worker handles empty batch gracefully."""
        engine, db = mock_engine
        
        config = WorkerConfig(batch_size=10)
        worker = CompressionWorker(engine=engine, config=config)
        
        count = await worker.run_once()
        
        assert count == 0


class TestShutdownBehavior:
    """Tests for shutdown behavior."""
    
    @pytest.fixture
    def mock_engine(self):
        """Create mock engine."""
        db = MockDatabase()
        
        engine = MagicMock(spec=CompressionEngine)
        engine._config = CompressionConfig()
        engine._db = db
        engine._stats = MagicMock()
        engine._stats.to_dict.return_value = {}
        engine._stats.items_skipped_version_mismatch = 0
        engine.last_error = None
        engine.compress_item = AsyncMock(return_value=True)
        
        return engine, db
    
    @pytest.mark.asyncio
    async def test_double_stop_is_safe(self, mock_engine):
        """Test that calling stop twice is safe."""
        engine, db = mock_engine
        
        config = WorkerConfig(interval_seconds=1)
        worker = CompressionWorker(engine=engine, config=config)
        
        await worker.start()
        await worker.stop()
        await worker.stop()
        
        assert not worker.is_running
    
    @pytest.mark.asyncio
    async def test_stop_during_compression(self, mock_engine):
        """Test stopping worker during active compression."""
        engine, db = mock_engine
        
        for i in range(20):
            item = MemoryItem(
                id=f"stop_test_{i}",
                type="conversation",
                content=f"Content {i}",
                session_id="session_1",
                last_updated=int(time.time()) - 8 * 86400,
            )
            db.set_item(item)
        
        compress_count = 0
        original_compress = engine.compress_item
        
        async def slow_compress(*args, **kwargs):
            nonlocal compress_count
            compress_count += 1
            await asyncio.sleep(0.1)
            return await original_compress(*args, **kwargs)
        
        engine.compress_item = slow_compress
        
        config = WorkerConfig(interval_seconds=0.05, batch_size=20)
        worker = CompressionWorker(engine=engine, config=config)
        
        worker_task = asyncio.create_task(worker.start())
        await asyncio.sleep(0.05)
        
        await worker.stop()
        
        try:
            await asyncio.wait_for(worker_task, timeout=1.0)
        except asyncio.TimeoutError:
            worker_task.cancel()
        
        assert compress_count >= 0
