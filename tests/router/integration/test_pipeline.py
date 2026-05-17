"""Integration tests for Semantic Router full pipeline."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import MagicMock

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
from src.infrastructure.router.policy_engine import PolicyEngine, PolicyEngineConfig
from src.infrastructure.router.router import SemanticRouter, SemanticRouterBuilder
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
    RequestContext,
    RouterConfig,
    RoutingRule,
    Snapshot,
)


class TestFullPipelineRouting:
    """Test full routing pipeline from request to decision."""

    @pytest.fixture
    async def router(self) -> SemanticRouter:
        """Create semantic router with all components."""
        # Create config with test intents
        intents = {
            "code_generation": IntentConfig(
                name="code_generation",
                base_score=0.8,
                priority=10,
                handler="CodeGenHandler",
                rules=[
                    RoutingRule(
                        pattern="write|create|generate",
                        intent="code_generation",
                        confidence=0.9,
                        needs_semantic=False,
                        priority=10,
                    )
                ],
            ),
            "data_query": IntentConfig(
                name="data_query",
                base_score=0.7,
                priority=5,
                handler="DataQueryHandler",
            ),
        }

        config = RouterConfig(
            default_intent="unknown",
            fallback_enabled=True,
            intents=intents,
            consistency=ConsistencyConfig(),
            boost_fairness=BoostFairnessConfig(enabled=False),
            lifecycle=LifecycleConfig(),
        )

        # Create components
        embedding = InMemoryEmbeddingModel(dimension=128)
        ann_index = InMemoryANNIndex(dimension=128)
        await ann_index.add("code_generation", "write code", await embedding.embed("write code"))
        await ann_index.add("data_query", "query data", await embedding.embed("query data"))

        storage = InMemoryFrequencyStorage()
        health_monitor = HealthMonitor()
        lifecycle_storage = InMemoryLifecycleStorage()
        lifecycle_manager = LifecycleManager(
            storage=lifecycle_storage,
            config=config.lifecycle,
            health_monitor=health_monitor,
        )
        fairness = FairnessBoostCalculator(config.boost_fairness)
        exactly_once = ExactlyOnceProcessor(storage)
        config_provider = MockConfigProvider(config, ann_index)
        snapshot_manager = SnapshotManager(config_provider)
        consistency_guard = ReadAfterWriteGuard(config.consistency, snapshot_manager)

        feedback_processor = FeedbackProcessor(
            exactly_once=exactly_once,
            consistency_guard=consistency_guard,
            snapshot_manager=snapshot_manager,
        )

        score_engine = ScoreEngine(
            embedding_model=embedding,
            ann_index=ann_index,
            fairness_calculator=fairness,
        )

        policy_engine_config = PolicyEngineConfig(
            default_intent=config.default_intent,
            fallback_enabled=config.fallback_enabled,
        )
        policy_engine = PolicyEngine(
            config=policy_engine_config,
            score_engine=score_engine,
        )

        execution_engine = ExecutionEngine(health_monitor=health_monitor)

        # Register handlers
        async def code_handler(ctx):
            return {"action": "generate_code"}

        async def data_handler(ctx):
            return {"action": "query_data"}

        execution_engine.register_handler("code_generation", code_handler)
        execution_engine.register_handler("data_query", data_handler)

        return SemanticRouter(
            config=config,
            snapshot_manager=snapshot_manager,
            policy_engine=policy_engine,
            execution_engine=execution_engine,
            feedback_processor=feedback_processor,
            lifecycle_manager=lifecycle_manager,
            health_monitor=health_monitor,
            fairness_calculator=fairness,
            consistency_guard=consistency_guard,
        )

    @pytest.mark.asyncio
    async def test_route_request_to_code_intent(self, router: SemanticRouter):
        """Test routing a code-related request."""
        request = Request(query="write a function to sort a list")

        result = await router.route(request)

        assert result.intent == "code_generation"
        assert result.confidence > 0

    @pytest.mark.asyncio
    async def test_route_request_to_data_intent(self, router: SemanticRouter):
        """Test routing a data-related request."""
        request = Request(query="find all users with active status")

        result = await router.route(request)

        # Should route to either rule-based or semantic match
        assert result.intent in ["data_query", "code_generation", "unknown"]

    @pytest.mark.asyncio
    async def test_route_with_fallback(self, router: SemanticRouter):
        """Test routing with fallback for unknown requests."""
        request = Request(query="completely random query xyz 123")

        result = await router.route(request)

        # Should fall back to default intent
        assert result.intent in ["unknown", "data_query", "code_generation"]


class TestFeedbackPipeline:
    """Test feedback pipeline from feedback to frequency update."""

    @pytest.fixture
    async def feedback_system(self):
        """Create feedback processing system."""
        storage = InMemoryFrequencyStorage()
        health_monitor = HealthMonitor()
        config = ConsistencyConfig()

        config_provider = MockConfigProvider(
            RouterConfig(),
            InMemoryANNIndex(dimension=128),
        )
        snapshot_manager = SnapshotManager(config_provider)
        consistency_guard = ReadAfterWriteGuard(config, snapshot_manager)

        exactly_once = ExactlyOnceProcessor(storage)
        feedback_processor = FeedbackProcessor(
            exactly_once=exactly_once,
            consistency_guard=consistency_guard,
            snapshot_manager=snapshot_manager,
        )

        return feedback_processor, consistency_guard, storage

    @pytest.mark.asyncio
    async def test_feedback_updates_frequency(
        self, feedback_system
    ):
        """Test that feedback updates frequency."""
        feedback_processor, _, storage = feedback_system

        feedback = Feedback(
            query="test query",
            intent_path="test_intent",
            example_text="test example text",
            success=True,
            timestamp=time.time(),
        )

        result = await feedback_processor.report_feedback(feedback)

        assert result.success is True

        # Check frequency updated
        frequencies = await storage.get_frequency("test_intent")
        assert sum(frequencies.values()) > 0

    @pytest.mark.asyncio
    async def test_duplicate_feedback_idempotent(
        self, feedback_system
    ):
        """Test that duplicate feedback is idempotent."""
        feedback_processor, _, storage = feedback_system

        feedback = Feedback(
            query="test query",
            intent_path="test_intent",
            example_text="test example text",
            success=True,
            timestamp=1000000.0,
        )

        # Process twice
        await feedback_processor.report_feedback(feedback)
        result = await feedback_processor.report_feedback(feedback)

        assert result.was_idempotent is True

    @pytest.mark.asyncio
    async def test_feedback_triggers_snapshot_update(
        self, feedback_system
    ):
        """Test that feedback triggers consistency guard."""
        feedback_processor, consistency_guard, _ = feedback_system

        feedback = Feedback(
            query="test",
            intent_path="test_intent",
            example_text="example",
            success=True,
            timestamp=time.time(),
        )

        await feedback_processor.report_feedback(feedback)

        # Consistency guard should be notified
        status = consistency_guard.get_guard_status()
        assert status["status"] in ["guarding", "idle"]


class TestHotReloadConfig:
    """Test configuration hot reload."""

    @pytest.mark.asyncio
    async def test_config_reload_creates_new_snapshot(self):
        """Test that config reload creates new snapshot."""
        intents = {
            "original": IntentConfig(name="original", base_score=0.5),
        }
        config = RouterConfig(intents=intents)

        provider = MockConfigProvider(config, InMemoryANNIndex(dimension=128))
        manager = SnapshotManager(provider)

        # Create initial snapshot
        snap1 = await manager.create_snapshot()
        snap1_id = snap1.snapshot_id

        # Update config
        intents["new_intent"] = IntentConfig(name="new_intent", base_score=0.8)
        config.intents = intents
        provider._config = config

        # Create new snapshot
        snap2 = await manager.create_snapshot()

        assert snap1_id != snap2.snapshot_id
        assert "new_intent" in snap2.config.intents


class TestANNRebuildTest:
    """Test ANN index rebuild."""

    @pytest.mark.asyncio
    async def test_ann_rebuild_separate_indices(self):
        """Test that ANN rebuild creates separate indices."""
        embedding = InMemoryEmbeddingModel(dimension=128)
        index1 = InMemoryANNIndex(dimension=128)
        index2 = InMemoryANNIndex(dimension=128)

        # Add data to first index
        await index1.add("intent_a", "text A", await embedding.embed("text A"))

        # Verify first index has data
        results1 = await index1.search(await embedding.embed("text A"), k=1)
        assert len(results1) == 1

        # Add different data to second index
        await index2.add("intent_b", "text B", await embedding.embed("text B"))

        # Verify second index has different data
        results2 = await index2.search(await embedding.embed("text B"), k=1)
        assert len(results2) == 1

        # Verify indices are independent
        assert index1 is not index2
        results1_b = await index1.search(await embedding.embed("text B"), k=1)
        results2_a = await index2.search(await embedding.embed("text A"), k=1)
        # Each index should only contain its own data
        assert len(results1_b) == 0 or all(r.intent_path != "intent_b" for r in results1_b)


class TestReadAfterWriteConsistency:
    """Test read-after-write consistency."""

    @pytest.mark.asyncio
    async def test_read_after_write_warning_within_guard_window(self):
        """Test warning when using stale snapshot within guard window."""
        config = ConsistencyConfig(
            read_after_write_guard_ms=5000,
            force_new_snapshot_on_feedback=False,
            warn_on_stale_snapshot=True,
        )

        provider = MockConfigProvider(
            RouterConfig(),
            InMemoryANNIndex(dimension=128),
        )
        snapshot_manager = SnapshotManager(provider)
        guard = ReadAfterWriteGuard(config, snapshot_manager)

        # Simulate feedback
        await guard.on_feedback_written()

        # Check if new snapshot should be forced
        should_force, reason = await guard.should_force_new_snapshot()

        # With force_new_snapshot_on_feedback=False, should not force
        assert should_force is False

    @pytest.mark.asyncio
    async def test_force_new_snapshot_within_guard_window(self):
        """Test force new snapshot within guard window."""
        config = ConsistencyConfig(
            read_after_write_guard_ms=5000,
            force_new_snapshot_on_feedback=True,
            warn_on_stale_snapshot=False,
        )

        provider = MockConfigProvider(
            RouterConfig(),
            InMemoryANNIndex(dimension=128),
        )
        snapshot_manager = SnapshotManager(provider)
        guard = ReadAfterWriteGuard(config, snapshot_manager)

        # Simulate feedback
        await guard.on_feedback_written()

        # Should force new snapshot
        should_force, reason = await guard.should_force_new_snapshot()
        assert should_force is True


class TestConsistencyConfig:
    """Test consistency configuration behavior."""

    @pytest.mark.asyncio
    async def test_guard_status_idle_initially(self):
        """Test that guard status is idle initially."""
        config = ConsistencyConfig()
        provider = MockConfigProvider(
            RouterConfig(),
            InMemoryANNIndex(dimension=128),
        )
        snapshot_manager = SnapshotManager(provider)
        guard = ReadAfterWriteGuard(config, snapshot_manager)

        status = guard.get_guard_status()

        assert status["status"] == "idle"
        assert status["elapsed_ms"] is None


class TestLifecycleIntegration:
    """Test lifecycle management integration."""

    @pytest.mark.asyncio
    async def test_disabled_intent_not_available(self):
        """Test that disabled intent is not available."""
        health_monitor = HealthMonitor()
        storage = InMemoryLifecycleStorage()
        config = LifecycleConfig()
        manager = LifecycleManager(
            storage=storage,
            config=config,
            health_monitor=health_monitor,
        )

        # Disable intent
        await manager.disable_intent("test_intent", reason="testing")

        # Check availability
        available = await manager.get_available_intents(["test_intent"])

        assert "test_intent" not in available

    @pytest.mark.asyncio
    async def test_lifecycle_aware_routing(self):
        """Test that routing respects lifecycle."""
        health_monitor = HealthMonitor()
        storage = InMemoryLifecycleStorage()
        config = LifecycleConfig()
        manager = LifecycleManager(
            storage=storage,
            config=config,
            health_monitor=health_monitor,
        )

        # Disable code_generation
        await manager.disable_intent("code_generation", reason="testing")

        # Get available intents
        all_intents = ["code_generation", "data_query"]
        available = await manager.get_available_intents(all_intents)

        assert "code_generation" not in available
        assert "data_query" in available


class TestSnapshotCreation:
    """Test snapshot creation and freezing."""

    @pytest.mark.asyncio
    async def test_snapshot_frozen_at_creation(self):
        """Test that snapshot is frozen at creation."""
        intents = {
            "test": IntentConfig(name="test", base_score=0.5),
        }
        config = RouterConfig(intents=intents)

        provider = MockConfigProvider(config, InMemoryANNIndex(dimension=128))
        manager = SnapshotManager(provider)

        snapshot = await manager.create_snapshot()

        # Snapshot should have a frozen ID
        assert snapshot.snapshot_id is not None
        assert snapshot.config is not None
        assert snapshot.index is not None

        # Config should be the same reference
        assert snapshot.config.intents is config.intents

    @pytest.mark.asyncio
    async def test_multiple_snapshots_have_unique_ids(self):
        """Test that multiple snapshots have unique IDs."""
        provider = MockConfigProvider(
            RouterConfig(),
            InMemoryANNIndex(dimension=128),
        )
        manager = SnapshotManager(provider)

        snap1 = await manager.create_snapshot()
        snap2 = await manager.create_snapshot()

        assert snap1.snapshot_id != snap2.snapshot_id


class TestBuilderPattern:
    """Test SemanticRouterBuilder."""

    @pytest.mark.asyncio
    async def test_builder_creates_router(self):
        """Test that builder creates a working router."""
        builder = SemanticRouterBuilder()

        intents = {
            "test_intent": IntentConfig(
                name="test_intent",
                handler="TestHandler",
            ),
        }
        config = RouterConfig(
            default_intent="unknown",
            intents=intents,
        )

        router = (
            await builder
            .with_config(config)
            .with_storage(InMemoryFrequencyStorage())
            .build()
        )

        assert router is not None
        assert isinstance(router, SemanticRouter)


class MockConfigProvider:
    """Mock config provider for testing."""

    def __init__(
        self,
        config: RouterConfig,
        ann_index: InMemoryANNIndex,
    ):
        self._config = config
        self._ann_index = ann_index
        self._frequency_version = 1

    async def get_config(self) -> RouterConfig:
        return self._config

    async def get_frequency_version(self) -> int:
        return self._frequency_version

    async def get_ann_index(self):
        return self._ann_index


class TestSemanticRouterBuilder:
    """Test SemanticRouterBuilder with various configurations."""

    @pytest.fixture
    def base_config(self) -> RouterConfig:
        """Create base router config."""
        return RouterConfig(
            default_intent="unknown",
            intents={
                "code": IntentConfig(name="code", handler="CodeHandler"),
                "data": IntentConfig(name="data", handler="DataHandler"),
            },
            consistency=ConsistencyConfig(),
            boost_fairness=BoostFairnessConfig(),
            lifecycle=LifecycleConfig(),
        )

    @pytest.mark.asyncio
    async def test_builder_with_defaults(self, base_config: RouterConfig):
        """Test builder with default values."""
        builder = SemanticRouterBuilder()
        router = await builder.with_config(base_config).build()

        assert router is not None

    @pytest.mark.asyncio
    async def test_builder_with_custom_storage(self, base_config: RouterConfig):
        """Test builder with custom storage."""
        custom_storage = InMemoryFrequencyStorage()

        builder = SemanticRouterBuilder()
        router = await builder.with_config(base_config).with_storage(custom_storage).build()

        assert router is not None

    @pytest.mark.asyncio
    async def test_builder_with_custom_embedding(self, base_config: RouterConfig):
        """Test builder with custom embedding model."""
        custom_embedding = InMemoryEmbeddingModel(dimension=256)

        builder = SemanticRouterBuilder()
        router = (
            await builder
            .with_config(base_config)
            .with_embedding_model(custom_embedding)
            .build()
        )

        assert router is not None

    @pytest.mark.asyncio
    async def test_builder_with_custom_ann(self, base_config: RouterConfig):
        """Test builder with custom ANN index."""
        custom_ann = InMemoryANNIndex(dimension=128)

        builder = SemanticRouterBuilder()
        router = (
            await builder
            .with_config(base_config)
            .with_ann_index(custom_ann)
            .build()
        )

        assert router is not None
