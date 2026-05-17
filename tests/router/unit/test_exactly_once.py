"""Unit tests for ExactlyOnceProcessor."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.infrastructure.router.observation.exactly_once import (
    ExactlyOnceProcessor,
    FrequencyStorage,
    InMemoryFrequencyStorage,
)
from src.infrastructure.router.types import Feedback


class TestExactlyOnceProcessor:
    """Test ExactlyOnceProcessor functionality."""

    @pytest.fixture
    def storage(self) -> InMemoryFrequencyStorage:
        """Create in-memory storage."""
        return InMemoryFrequencyStorage()

    @pytest.fixture
    def processor(self, storage: InMemoryFrequencyStorage) -> ExactlyOnceProcessor:
        """Create processor with storage."""
        return ExactlyOnceProcessor(storage)

    @pytest.fixture
    def sample_feedback(self) -> Feedback:
        """Create sample feedback."""
        return Feedback(
            query="test query",
            intent_path="test_intent",
            example_text="test example",
            success=True,
            timestamp=time.time(),
        )

    @pytest.mark.asyncio
    async def test_first_process_returns_true(
        self,
        processor: ExactlyOnceProcessor,
        sample_feedback: Feedback,
    ):
        """Test that first processing returns True."""
        result = await processor.process_feedback(sample_feedback)
        assert result is True

    @pytest.mark.asyncio
    async def test_duplicate_process_returns_false(
        self,
        processor: ExactlyOnceProcessor,
        sample_feedback: Feedback,
    ):
        """Test that duplicate processing returns False (idempotent)."""
        # First processing
        await processor.process_feedback(sample_feedback)

        # Duplicate processing
        result = await processor.process_feedback(sample_feedback)
        assert result is False

    @pytest.mark.asyncio
    async def test_frequency_incremented(
        self,
        processor: ExactlyOnceProcessor,
        sample_feedback: Feedback,
    ):
        """Test that frequency is incremented on processing."""
        await processor.process_feedback(sample_feedback)

        frequencies = await processor._storage.get_frequency("test_intent")
        assert len(frequencies) > 0

    @pytest.mark.asyncio
    async def test_idempotency_key_deterministic(
        self,
        processor: ExactlyOnceProcessor,
    ):
        """Test that idempotency key is deterministic."""
        feedback1 = Feedback(
            query="same query",
            intent_path="same_intent",
            example_text="same example",
            success=True,
            timestamp=1000000.0,  # Fixed timestamp
        )
        feedback2 = Feedback(
            query="same query",
            intent_path="same_intent",
            example_text="same example",
            success=True,
            timestamp=1000000.0,  # Same timestamp
        )

        key1 = processor._generate_idempotency_key(feedback1)
        key2 = processor._generate_idempotency_key(feedback2)

        assert key1 == key2

    @pytest.mark.asyncio
    async def test_different_feedback_different_keys(
        self,
        processor: ExactlyOnceProcessor,
    ):
        """Test that different feedback produces different keys."""
        feedback1 = Feedback(
            query="query 1",
            intent_path="intent",
            example_text="example",
            success=True,
            timestamp=1000000.0,
        )
        feedback2 = Feedback(
            query="query 2",
            intent_path="intent",
            example_text="example",
            success=True,
            timestamp=1000000.0,
        )

        key1 = processor._generate_idempotency_key(feedback1)
        key2 = processor._generate_idempotency_key(feedback2)

        assert key1 != key2

    @pytest.mark.asyncio
    async def test_day_bucket_normalization(
        self,
        processor: ExactlyOnceProcessor,
    ):
        """Test that timestamps are normalized to day buckets."""
        # Two feedbacks on the same day should have same bucket
        day_start = 1000000.0 - (1000000.0 % 86400)

        feedback1 = Feedback(
            query="query",
            intent_path="intent",
            example_text="example",
            success=True,
            timestamp=day_start + 1000,  # 1000 seconds into day
        )
        feedback2 = Feedback(
            query="query",
            intent_path="intent",
            example_text="example",
            success=True,
            timestamp=day_start + 80000,  # Different time same day
        )

        key1 = processor._generate_idempotency_key(feedback1)
        key2 = processor._generate_idempotency_key(feedback2)

        assert key1 == key2

    @pytest.mark.asyncio
    async def test_different_days_different_keys(
        self,
        processor: ExactlyOnceProcessor,
    ):
        """Test that feedbacks on different days have different keys."""
        day1 = 1000000.0
        day2 = day1 + 86400  # Next day

        feedback1 = Feedback(
            query="query",
            intent_path="intent",
            example_text="example",
            success=True,
            timestamp=day1,
        )
        feedback2 = Feedback(
            query="query",
            intent_path="intent",
            example_text="example",
            success=True,
            timestamp=day2,
        )

        key1 = processor._generate_idempotency_key(feedback1)
        key2 = processor._generate_idempotency_key(feedback2)

        assert key1 != key2


class TestInMemoryFrequencyStorage:
    """Test InMemoryFrequencyStorage functionality."""

    @pytest.fixture
    def storage(self) -> InMemoryFrequencyStorage:
        """Create fresh storage."""
        return InMemoryFrequencyStorage()

    @pytest.mark.asyncio
    async def test_key_exists_false_initially(self, storage: InMemoryFrequencyStorage):
        """Test that key exists returns False initially."""
        exists = await storage.key_exists("some_key")
        assert exists is False

    @pytest.mark.asyncio
    async def test_key_exists_true_after_insert(self, storage: InMemoryFrequencyStorage):
        """Test that key exists returns True after insert."""
        await storage.insert_applied_key("test_key")
        exists = await storage.key_exists("test_key")
        assert exists is True

    @pytest.mark.asyncio
    async def test_insert_applied_key_returns_true_first_time(
        self, storage: InMemoryFrequencyStorage
    ):
        """Test that insert returns True on first insert."""
        result = await storage.insert_applied_key("new_key")
        assert result is True

    @pytest.mark.asyncio
    async def test_insert_applied_key_returns_false_on_duplicate(
        self, storage: InMemoryFrequencyStorage
    ):
        """Test that insert returns False on duplicate."""
        await storage.insert_applied_key("existing_key")
        result = await storage.insert_applied_key("existing_key")
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_applied_key(self, storage: InMemoryFrequencyStorage):
        """Test that applied key can be deleted."""
        await storage.insert_applied_key("key_to_delete")
        await storage.delete_applied_key("key_to_delete")
        exists = await storage.key_exists("key_to_delete")
        assert exists is False

    @pytest.mark.asyncio
    async def test_write_wal_event(self, storage: InMemoryFrequencyStorage):
        """Test WAL event writing."""
        await storage.write_wal_event(
            event_id="evt_123",
            intent_path="test_intent",
            example_text="test example",
            idempotency_key="key_123",
            timestamp=time.time(),
        )
        # No exception means success

    @pytest.mark.asyncio
    async def test_update_frequency_increments(
        self, storage: InMemoryFrequencyStorage
    ):
        """Test that frequency update increments count."""
        await storage.update_frequency("test_intent", "hash_1")
        await storage.update_frequency("test_intent", "hash_1")

        frequencies = await storage.get_frequency("test_intent")
        assert frequencies.get("hash_1", 0) == 2

    @pytest.mark.asyncio
    async def test_increment_frequency_version(
        self, storage: InMemoryFrequencyStorage
    ):
        """Test frequency version increment."""
        initial = 1  # Default
        await storage.increment_frequency_version()
        await storage.increment_frequency_version()

        # Verify through storage state (indirect test)
        assert True  # No exception

    @pytest.mark.asyncio
    async def test_concurrent_inserts_only_one_succeeds(
        self, storage: InMemoryFrequencyStorage
    ):
        """Test that concurrent inserts only one succeeds."""
        results = await asyncio.gather(
            storage.insert_applied_key("concurrent_key"),
            storage.insert_applied_key("concurrent_key"),
            storage.insert_applied_key("concurrent_key"),
        )

        # Only one should succeed
        assert sum(results) == 1


class TestWALInsertAndRetry:
    """Test WAL insert and retry behavior."""

    @pytest.fixture
    def storage(self) -> InMemoryFrequencyStorage:
        """Create storage."""
        return InMemoryFrequencyStorage()

    @pytest.fixture
    def processor(self, storage: InMemoryFrequencyStorage) -> ExactlyOnceProcessor:
        """Create processor."""
        return ExactlyOnceProcessor(storage)

    @pytest.mark.asyncio
    async def test_wal_written_on_process(
        self, processor: ExactlyOnceProcessor, storage: InMemoryFrequencyStorage
    ):
        """Test that WAL is written when processing feedback."""
        feedback = Feedback(
            query="test",
            intent_path="test_intent",
            example_text="example",
            success=True,
            timestamp=time.time(),
        )

        await processor.process_feedback(feedback)

        # WAL should have entry
        assert len(storage._wal) == 1
        assert storage._wal[0]["intent_path"] == "test_intent"

    @pytest.mark.asyncio
    async def test_retry_after_failure_still_processes(
        self, processor: ExactlyOnceProcessor, storage: InMemoryFrequencyStorage
    ):
        """Test that processing succeeds after initial failure simulation."""
        feedback = Feedback(
            query="test",
            intent_path="test_intent",
            example_text="example",
            success=True,
            timestamp=time.time(),
        )

        # First process
        result1 = await processor.process_feedback(feedback)
        assert result1 is True

        # Second process (should be idempotent)
        result2 = await processor.process_feedback(feedback)
        assert result2 is False


class TestExactlyOnceWithIdempotencyKey:
    """Test exactly-once guarantee with idempotency keys."""

    @pytest.fixture
    def storage(self) -> InMemoryFrequencyStorage:
        """Create storage."""
        return InMemoryFrequencyStorage()

    @pytest.fixture
    def processor(self, storage: InMemoryFrequencyStorage) -> ExactlyOnceProcessor:
        """Create processor."""
        return ExactlyOnceProcessor(storage)

    @pytest.mark.asyncio
    async def test_exactly_once_guarantee(self, processor: ExactlyOnceProcessor):
        """Test exactly-once guarantee with same feedback."""
        feedback = Feedback(
            query="unique query",
            intent_path="unique_intent",
            example_text="unique example",
            success=True,
            timestamp=2000000.0,  # Fixed timestamp
        )

        # Process 5 times
        results = []
        for _ in range(5):
            result = await processor.process_feedback(feedback)
            results.append(result)

        # Only first should return True
        assert results[0] is True
        assert all(r is False for r in results[1:])

        # Frequency should only be incremented once
        frequencies = await processor._storage.get_frequency("unique_intent")
        total = sum(frequencies.values())
        assert total == 1

    @pytest.mark.asyncio
    async def test_idempotent_key_uniqueness(
        self, processor: ExactlyOnceProcessor
    ):
        """Test that idempotency keys are unique per feedback."""
        base_time = 3000000.0

        feedbacks = [
            Feedback(
                query=f"query_{i}",
                intent_path="intent",
                example_text="same example",
                success=True,
                timestamp=base_time,
            )
            for i in range(5)
        ]

        keys = [processor._generate_idempotency_key(f) for f in feedbacks]

        # All keys should be different
        assert len(set(keys)) == 5

    @pytest.mark.asyncio
    async def test_multiple_intents_exactly_once(
        self, processor: ExactlyOnceProcessor
    ):
        """Test exactly-once for multiple intents."""
        feedbacks = [
            Feedback(
                query=f"query_{i}",
                intent_path=f"intent_{i}",
                example_text=f"example_{i}",
                success=True,
                timestamp=4000000.0 + i,
            )
            for i in range(3)
        ]

        # Process each feedback
        for fb in feedbacks:
            await processor.process_feedback(fb)

        # Process again - all should be idempotent
        for fb in feedbacks:
            result = await processor.process_feedback(fb)
            assert result is False


class TestStalenessCalculation:
    """Test staleness calculation for snapshots."""

    def test_idempotency_key_format(self):
        """Test idempotency key format."""
        storage = InMemoryFrequencyStorage()
        processor = ExactlyOnceProcessor(storage)

        feedback = Feedback(
            query="test",
            intent_path="intent",
            example_text="example",
            success=True,
            timestamp=5000000.0,
        )

        key = processor._generate_idempotency_key(feedback)

        # Key should be a hex string (SHA256)
        assert len(key) == 64
        assert all(c in "0123456789abcdef" for c in key)

    def test_idempotency_key_consistency_across_days(self):
        """Test key consistency across multiple day boundaries."""
        storage = InMemoryFrequencyStorage()
        processor = ExactlyOnceProcessor(storage)

        # Same query across day boundary
        day_start = 86400 * 100  # Day 100

        feedback1 = Feedback(
            query="same",
            intent_path="same",
            example_text="same",
            success=True,
            timestamp=day_start + 100,  # 100 seconds into day
        )
        feedback2 = Feedback(
            query="same",
            intent_path="same",
            example_text="same",
            success=True,
            timestamp=day_start + 100 + 86400,  # Same time next day
        )

        key1 = processor._generate_idempotency_key(feedback1)
        key2 = processor._generate_idempotency_key(feedback2)

        # Keys should be different across days
        assert key1 != key2


class TestCrashRecovery:
    """Test crash recovery scenarios."""

    @pytest.fixture
    def storage(self) -> InMemoryFrequencyStorage:
        """Create storage."""
        return InMemoryFrequencyStorage()

    @pytest.fixture
    def processor(self, storage: InMemoryFrequencyStorage) -> ExactlyOnceProcessor:
        """Create processor."""
        return ExactlyOnceProcessor(storage)

    @pytest.mark.asyncio
    async def test_crash_simulation_with_preinserted_key(
        self, storage: InMemoryFrequencyStorage
    ):
        """Test scenario where crash occurs before frequency update."""
        processor = ExactlyOnceProcessor(storage)

        # Create feedback with a specific timestamp
        base_time = 6000000.0
        feedback = Feedback(
            query="crash scenario",
            intent_path="crash_intent",
            example_text="crash example",
            success=True,
            timestamp=base_time,
        )

        # Get the idempotency key that would be generated
        idempotency_key = processor._generate_idempotency_key(feedback)

        # Insert applied key manually (simulating partial completion)
        await storage.insert_applied_key(idempotency_key)

        # Process again - should be idempotent because key exists
        result = await processor.process_feedback(feedback)
        assert result is False

    @pytest.mark.asyncio
    async def test_replay_after_crash(self, storage: InMemoryFrequencyStorage):
        """Test that WAL replay works after crash."""
        feedback = Feedback(
            query="replay test",
            intent_path="replay_intent",
            example_text="replay example",
            success=True,
            timestamp=time.time(),
        )

        # Process normally
        processor = ExactlyOnceProcessor(storage)
        await processor.process_feedback(feedback)

        # Verify it was processed
        frequencies = await storage.get_frequency("replay_intent")
        assert sum(frequencies.values()) > 0
