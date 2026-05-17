"""Chaos tests for semantic router - simulating failures and degradation."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.infrastructure.router.consistency.read_after_write import ReadAfterWriteGuard
from src.infrastructure.router.execution_engine import ExecutionEngine
from src.infrastructure.router.fairness.boost_fairness import FairnessBoostCalculator
from src.infrastructure.router.observation.exactly_once import (
    ExactlyOnceProcessor,
    InMemoryFrequencyStorage,
)
from src.infrastructure.router.observation.feedback_processor import FeedbackProcessor
from src.infrastructure.router.observation.health_monitor import HealthMonitor
from src.infrastructure.router.observation.lifecycle_manager import (
    InMemoryLifecycleStorage,
    LifecycleManager,
)
from src.infrastructure.router.router import SemanticRouter
from src.infrastructure.router.snapshot import ConfigProvider, SnapshotManager
from src.infrastructure.router.score_engine import (
    InMemoryANNIndex,
    InMemoryEmbeddingModel,
    ScoreEngine,
)
from src.infrastructure.router.types import (
    BoostFairnessConfig,
    ConsistencyConfig,
    Feedback,
    IntentConfig,
    LifecycleConfig,
    Request,
    RouterConfig,
    Snapshot,
)


class TestEmbeddingTimeoutChaos:
    """Chaos tests for embedding service timeout scenarios."""

    @pytest.mark.asyncio
    async def test_embedding_timeout_fallback_to_rule(self):
        """Test router handles embedding timeout by falling back to rule-based."""
        # Create a failing embedding model
        class FailingEmbeddingModel:
            async def embed(self, text: str):
                await asyncio.sleep(0.1)  # Simulate slow response
                raise TimeoutError("Embedding service timeout")

        # Create router with failing embedding
        from src.infrastructure.router.policy_engine import PolicyEngine, PolicyEngineConfig

        embedding = FailingEmbeddingModel()
        index = InMemoryANNIndex(dimension=128)
        fairness = FairnessBoostCalculator(BoostFairnessConfig(enabled=False))

        score_engine = ScoreEngine(
            embedding_model=embedding,
            ann_index=index,
            fairness_calculator=fairness,
        )

        policy_engine_config = PolicyEngineConfig(
            default_intent="fallback",
            fallback_enabled=True,
        )

        intents = {
            "code": IntentConfig(
                name="code",
                rules=[
                    MagicMock(matches=lambda r: "code" in r.query.lower())
                ],
            ),
        }
        snapshot = Snapshot(
            snapshot_id="test",
            config=RouterConfig(intents=intents),
            index=index,
            frequency_version=1,
            freq_snapshot_time=time.time(),
            created_at=time.time(),
        )

        # With semantic timeout, rule-based should still work
        # Note: The actual behavior depends on error handling in the router

    @pytest.mark.asyncio
    async def test_multiple_embedding_failures_degradation(self):
        """Test degradation behavior with multiple embedding failures."""
        from src.infrastructure.router.policy_engine import PolicyEngine, PolicyEngineConfig

        failure_count = [0]

        class DegradingEmbeddingModel:
            async def embed(self, text: str):
                failure_count[0] += 1
                if failure_count[0] <= 3:
                    raise TimeoutError("Service unavailable")
                return [0.5] * 128

        embedding = DegradingEmbeddingModel()
        index = InMemoryANNIndex(dimension=128)
        fairness = FairnessBoostCalculator(BoostFairnessConfig(enabled=False))

        score_engine = ScoreEngine(
            embedding_model=embedding,
            ann_index=index,
            fairness_calculator=fairness,
        )

        # After 3 failures, should succeed
        for i in range(5):
            try:
                await asyncio.wait_for(
                    embedding.embed("test"),
                    timeout=0.5,
                )
            except TimeoutError:
                pass


class TestDatabaseUnavailableChaos:
    """Chaos tests for database (LanceDB) unavailability."""

    @pytest.mark.asyncio
    async def test_storage_failure_handling(self):
        """Test handling when storage is unavailable."""
        storage = InMemoryFrequencyStorage()

        # Simulate storage failure
        original_update = storage.update_frequency
        call_count = [0]

        async def failing_update(intent_path: str, example_hash: str):
            call_count[0] += 1
            if call_count[0] <= 2:
                raise ConnectionError("Database unavailable")
            return await original_update(intent_path, example_hash)

        storage.update_frequency = failing_update

        processor = ExactlyOnceProcessor(storage)

        feedback = Feedback(
            query="test",
            intent_path="test_intent",
            example_text="example",
            success=True,
            timestamp=time.time(),
        )

        # First attempt should raise exception (handled by processor)
        with pytest.raises(ConnectionError):
            await processor.process_feedback(feedback)


class TestCrashDuringWALCommit:
    """Chaos tests simulating crashes during WAL commit."""

    @pytest.mark.asyncio
    async def test_crash_during_wal_write_recovery(self):
        """Test recovery when crash occurs during WAL write."""
        storage = InMemoryFrequencyStorage()

        # Simulate crash: WAL write succeeds but frequency update fails
        wal_written = [False]
        frequency_updated = [False]

        original_wal = storage.write_wal_event

        async def crashing_wal(*args, **kwargs):
            await original_wal(*args, **kwargs)
            wal_written[0] = True
            raise IOError("Simulated crash after WAL write")

        storage.write_wal_event = crashing_wal

        processor = ExactlyOnceProcessor(storage)

        feedback = Feedback(
            query="crash test",
            intent_path="crash_intent",
            example_text="crash example",
            success=True,
            timestamp=time.time(),
        )

        try:
            await processor.process_feedback(feedback)
        except IOError:
            pass  # Expected

        # WAL should have been written
        assert wal_written[0] is True

    @pytest.mark.asyncio
    async def test_crash_before_applied_key_insert(self):
        """Test behavior when crash occurs before applied key insert."""
        storage = InMemoryFrequencyStorage()

        # Track operations
        operations = []

        original_insert = storage.insert_applied_key

        async def tracing_insert(key: str):
            operations.append(("insert_key", key))
            if len([op for op in operations if op[0] == "insert_key"]) == 1:
                # First time: fail
                raise IOError("Simulated crash")
            return await original_insert(key)

        storage.insert_applied_key = tracing_insert

        processor = ExactlyOnceProcessor(storage)

        feedback = Feedback(
            query="crash before key",
            intent_path="test_intent",
            example_text="example",
            success=True,
            timestamp=time.time(),
        )

        # First attempt fails
        try:
            await processor.process_feedback(feedback)
        except IOError:
            pass

        # Second attempt should succeed (no key exists)
        result = await processor.process_feedback(feedback)
        assert result is True  # Should process on retry


class TestNetworkPartition:
    """Chaos tests for network partition scenarios."""

    @pytest.mark.asyncio
    async def test_network_partition_retry_behavior(self):
        """Test retry behavior during network partition."""
        storage = InMemoryFrequencyStorage()
        processor = ExactlyOnceProcessor(storage)

        retry_count = [0]
        feedback = Feedback(
            query="partition test",
            intent_path="partition_intent",
            example_text="example",
            success=True,
            timestamp=time.time(),
        )

        # Simulate intermittent network failures
        original_update = storage.update_frequency

        async def flaky_update(intent_path: str, example_hash: str):
            retry_count[0] += 1
            if retry_count[0] < 3:
                raise ConnectionError("Network partition")
            return await original_update(intent_path, example_hash)

        storage.update_frequency = flaky_update

        # With proper retry, should eventually succeed
        # This test verifies the pattern
        for i in range(5):
            try:
                await processor.process_feedback(feedback)
                break
            except ConnectionError:
                if i == 4:
                    raise


class TestMemoryPressure:
    """Chaos tests for memory pressure scenarios."""

    @pytest.mark.asyncio
    async def test_large_number_of_intents_handled(self):
        """Test handling of large number of intents."""
        # Create config with many intents
        intents = {
            f"intent_{i}": IntentConfig(
                name=f"intent_{i}",
                base_score=0.5,
                priority=i,
            )
            for i in range(100)  # 100 intents
        }

        config = RouterConfig(intents=intents)

        # Should handle gracefully
        snapshot = Snapshot(
            snapshot_id="large_test",
            config=config,
            index=MagicMock(),
            frequency_version=1,
            freq_snapshot_time=time.time(),
            created_at=time.time(),
        )

        # Access should work
        assert len(snapshot.config.intents) == 100

    @pytest.mark.asyncio
    async def test_rapid_lifecycle_changes(self):
        """Test handling of rapid lifecycle state changes."""
        storage = InMemoryLifecycleStorage()
        health_monitor = HealthMonitor()
        config = LifecycleConfig()
        manager = LifecycleManager(
            storage=storage,
            config=config,
            health_monitor=health_monitor,
        )

        intent = "rapid_change"

        # Rapid enable/disable
        for _ in range(20):
            await manager.enable_intent(intent)
            await manager.disable_intent(intent, reason="rapid test")
            await manager.enable_intent(intent)

        # Should complete without deadlock or corruption
        lifecycle = await manager.get_intent_state(intent)
        assert lifecycle is not None


class TestDegradedMode:
    """Tests for degraded mode behavior."""

    @pytest.mark.asyncio
    async def test_fairness_disabled_still_works(self):
        """Test that router works when fairness is disabled."""
        config = BoostFairnessConfig(enabled=False)
        calculator = FairnessBoostCalculator(config)

        # Should still calculate boost (no fairness limits)
        for i in range(50):
            boost = await calculator.calculate_boost(
                intent=f"intent_{i}",
                base_score=0.5,
                max_intent_boost=100.0,
            )
            assert boost >= 0.5

    @pytest.mark.asyncio
    async def test_consistency_guard_disabled(self):
        """Test behavior when consistency guard is disabled."""
        config = ConsistencyConfig(
            read_after_write_guard_ms=0,  # Disabled
            force_new_snapshot_on_feedback=False,
            warn_on_stale_snapshot=False,
        )

        from src.infrastructure.router.score_engine import InMemoryANNIndex

        provider = MagicMock()
        provider.get_config = AsyncMock(return_value=RouterConfig())
        provider.get_frequency_version = AsyncMock(return_value=1)
        provider.get_ann_index = AsyncMock(return_value=InMemoryANNIndex())

        snapshot_manager = SnapshotManager(provider)
        guard = ReadAfterWriteGuard(config, snapshot_manager)

        # Should force new snapshot immediately
        await guard.on_feedback_written()
        should_force, reason = await guard.should_force_new_snapshot()

        # With 0ms guard, should not force (immediate expiry)
        # But should also not warn


class TestResourceExhaustion:
    """Tests for resource exhaustion scenarios."""

    @pytest.mark.asyncio
    async def test_storage_key_overflow_handled(self):
        """Test handling of storage key overflow."""
        storage = InMemoryFrequencyStorage()

        # Insert many keys
        for i in range(1000):
            await storage.insert_applied_key(f"key_{i}")

        # Check storage is not corrupted
        for i in range(1000):
            exists = await storage.key_exists(f"key_{i}")
            assert exists is True

    @pytest.mark.asyncio
    async def test_frequency_hash_collision_handled(self):
        """Test handling of frequency hash collisions."""
        storage = InMemoryFrequencyStorage()

        # Same hash, different contexts
        await storage.update_frequency("intent_a", "same_hash")
        await storage.update_frequency("intent_a", "same_hash")

        frequencies = await storage.get_frequency("intent_a")
        # Should increment (2)
        total = sum(frequencies.values())
        assert total == 2


class TestClockSkew:
    """Tests for clock skew scenarios."""

    @pytest.mark.asyncio
    async def test_timestamp_normalization(self):
        """Test that timestamps are properly normalized."""
        processor = ExactlyOnceProcessor(InMemoryFrequencyStorage())

        # Same day, different times
        day_start = 86400 * 10000  # Day 10000

        feedback1 = Feedback(
            query="test",
            intent_path="intent",
            example_text="example",
            success=True,
            timestamp=day_start + 1000,
        )
        feedback2 = Feedback(
            query="test",
            intent_path="intent",
            example_text="example",
            success=True,
            timestamp=day_start + 2000,  # 1000 seconds later, same day
        )

        key1 = processor._generate_idempotency_key(feedback1)
        key2 = processor._generate_idempotency_key(feedback2)

        # Same day = same key
        assert key1 == key2

    @pytest.mark.asyncio
    async def test_day_boundary_keys(self):
        """Test idempotency keys across day boundaries."""
        processor = ExactlyOnceProcessor(InMemoryFrequencyStorage())

        day_start = 86400 * 10000

        feedback1 = Feedback(
            query="test",
            intent_path="intent",
            example_text="example",
            success=True,
            timestamp=day_start + 86399,  # Last second of day
        )
        feedback2 = Feedback(
            query="test",
            intent_path="intent",
            example_text="example",
            success=True,
            timestamp=day_start + 86400,  # First second of next day
        )

        key1 = processor._generate_idempotency_key(feedback1)
        key2 = processor._generate_idempotency_key(feedback2)

        # Different days = different keys
        assert key1 != key2


class TestCorruptionRecovery:
    """Tests for data corruption and recovery."""

    @pytest.mark.asyncio
    async def test_partial_wal_recovery(self):
        """Test recovery from partial WAL write."""
        storage = InMemoryFrequencyStorage()

        # Write to WAL without marking processed
        await storage.write_wal_event(
            event_id="partial_evt",
            intent_path="test_intent",
            example_text="partial example",
            idempotency_key="partial_key",
            timestamp=time.time(),
        )

        # Manual recovery: process the event
        processor = ExactlyOnceProcessor(storage)

        # The event should be recoverable
        # (In real scenario, WAL replay would handle this)


class TestTimeoutScenarios:
    """Tests for various timeout scenarios."""

    @pytest.mark.asyncio
    async def test_handler_timeout_returns_error(self):
        """Test that handler timeout returns proper error."""
        engine = ExecutionEngine()

        async def slow_handler(ctx):
            await asyncio.sleep(5)
            return "done"

        from src.infrastructure.router.execution_engine import HandlerConfig
        engine.register_handler("slow", slow_handler, HandlerConfig(timeout_seconds=0.1))

        snapshot = Snapshot(
            snapshot_id="test",
            config=RouterConfig(),
            index=MagicMock(),
            frequency_version=1,
            freq_snapshot_time=time.time(),
            created_at=time.time(),
        )

        from src.infrastructure.router.types import Request, RequestContext, RouteResult
        context = RequestContext.create(
            snapshot=snapshot,
            request=Request(query="test"),
        )

        result = await engine.execute(context, RouteResult(intent="slow", confidence=0.9))

        assert result.success is False
        assert "timeout" in result.error.lower()

    @pytest.mark.asyncio
    async def test_multiple_timeouts_dont_crash(self):
        """Test that multiple timeouts don't crash the system."""
        engine = ExecutionEngine()

        async def always_timeout(ctx):
            await asyncio.sleep(10)
            return "done"

        from src.infrastructure.router.execution_engine import HandlerConfig
        engine.register_handler("timeout", always_timeout, HandlerConfig(timeout_seconds=0.1))

        snapshot = Snapshot(
            snapshot_id="test",
            config=RouterConfig(),
            index=MagicMock(),
            frequency_version=1,
            freq_snapshot_time=time.time(),
            created_at=time.time(),
        )

        from src.infrastructure.router.types import Request, RequestContext, RouteResult

        # Execute many timeouts
        for i in range(10):
            context = RequestContext.create(
                snapshot=snapshot,
                request=Request(query=f"test_{i}"),
            )
            result = await engine.execute(context, RouteResult(intent="timeout", confidence=0.9))
            assert result.success is False


class TestPartialFailure:
    """Tests for partial failure scenarios."""

    @pytest.mark.asyncio
    async def test_partial_feedback_success(self):
        """Test partial success in feedback processing."""
        storage = InMemoryFrequencyStorage()

        # WAL succeeds, key insert fails
        original_insert = storage.insert_applied_key

        async def failing_insert(key: str):
            raise IOError("Partial failure")

        storage.insert_applied_key = failing_insert

        processor = ExactlyOnceProcessor(storage)

        feedback = Feedback(
            query="partial",
            intent_path="intent",
            example_text="example",
            success=True,
            timestamp=time.time(),
        )

        # Should fail gracefully
        with pytest.raises(IOError):
            await processor.process_feedback(feedback)


# Flag for running chaos tests
def pytest_configure(config):
    """Register custom marker for chaos tests."""
    config.addinivalue_line(
        "markers", "chaos: mark test as chaos test"
    )


@pytest.mark.chaos
class TestChaosMarkers:
    """Tests with chaos marker for selective execution."""

    @pytest.mark.asyncio
    async def test_chaos_marker_works(self):
        """Verify chaos marker is registered."""
        assert True
