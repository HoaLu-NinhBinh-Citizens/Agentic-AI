"""Pytest configuration for semantic router tests."""

from __future__ import annotations

import asyncio
import time
from typing import Any, AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

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
from src.infrastructure.router.score_engine import (
    ANNNeighbor,
    InMemoryANNIndex,
    InMemoryEmbeddingModel,
    ScoreEngine,
)
from src.infrastructure.router.snapshot import ConfigProvider, SnapshotManager
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


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def router_config() -> RouterConfig:
    """Create test router configuration."""
    intents = {
        "code_generation": IntentConfig(
            name="code_generation",
            base_score=0.8,
            priority=10,
            handler="CodeGenHandler",
            rules=[
                RoutingRule(
                    pattern="generate|create|write code",
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
            rules=[
                RoutingRule(
                    pattern="query|select|find data",
                    intent="data_query",
                    confidence=0.85,
                    needs_semantic=False,
                    priority=8,
                )
            ],
        ),
        "rag": IntentConfig(
            name="rag",
            base_score=0.6,
            priority=3,
            handler="RAGHandler",
        ),
        "unknown": IntentConfig(
            name="unknown",
            base_score=0.1,
            priority=1,
            handler="UnknownHandler",
        ),
    }

    return RouterConfig(
        default_intent="unknown",
        fallback_enabled=True,
        intents=intents,
        consistency=ConsistencyConfig(
            read_after_write_guard_ms=5000,
            force_new_snapshot_on_feedback=False,
            warn_on_stale_snapshot=True,
        ),
        boost_fairness=BoostFairnessConfig(
            enabled=True,
            per_intent_weight_cap=0.30,
            min_share_per_intent=0.01,
            global_boost_per_second=1000,
        ),
        lifecycle=LifecycleConfig(
            disable_ttl_seconds=86400,
            auto_restore_if_health_recovers=True,
            restore_success_rate_threshold=0.7,
            restore_observation_window_hours=1,
        ),
    )


@pytest.fixture
def embedding_model() -> InMemoryEmbeddingModel:
    """Create in-memory embedding model."""
    return InMemoryEmbeddingModel(dimension=128)


@pytest.fixture
def ann_index(embedding_model: InMemoryEmbeddingModel) -> InMemoryANNIndex:
    """Create ANN index with test data."""
    index = InMemoryANNIndex(dimension=128)

    async def seed_index():
        examples = [
            ("code_generation", "write a function to sort a list"),
            ("code_generation", "create a class for user authentication"),
            ("code_generation", "implement binary search algorithm"),
            ("data_query", "find all users with active status"),
            ("data_query", "query the database for recent orders"),
            ("data_query", "search for products in category"),
            ("rag", "retrieve relevant documents about policy"),
            ("rag", "find information about the company"),
        ]

        for intent, text in examples:
            embedding = await embedding_model.embed(text)
            await index.add(intent, text, embedding)

    asyncio.get_event_loop().run_until_complete(seed_index())
    return index


@pytest.fixture
def frequency_storage() -> InMemoryFrequencyStorage:
    """Create in-memory frequency storage."""
    return InMemoryFrequencyStorage()


@pytest.fixture
def health_monitor() -> HealthMonitor:
    """Create health monitor."""
    return HealthMonitor(window_size=100)


@pytest.fixture
def lifecycle_storage() -> InMemoryLifecycleStorage:
    """Create in-memory lifecycle storage."""
    return InMemoryLifecycleStorage()


@pytest.fixture
def fairness_config() -> BoostFairnessConfig:
    """Create fairness configuration."""
    return BoostFairnessConfig(
        enabled=True,
        per_intent_weight_cap=0.30,
        min_share_per_intent=0.01,
        global_boost_per_second=1000,
    )


@pytest.fixture
def consistency_config() -> ConsistencyConfig:
    """Create consistency configuration."""
    return ConsistencyConfig(
        read_after_write_guard_ms=5000,
        force_new_snapshot_on_feedback=False,
        warn_on_stale_snapshot=True,
    )


@pytest.fixture
def fairness_calculator(fairness_config: BoostFairnessConfig) -> FairnessBoostCalculator:
    """Create fairness calculator."""
    return FairnessBoostCalculator(fairness_config)


@pytest_asyncio.fixture
async def snapshot_manager(
    router_config: RouterConfig,
    ann_index: InMemoryANNIndex,
    frequency_storage: InMemoryFrequencyStorage,
) -> SnapshotManager:
    """Create snapshot manager with test data."""
    provider = TestConfigProvider(
        config=router_config,
        ann_index=ann_index,
        frequency_version=1,
    )
    manager = SnapshotManager(provider)
    await manager.create_snapshot()
    return manager


@pytest_asyncio.fixture
async def lifecycle_manager(
    lifecycle_storage: InMemoryLifecycleStorage,
    health_monitor: HealthMonitor,
    router_config: RouterConfig,
) -> LifecycleManager:
    """Create lifecycle manager."""
    return LifecycleManager(
        storage=lifecycle_storage,
        config=router_config.lifecycle,
        health_monitor=health_monitor,
    )


@pytest_asyncio.fixture
async def score_engine(
    embedding_model: InMemoryEmbeddingModel,
    ann_index: InMemoryANNIndex,
    fairness_calculator: FairnessBoostCalculator,
) -> ScoreEngine:
    """Create score engine."""
    return ScoreEngine(
        embedding_model=embedding_model,
        ann_index=ann_index,
        fairness_calculator=fairness_calculator,
    )


@pytest_asyncio.fixture
async def policy_engine_config(router_config: RouterConfig) -> PolicyEngineConfig:
    """Create policy engine configuration."""
    return PolicyEngineConfig(
        default_intent=router_config.default_intent,
        fallback_enabled=router_config.fallback_enabled,
        min_confidence_threshold=0.3,
    )


@pytest_asyncio.fixture
async def policy_engine(
    policy_engine_config: PolicyEngineConfig,
    score_engine: ScoreEngine,
) -> PolicyEngine:
    """Create policy engine."""
    return PolicyEngine(
        config=policy_engine_config,
        score_engine=score_engine,
    )


@pytest_asyncio.fixture
async def execution_engine(
    health_monitor: HealthMonitor,
) -> ExecutionEngine:
    """Create execution engine."""
    return ExecutionEngine(health_monitor=health_monitor)


@pytest_asyncio.fixture
async def exactly_once_processor(
    frequency_storage: InMemoryFrequencyStorage,
) -> ExactlyOnceProcessor:
    """Create exactly-once processor."""
    return ExactlyOnceProcessor(frequency_storage)


@pytest_asyncio.fixture
async def consistency_guard(
    consistency_config: ConsistencyConfig,
    snapshot_manager: SnapshotManager,
) -> ReadAfterWriteGuard:
    """Create read-after-write guard."""
    return ReadAfterWriteGuard(
        config=consistency_config,
        snapshot_manager=snapshot_manager,
    )


@pytest_asyncio.fixture
async def feedback_processor(
    exactly_once_processor: ExactlyOnceProcessor,
    consistency_guard: ReadAfterWriteGuard,
    snapshot_manager: SnapshotManager,
) -> FeedbackProcessor:
    """Create feedback processor."""
    return FeedbackProcessor(
        exactly_once=exactly_once_processor,
        consistency_guard=consistency_guard,
        snapshot_manager=snapshot_manager,
    )


@pytest.fixture
def mock_request() -> Request:
    """Create a test request."""
    return Request(
        query="write a function to sort a list",
        session_id="test-session-123",
        user_id="test-user-456",
    )


@pytest.fixture
def mock_feedback() -> Feedback:
    """Create a test feedback."""
    return Feedback(
        query="write a function to sort a list",
        intent_path="code_generation",
        example_text="write a function to sort a list",
        success=True,
        timestamp=time.time(),
    )


@pytest.fixture
def snapshot_with_intents(
    router_config: RouterConfig,
    ann_index: InMemoryANNIndex,
) -> Snapshot:
    """Create a snapshot with test intents."""
    return Snapshot(
        snapshot_id="test-snapshot-001",
        config=router_config,
        index=ann_index,
        frequency_version=1,
        freq_snapshot_time=time.time(),
        created_at=time.time(),
    )


@pytest.fixture
def request_context(
    snapshot_with_intents: Snapshot,
    mock_request: Request,
) -> RequestContext:
    """Create a test request context."""
    return RequestContext.create(
        snapshot=snapshot_with_intents,
        request=mock_request,
    )


class TestConfigProvider(ConfigProvider):
    """Test config provider with custom data."""

    def __init__(
        self,
        config: RouterConfig,
        ann_index: Any,
        frequency_version: int,
    ):
        self._config = config
        self._ann_index = ann_index
        self._frequency_version = frequency_version

    async def get_config(self) -> RouterConfig:
        return self._config

    async def get_frequency_version(self) -> int:
        return self._frequency_version

    async def get_ann_index(self) -> Any:
        return self._ann_index


class MockEmbeddingModel:
    """Mock embedding model for testing failures."""

    def __init__(self, should_fail: bool = False):
        self._should_fail = should_fail

    async def embed(self, text: str) -> list[float]:
        if self._should_fail:
            raise TimeoutError("Embedding timeout")
        return [0.1] * 128


class MockANNIndex:
    """Mock ANN index for testing failures."""

    def __init__(self, should_fail: bool = False):
        self._should_fail = should_fail
        self._vectors: list[tuple[str, str, list[float]]] = []

    async def search(
        self,
        query_embedding: list[float],
        k: int = 10,
    ) -> list[ANNNeighbor]:
        if self._should_fail:
            raise ConnectionError("ANN index unavailable")
        return []

    async def add(
        self,
        intent_path: str,
        example_text: str,
        embedding: list[float],
    ) -> None:
        self._vectors.append((intent_path, example_text, embedding))
