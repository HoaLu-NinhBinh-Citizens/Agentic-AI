"""Semantic Router main facade.

Provides unified interface for semantic routing with all consistency guarantees.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from src.infrastructure.router.consistency.read_after_write import ReadAfterWriteGuard
    from src.infrastructure.router.execution_engine import ExecutionEngine
    from src.infrastructure.router.fairness.boost_fairness import FairnessBoostCalculator
    from src.infrastructure.router.observation.feedback_processor import FeedbackProcessor
    from src.infrastructure.router.observation.health_monitor import HealthMonitor
    from src.infrastructure.router.observation.lifecycle_manager import LifecycleManager
    from src.infrastructure.router.policy_engine import PolicyEngine
    from src.infrastructure.router.snapshot import SnapshotManager
    from src.infrastructure.router.types import (
        Feedback,
        FeedbackResult,
        Request,
        RouteResult,
        RouterConfig,
    )

logger = logging.getLogger(__name__)


class SemanticRouter:
    """
    Main facade for semantic routing.
    
    Features:
    - Immutable request context with frozen snapshot
    - Exactly-once frequency updates
    - Read-after-write consistency guard
    - Fairness boost budget
    - Rollback-safe intent lifecycle
    
    Usage:
        router = SemanticRouter(...)
        result = await router.route(request)
        await router.report_feedback(feedback)
    """

    def __init__(
        self,
        config: RouterConfig,
        snapshot_manager: SnapshotManager,
        policy_engine: PolicyEngine,
        execution_engine: ExecutionEngine,
        feedback_processor: FeedbackProcessor,
        lifecycle_manager: LifecycleManager,
        health_monitor: HealthMonitor,
        fairness_calculator: FairnessBoostCalculator,
        consistency_guard: ReadAfterWriteGuard,
    ):
        self._config = config
        self._snapshot_manager = snapshot_manager
        self._policy_engine = policy_engine
        self._execution_engine = execution_engine
        self._feedback_processor = feedback_processor
        self._lifecycle_manager = lifecycle_manager
        self._health_monitor = health_monitor
        self._fairness_calculator = fairness_calculator
        self._consistency_guard = consistency_guard

    async def route(self, request: Request) -> RouteResult:
        """
        Route request to appropriate handler.
        
        Creates immutable context with frozen snapshot, then:
        1. Policy engine evaluates rules
        2. Score engine calculates semantic scores
        3. Execution engine dispatches to handler
        
        Args:
            request: Incoming request
            
        Returns:
            RouteResult with routing decision and execution result
        """
        from src.infrastructure.router.context import RequestContextFactory
        from src.infrastructure.router.types import RequestContext

        context_factory = RequestContextFactory(self._snapshot_manager)
        context = await context_factory.create_context(request)

        available_intents = await self._lifecycle_manager.get_available_intents(
            list(context.frozen_snapshot.config.intents.keys())
        )

        route_result = await self._policy_engine.route(
            context,
            request,
            available_intents=available_intents,
        )

        execution_result = await self._execution_engine.execute(context, route_result)

        if execution_result.success:
            logger.info(
                f"Routed to {route_result.intent} "
                f"(confidence={route_result.confidence:.2f})"
            )
        else:
            logger.warning(
                f"Routing failed for {route_result.intent}: {execution_result.error}"
            )

        return route_result

    async def report_feedback(self, feedback: Feedback) -> FeedbackResult:
        """
        Report feedback for learning.
        
        Processes with exactly-once guarantee and updates consistency guard.
        
        Args:
            feedback: Feedback data
            
        Returns:
            FeedbackResult with processing status
        """
        result = await self._feedback_processor.report_feedback(feedback)

        if result.was_idempotent:
            logger.debug(f"Idempotent feedback processed: {feedback.intent_path}")
        else:
            logger.info(
                f"Feedback processed for {feedback.intent_path} "
                f"(new_snapshot={result.new_snapshot_id})"
            )

        return result

    async def disable_intent(
        self,
        intent_path: str,
        reason: str,
        ttl_seconds: Optional[int] = None,
    ) -> None:
        """
        Disable intent (e.g., due to health issues).
        
        Args:
            intent_path: Intent to disable
            reason: Reason for disabling
            ttl_seconds: Auto-restore TTL
        """
        await self._lifecycle_manager.disable_intent(intent_path, reason, ttl_seconds)

    async def enable_intent(self, intent_path: str) -> None:
        """
        Manually enable intent.
        
        Args:
            intent_path: Intent to enable
        """
        await self._lifecycle_manager.enable_intent(intent_path)

    def get_health_summary(self) -> dict[str, Any]:
        """Get health summary for all intents."""
        return asyncio.get_event_loop().run_until_complete(
            self._health_monitor.get_health_summary()
        )

    def get_fairness_stats(self) -> dict[str, Any]:
        """Get fairness usage statistics."""
        return asyncio.get_event_loop().run_until_complete(
            self._fairness_calculator.get_usage_stats()
        )

    def get_consistency_status(self) -> dict[str, Any]:
        """Get consistency guard status."""
        return self._consistency_guard.get_guard_status()

    def get_snapshot_info(self) -> dict[str, Any]:
        """Get current snapshot info."""
        return self._snapshot_manager.get_snapshot_info()


class SemanticRouterBuilder:
    """
    Builder for SemanticRouter with dependency injection.
    
    Usage:
        builder = SemanticRouterBuilder()
        builder.with_config(config)
        builder.with_storage(InMemoryFrequencyStorage())
        router = await builder.build()
    """

    def __init__(self):
        self._config: Optional[RouterConfig] = None
        self._storage = None
        self._embedding_model = None
        self._ann_index = None

    def with_config(self, config: RouterConfig) -> "SemanticRouterBuilder":
        """Set router configuration."""
        self._config = config
        return self

    def with_storage(self, storage) -> "SemanticRouterBuilder":
        """Set frequency storage."""
        self._storage = storage
        return self

    def with_embedding_model(self, model) -> "SemanticRouterBuilder":
        """Set embedding model."""
        self._embedding_model = model
        return self

    def with_ann_index(self, index) -> "SemanticRouterBuilder":
        """Set ANN index."""
        self._ann_index = index
        return self

    async def build(self) -> SemanticRouter:
        """Build and return SemanticRouter instance."""
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
        from src.infrastructure.router.snapshot import ConfigProvider, SnapshotManager
        from src.infrastructure.router.score_engine import (
            InMemoryANNIndex,
            InMemoryEmbeddingModel,
            ScoreEngine,
        )
        from src.infrastructure.router.types import RouterConfig

        config = self._config or RouterConfig()

        storage = self._storage or InMemoryFrequencyStorage()
        health_monitor = HealthMonitor()
        lifecycle_storage = InMemoryLifecycleStorage()
        lifecycle_manager = LifecycleManager(
            storage=lifecycle_storage,
            config=config.lifecycle,
            health_monitor=health_monitor,
        )
        embedding_model = self._embedding_model or InMemoryEmbeddingModel()
        ann_index = self._ann_index or InMemoryANNIndex()
        fairness_calculator = FairnessBoostCalculator(config.boost_fairness)

        exactly_once = ExactlyOnceProcessor(storage)
        config_provider = ConfigProvider()
        snapshot_manager = SnapshotManager(config_provider)
        consistency_guard = ReadAfterWriteGuard(
            config=config.consistency,
            snapshot_manager=snapshot_manager,
        )

        feedback_processor = FeedbackProcessor(
            exactly_once=exactly_once,
            consistency_guard=consistency_guard,
            snapshot_manager=snapshot_manager,
        )

        score_engine = ScoreEngine(
            embedding_model=embedding_model,
            ann_index=ann_index,
            fairness_calculator=fairness_calculator,
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

        return SemanticRouter(
            config=config,
            snapshot_manager=snapshot_manager,
            policy_engine=policy_engine,
            execution_engine=execution_engine,
            feedback_processor=feedback_processor,
            lifecycle_manager=lifecycle_manager,
            health_monitor=health_monitor,
            fairness_calculator=fairness_calculator,
            consistency_guard=consistency_guard,
        )
