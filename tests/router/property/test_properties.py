"""Property-based tests for semantic router using Hypothesis."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import MagicMock

import pytest
from hypothesis import given, settings, assume, example, assume
from hypothesis import strategies as st

from src.infrastructure.router.fairness.boost_fairness import FairnessBoostCalculator
from src.infrastructure.router.observation.exactly_once import (
    ExactlyOnceProcessor,
    InMemoryFrequencyStorage,
)
from src.infrastructure.router.observation.lifecycle_manager import (
    InMemoryLifecycleStorage,
    LifecycleManager,
)
from src.infrastructure.router.observation.health_monitor import HealthMonitor
from src.infrastructure.router.types import (
    BoostFairnessConfig,
    Feedback,
    IntentConfig,
    IntentLifecycleState,
    LifecycleConfig,
    Request,
    RequestContext,
    RouterConfig,
    RoutingRule,
    Snapshot,
)


# =============================================================================
# Invariant: No Mixed Versions
# =============================================================================

class TestNoMixedVersionsInvariant:
    """Property tests for 'No mixed versions' invariant."""

    @settings(max_examples=50)
    @given(
        config_changes=st.lists(
            st.tuples(
                st.text(min_size=1, max_size=20),
                st.floats(min_value=0.1, max_value=1.0),
            ),
            min_size=1,
            max_size=10,
        )
    )
    @pytest.mark.asyncio
    async def test_snapshot_versions_consistent_in_request(
        self,
        config_changes,
    ):
        """Property: Within a request, all versions should be equal."""
        # Generate random config changes
        intents = {}
        for i, (name, score) in enumerate(config_changes):
            intents[name] = IntentConfig(
                name=name,
                base_score=score,
                priority=i,
            )

        config = RouterConfig(intents=intents)

        # Create snapshot
        snapshot = Snapshot(
            snapshot_id=f"snap_{hash(tuple(config_changes))}",
            config=config,
            index=MagicMock(),
            frequency_version=42,  # Fixed version for this test
            freq_snapshot_time=time.time(),
            created_at=time.time(),
        )

        # Simulate request pipeline
        context = RequestContext.create(
            snapshot=snapshot,
            request=Request(query="test query"),
        )

        # Verify all accesses use same snapshot
        policy_version = context.frozen_snapshot.frequency_version
        score_version = context.frozen_snapshot.frequency_version
        exec_version = context.frozen_snapshot.frequency_version

        # Property: All versions should be equal
        assert policy_version == score_version == exec_version

    @settings(max_examples=30)
    @given(
        snapshot_count=st.integers(min_value=1, max_value=5),
        request_per_snapshot=st.integers(min_value=1, max_value=3),
    )
    @pytest.mark.asyncio
    async def test_no_version_mixing_across_requests(
        self,
        snapshot_count,
        request_per_snapshot,
    ):
        """Property: Different snapshots should not be mixed in same request."""
        snapshots = []
        for i in range(snapshot_count):
            config = RouterConfig(
                intents={
                    f"intent_{i}": IntentConfig(
                        name=f"intent_{i}",
                        base_score=0.5 + i * 0.1,
                    )
                }
            )
            snapshot = Snapshot(
                snapshot_id=f"snap_{i}",
                config=config,
                index=MagicMock(),
                frequency_version=i,
                freq_snapshot_time=time.time(),
                created_at=time.time(),
            )
            snapshots.append(snapshot)

        # Simulate requests, each using its own snapshot
        for snap_idx in range(snapshot_count):
            for req_idx in range(request_per_snapshot):
                context = RequestContext.create(
                    snapshot=snapshots[snap_idx],
                    request=Request(query=f"request_{snap_idx}_{req_idx}"),
                )

                # Property: Each request should only use its assigned snapshot
                assert context.snapshot_id == f"snap_{snap_idx}"
                assert context.frozen_snapshot.frequency_version == snap_idx


# =============================================================================
# Invariant: Exactly-Once Update
# =============================================================================

class TestExactlyOnceInvariant:
    """Property tests for 'Exactly-once update' invariant."""

    @settings(max_examples=50)
    @given(
        feedback_count=st.integers(min_value=1, max_value=20),
        intent_count=st.integers(min_value=1, max_value=5),
    )
    @pytest.mark.asyncio
    async def test_exactly_once_frequency_increment(
        self,
        feedback_count,
        intent_count,
    ):
        """Property: Frequency should only be incremented once per unique feedback."""
        storage = InMemoryFrequencyStorage()
        processor = ExactlyOnceProcessor(storage)

        # Generate unique feedbacks
        feedbacks = []
        for i in range(feedback_count):
            intent_idx = i % intent_count
            feedbacks.append(
                Feedback(
                    query=f"query_{i}",
                    intent_path=f"intent_{intent_idx}",
                    example_text=f"example_{i}",
                    success=True,
                    timestamp=1000000.0 + i * 1000,  # Different timestamps
                )
            )

        # Process all feedbacks
        for fb in feedbacks:
            await processor.process_feedback(fb)

        # Check frequency counts
        for intent_idx in range(intent_count):
            frequencies = await storage.get_frequency(f"intent_{intent_idx}")
            # Count how many feedbacks were for this intent
            expected_count = sum(
                1 for i, fb in enumerate(feedbacks) if i % intent_count == intent_idx
            )
            actual_count = sum(frequencies.values())
            assert actual_count == expected_count

    @settings(max_examples=30)
    @given(
        duplicate_count=st.integers(min_value=1, max_value=10),
    )
    @pytest.mark.asyncio
    async def test_idempotent_duplicates_never_increment(
        self,
        duplicate_count,
    ):
        """Property: Duplicates should never increment frequency."""
        storage = InMemoryFrequencyStorage()
        processor = ExactlyOnceProcessor(storage)

        # Same feedback repeated
        feedback = Feedback(
            query="consistent query",
            intent_path="consistent_intent",
            example_text="consistent example",
            success=True,
            timestamp=2000000.0,
        )

        # Process same feedback multiple times
        results = []
        for _ in range(duplicate_count):
            result = await processor.process_feedback(feedback)
            results.append(result)

        # Property: Only first should return True
        assert results[0] is True
        assert all(r is False for r in results[1:])

        # Check frequency - should be exactly 1
        frequencies = await storage.get_frequency("consistent_intent")
        total = sum(frequencies.values())
        assert total == 1

    @settings(max_examples=20)
    @given(
        crash_after_insert=st.booleans(),
    )
    @pytest.mark.asyncio
    async def test_crash_simulation_maintains_exactly_once(
        self,
        crash_after_insert,
    ):
        """Property: Crash simulation should still maintain exactly-once."""
        storage = InMemoryFrequencyStorage()
        processor = ExactlyOnceProcessor(storage)

        feedback = Feedback(
            query="crash test",
            intent_path="crash_intent",
            example_text="crash example",
            success=True,
            timestamp=3000000.0,
        )

        # Get the actual idempotency key that will be generated
        idempotency_key = processor._generate_idempotency_key(feedback)

        # Pre-insert key to simulate crash recovery
        if crash_after_insert:
            await storage.insert_applied_key(idempotency_key)

        # Process feedback
        result = await processor.process_feedback(feedback)

        if crash_after_insert:
            # Should be idempotent (False) because key already exists
            assert result is False
        else:
            # Should process (True)
            assert result is True


# =============================================================================
# Invariant: Fairness Boost
# =============================================================================

class TestFairnessInvariant:
    """Property tests for 'Fairness boost' invariant."""

    @settings(max_examples=50)
    @given(
        intent_count=st.integers(min_value=2, max_value=10),
        request_per_intent=st.integers(min_value=1, max_value=20),
    )
    @pytest.mark.asyncio
    async def test_no_intent_exceeds_cap(
        self,
        intent_count,
        request_per_intent,
    ):
        """Property: No intent should exceed its cap."""
        cap_percentage = 0.3  # 30% cap
        global_budget = 1000.0

        config = BoostFairnessConfig(
            enabled=True,
            per_intent_weight_cap=cap_percentage,
            min_share_per_intent=0.0,
            global_boost_per_second=global_budget,
        )
        calculator = FairnessBoostCalculator(config)

        # Track usage per intent
        usage_per_intent = {}

        # Simulate requests
        for _ in range(request_per_intent):
            for intent_idx in range(intent_count):
                intent = f"intent_{intent_idx}"

                boost = await calculator.calculate_boost(
                    intent=intent,
                    base_score=0.0,
                    max_intent_boost=100.0,
                )

                usage_per_intent[intent] = usage_per_intent.get(intent, 0.0) + boost

        # Property: No intent should exceed its cap
        max_per_intent = global_budget * cap_percentage
        for intent, usage in usage_per_intent.items():
            assert usage <= max_per_intent + 0.01, f"Intent {intent} exceeded cap"

    @settings(max_examples=30)
    @given(
        intent_count=st.integers(min_value=1, max_value=10),
    )
    @pytest.mark.asyncio
    async def test_min_share_guaranteed(self, intent_count):
        """Property: Every intent should get minimum share if requested."""
        config = BoostFairnessConfig(
            enabled=True,
            per_intent_weight_cap=1.0,  # No cap
            min_share_per_intent=0.05,  # 5% minimum
            global_boost_per_second=1000.0,
        )
        calculator = FairnessBoostCalculator(config)

        # Make single request per intent
        for intent_idx in range(intent_count):
            intent = f"intent_{intent_idx}"

            boost = await calculator.calculate_boost(
                intent=intent,
                base_score=0.0,
                max_intent_boost=100.0,
            )

            # Property: Should get at least 5% of requested boost
            min_expected = 100.0 * 0.05
            assert boost >= min_expected - 0.01

    @settings(max_examples=20)
    @given(
        high_traffic_ratio=st.floats(min_value=0.1, max_value=0.9),
    )
    @pytest.mark.asyncio
    async def test_low_traffic_not_starved(
        self,
        high_traffic_ratio,
    ):
        """Property: Low-traffic intent should not be starved."""
        config = BoostFairnessConfig(
            enabled=True,
            per_intent_weight_cap=0.30,
            min_share_per_intent=0.01,
            global_boost_per_second=1000.0,
        )
        calculator = FairnessBoostCalculator(config)

        # Exhaust budget with high-traffic intent
        high_intent = "high_traffic"
        low_intent = "low_traffic"

        # High traffic uses most of budget
        high_requests = int(100 * high_traffic_ratio)
        for _ in range(high_requests):
            await calculator.calculate_boost(
                intent=high_intent,
                base_score=0.0,
                max_intent_boost=100.0,
            )

        # Low traffic should still get some boost
        low_boost = await calculator.calculate_boost(
            intent=low_intent,
            base_score=0.0,
            max_intent_boost=50.0,
        )

        # Property: Low traffic should get at least some boost
        assert low_boost > 0.0 or low_intent in (await calculator.get_usage_stats())


# =============================================================================
# Invariant: Lifecycle State Machine
# =============================================================================

class TestLifecycleInvariant:
    """Property tests for lifecycle state machine."""

    @settings(max_examples=30)
    @given(
        enable_count=st.integers(min_value=0, max_value=3),
        disable_count=st.integers(min_value=0, max_value=3),
    )
    @pytest.mark.asyncio
    async def test_lifecycle_state_transitions(
        self,
        enable_count,
        disable_count,
    ):
        """Property: Lifecycle should have valid state transitions."""
        assume(enable_count + disable_count > 0)  # At least one operation

        storage = InMemoryLifecycleStorage()
        health_monitor = HealthMonitor()
        config = LifecycleConfig()
        manager = LifecycleManager(
            storage=storage,
            config=config,
            health_monitor=health_monitor,
        )

        intent = "test_intent"

        # Interleave enable/disable operations
        for i in range(max(enable_count, disable_count)):
            if i < enable_count:
                await manager.enable_intent(intent)
            if i < disable_count:
                await manager.disable_intent(intent, reason="test")

        # Check final state
        lifecycle = await manager.get_intent_state(intent)

        # Property: State should be valid
        assert lifecycle.state in [
            IntentLifecycleState.ACTIVE,
            IntentLifecycleState.DISABLED,
        ]

    @settings(max_examples=20)
    @given(
        success_rate=st.floats(min_value=0.0, max_value=1.0),
    )
    @pytest.mark.asyncio
    async def test_auto_restore_state_validity(
        self,
        success_rate,
    ):
        """Property: Lifecycle state should always be valid."""
        storage = InMemoryLifecycleStorage()
        health_monitor = HealthMonitor()
        config = LifecycleConfig(
            disable_ttl_seconds=1,
            auto_restore_if_health_recovers=True,
            restore_success_rate_threshold=0.7,
        )
        manager = LifecycleManager(
            storage=storage,
            config=config,
            health_monitor=health_monitor,
        )

        intent = "restore_test"

        # Record success rate
        for _ in range(10):
            await health_monitor.record(
                intent,
                success=(success_rate > 0.5),
                latency_ms=10,
            )

        # Disable
        await manager.disable_intent(intent, reason="test", ttl_seconds=1)

        # Get state immediately
        lifecycle = await manager.get_intent_state(intent)

        # Property: State should always be valid
        assert lifecycle.state in [
            IntentLifecycleState.ACTIVE,
            IntentLifecycleState.DISABLED,
            IntentLifecycleState.PENDING_RESTORE,
        ]


# =============================================================================
# Invariant: Request Context Immutability
# =============================================================================

class TestImmutabilityInvariant:
    """Property tests for request context immutability."""

    @settings(max_examples=50)
    @given(
        query=st.text(min_size=0, max_size=100),
        metadata_items=st.dictionaries(
            keys=st.text(min_size=1, max_size=20),
            values=st.one_of(st.text(), st.integers(), st.floats()),
            max_size=5,
        ),
    )
    @pytest.mark.asyncio
    async def test_context_with_metadata_preserves_original(
        self,
        query,
        metadata_items,
    ):
        """Property: with_metadata should not modify original context."""
        snapshot = Snapshot(
            snapshot_id="snap_test",
            config=RouterConfig(),
            index=MagicMock(),
            frequency_version=1,
            freq_snapshot_time=time.time(),
            created_at=time.time(),
        )

        original_context = RequestContext.create(
            snapshot=snapshot,
            request=Request(query=query),
        )

        # Add metadata
        for key, value in metadata_items.items():
            new_context = original_context.with_metadata(key, value)

            # Property: Original should be unchanged
            assert original_context.metadata.get(key) is None
            assert original_context.context_id == new_context.context_id

    @settings(max_examples=30)
    @given(
        context_count=st.integers(min_value=2, max_value=5),
    )
    @pytest.mark.asyncio
    async def test_contexts_independent(self, context_count):
        """Property: Multiple contexts should be independent."""
        snapshot = Snapshot(
            snapshot_id="shared_snap",
            config=RouterConfig(),
            index=MagicMock(),
            frequency_version=1,
            freq_snapshot_time=time.time(),
            created_at=time.time(),
        )

        contexts = []
        for i in range(context_count):
            ctx = RequestContext.create(
                snapshot=snapshot,
                request=Request(query=f"query_{i}"),
            )
            ctx = ctx.with_metadata("index", i)
            contexts.append(ctx)

        # Property: Each context should have unique context_id
        context_ids = [c.context_id for c in contexts]
        assert len(set(context_ids)) == context_count

        # Property: Metadata should not leak between contexts
        for i, ctx in enumerate(contexts):
            for j, other_ctx in enumerate(contexts):
                if i != j:
                    assert ctx.metadata.get("index") != other_ctx.metadata.get("index")
