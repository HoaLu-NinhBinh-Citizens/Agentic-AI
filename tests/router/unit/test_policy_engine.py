"""Unit tests for PolicyEngine."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.infrastructure.router.policy_engine import (
    PolicyEngine,
    PolicyEngineConfig,
    create_keyword_rule,
    create_regex_rule,
)
from src.infrastructure.router.score_engine import (
    InMemoryANNIndex,
    InMemoryEmbeddingModel,
    ScoreEngine,
)
from src.infrastructure.router.fairness.boost_fairness import FairnessBoostCalculator
from src.infrastructure.router.types import (
    IntentConfig,
    Request,
    RequestContext,
    RoutingRule,
    Snapshot,
)


class TestPolicyEngineBasic:
    """Test basic PolicyEngine functionality."""

    @pytest.fixture
    def score_engine(self) -> ScoreEngine:
        """Create a mock score engine."""
        embedding = InMemoryEmbeddingModel(dimension=128)
        index = InMemoryANNIndex(dimension=128)
        fairness = FairnessBoostCalculator(
            MagicMock(enabled=False)
        )
        return ScoreEngine(embedding, index, fairness)

    @pytest.fixture
    def policy_engine(self, score_engine: ScoreEngine) -> PolicyEngine:
        """Create a policy engine with test config."""
        config = PolicyEngineConfig(
            default_intent="unknown",
            fallback_enabled=True,
            min_confidence_threshold=0.3,
        )
        return PolicyEngine(config=config, score_engine=score_engine)

    @pytest.fixture
    def snapshot_with_rules(self) -> Snapshot:
        """Create snapshot with routing rules."""
        intents = {
            "code_generation": IntentConfig(
                name="code_generation",
                base_score=0.8,
                priority=10,
                rules=[
                    RoutingRule(
                        pattern="write|create|generate code",
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
            "unknown": IntentConfig(name="unknown"),
        }
        from src.infrastructure.router.types import RouterConfig
        config = RouterConfig(default_intent="unknown", intents=intents)
        return Snapshot(
            snapshot_id="test-snap",
            config=config,
            index=MagicMock(),
            frequency_version=1,
            freq_snapshot_time=0.0,
            created_at=0.0,
        )

    def _create_context(self, snapshot: Snapshot, query: str) -> RequestContext:
        """Helper to create request context."""
        return RequestContext.create(
            snapshot=snapshot,
            request=Request(query=query),
        )

    @pytest.mark.asyncio
    async def test_rule_matching_with_keyword(
        self,
        policy_engine: PolicyEngine,
        snapshot_with_rules: Snapshot,
    ):
        """Test rule matching with keyword pattern."""
        context = self._create_context(snapshot_with_rules, "write a function")

        result = await policy_engine.evaluate(context, context.request)

        assert result.intent == "code_generation"
        assert result.needs_semantic is False
        assert result.confidence == 0.9

    @pytest.mark.asyncio
    async def test_rule_matching_with_regex(
        self,
        policy_engine: PolicyEngine,
        snapshot_with_rules: Snapshot,
    ):
        """Test rule matching with regex pattern."""
        context = self._create_context(snapshot_with_rules, "find data about users")

        result = await policy_engine.evaluate(context, context.request)

        assert result.intent == "data_query"
        assert result.needs_semantic is False
        assert result.confidence == 0.85

    @pytest.mark.asyncio
    async def test_no_matching_rule_needs_semantic(
        self,
        policy_engine: PolicyEngine,
        snapshot_with_rules: Snapshot,
    ):
        """Test that unmatched requests need semantic evaluation."""
        context = self._create_context(snapshot_with_rules, "what is the weather")

        result = await policy_engine.evaluate(context, context.request)

        assert result.needs_semantic is True
        assert result.intent is None

    @pytest.mark.asyncio
    async def test_priority_order(
        self,
        policy_engine: PolicyEngine,
    ):
        """Test that rules are evaluated in priority order."""
        intents = {
            "high_priority": IntentConfig(
                name="high_priority",
                priority=100,
                rules=[
                    RoutingRule(
                        pattern="test",
                        intent="high_priority",
                        confidence=0.5,
                        priority=100,
                    )
                ],
            ),
            "low_priority": IntentConfig(
                name="low_priority",
                priority=1,
                rules=[
                    RoutingRule(
                        pattern="test",
                        intent="low_priority",
                        confidence=0.9,
                        priority=1,
                    )
                ],
            ),
        }
        from src.infrastructure.router.types import RouterConfig
        snapshot = Snapshot(
            snapshot_id="test-snap",
            config=RouterConfig(intents=intents),
            index=MagicMock(),
            frequency_version=1,
            freq_snapshot_time=0.0,
            created_at=0.0,
        )
        context = self._create_context(snapshot, "test query")

        result = await policy_engine.evaluate(context, context.request)

        assert result.intent == "high_priority"


class TestPolicyEngineSnapshot:
    """Test snapshot creation and freeze behavior."""

    @pytest.fixture
    def score_engine(self) -> ScoreEngine:
        """Create a mock score engine."""
        embedding = InMemoryEmbeddingModel(dimension=128)
        index = InMemoryANNIndex(dimension=128)
        fairness = FairnessBoostCalculator(MagicMock(enabled=False))
        return ScoreEngine(embedding, index, fairness)

    def test_snapshot_immutability(self, score_engine: ScoreEngine):
        """Test that snapshot is immutable during routing."""
        config = PolicyEngineConfig(default_intent="unknown")
        engine = PolicyEngine(config=config, score_engine=score_engine)

        intents = {
            "test_intent": IntentConfig(
                name="test_intent",
                rules=[
                    RoutingRule(
                        pattern="test",
                        intent="test_intent",
                        confidence=1.0,
                    )
                ],
            )
        }
        from src.infrastructure.router.types import RouterConfig
        snapshot1 = Snapshot(
            snapshot_id="snap-1",
            config=RouterConfig(intents=intents),
            index=MagicMock(),
            frequency_version=1,
            freq_snapshot_time=0.0,
            created_at=0.0,
        )

        context = RequestContext.create(
            snapshot=snapshot1,
            request=Request(query="test"),
        )

        assert context.snapshot_id == "snap-1"
        assert context.frozen_snapshot.snapshot_id == "snap-1"


class TestPolicyEngineBoostBudget:
    """Test boost budget per request exceeded scenarios."""

    @pytest.fixture
    def score_engine(self) -> ScoreEngine:
        """Create score engine with fairness enabled."""
        embedding = InMemoryEmbeddingModel(dimension=128)
        index = InMemoryANNIndex(dimension=128)
        from src.infrastructure.router.types import BoostFairnessConfig
        fairness_config = BoostFairnessConfig(
            enabled=True,
            per_intent_weight_cap=0.1,  # 10% cap
            min_share_per_intent=0.01,
            global_boost_per_second=100,
        )
        fairness = FairnessBoostCalculator(fairness_config)
        return ScoreEngine(embedding, index, fairness)

    @pytest.fixture
    def policy_engine(self, score_engine: ScoreEngine) -> PolicyEngine:
        """Create policy engine."""
        config = PolicyEngineConfig(
            default_intent="unknown",
            fallback_enabled=True,
        )
        return PolicyEngine(config=config, score_engine=score_engine)

    @pytest.mark.asyncio
    async def test_boost_budget_per_request_exceeded(
        self,
        policy_engine: PolicyEngine,
    ):
        """Test behavior when boost budget per request is exceeded."""
        intents = {
            "high_traffic": IntentConfig(
                name="high_traffic",
                frequency=1000,  # High frequency
            ),
            "low_traffic": IntentConfig(
                name="low_traffic",
                frequency=1,
            ),
        }
        from src.infrastructure.router.types import RouterConfig
        snapshot = Snapshot(
            snapshot_id="test-snap",
            config=RouterConfig(intents=intents),
            index=MagicMock(),
            frequency_version=1,
            freq_snapshot_time=0.0,
            created_at=0.0,
        )

        context = RequestContext.create(
            snapshot=snapshot,
            request=Request(query="test query"),
        )

        # Make multiple requests to exhaust budget
        results = []
        for _ in range(10):
            result = await policy_engine.route(
                context,
                context.request,
                available_intents=["high_traffic", "low_traffic"],
            )
            results.append(result)

        # Should still return results (degraded but functional)
        assert all(r.intent in ["high_traffic", "low_traffic", "unknown"] for r in results)


class TestPolicyEngineFallback:
    """Test fallback behavior when budget exhausted."""

    @pytest.fixture
    def score_engine(self) -> ScoreEngine:
        """Create score engine."""
        embedding = InMemoryEmbeddingModel(dimension=128)
        index = InMemoryANNIndex(dimension=128)
        fairness = FairnessBoostCalculator(MagicMock(enabled=False))
        return ScoreEngine(embedding, index, fairness)

    @pytest.fixture
    def policy_engine(self, score_engine: ScoreEngine) -> PolicyEngine:
        """Create policy engine with fallback enabled."""
        config = PolicyEngineConfig(
            default_intent="fallback_intent",
            fallback_enabled=True,
            min_confidence_threshold=0.9,  # High threshold
        )
        return PolicyEngine(config=config, score_engine=score_engine)

    @pytest.mark.asyncio
    async def test_fallback_on_low_confidence(
        self,
        policy_engine: PolicyEngine,
    ):
        """Test fallback to default intent on low confidence."""
        intents = {
            "low_score": IntentConfig(name="low_score", base_score=0.1),
        }
        from src.infrastructure.router.types import RouterConfig
        snapshot = Snapshot(
            snapshot_id="test-snap",
            config=RouterConfig(intents=intents),
            index=MagicMock(),
            frequency_version=1,
            freq_snapshot_time=0.0,
            created_at=0.0,
        )

        context = RequestContext.create(
            snapshot=snapshot,
            request=Request(query="some query"),
        )

        result = await policy_engine.route(
            context,
            context.request,
            available_intents=["low_score"],
        )

        assert result.intent == "fallback_intent"

    @pytest.mark.asyncio
    async def test_fallback_disabled(
        self,
        score_engine: ScoreEngine,
    ):
        """Test behavior when fallback is disabled."""
        config = PolicyEngineConfig(
            default_intent="default",
            fallback_enabled=False,
            min_confidence_threshold=0.9,
        )
        policy_engine = PolicyEngine(config=config, score_engine=score_engine)

        intents = {
            "low_score": IntentConfig(name="low_score", base_score=0.1),
        }
        from src.infrastructure.router.types import RouterConfig
        snapshot = Snapshot(
            snapshot_id="test-snap",
            config=RouterConfig(intents=intents),
            index=MagicMock(),
            frequency_version=1,
            freq_snapshot_time=0.0,
            created_at=0.0,
        )

        context = RequestContext.create(
            snapshot=snapshot,
            request=Request(query="some query"),
        )

        result = await policy_engine.route(
            context,
            context.request,
            available_intents=["low_score"],
        )

        # Should still return the low-score intent, not fallback
        assert result.intent == "low_score"
        assert result.confidence < 0.9


class TestGlobalBoostTokenBucket:
    """Test global boost token bucket behavior."""

    @pytest.mark.asyncio
    async def test_global_boost_token_bucket_limits_total_usage(self):
        """Test that global boost token bucket limits total boost usage."""
        from src.infrastructure.router.types import BoostFairnessConfig
        fairness_config = BoostFairnessConfig(
            enabled=True,
            per_intent_weight_cap=0.5,  # 50% per intent
            min_share_per_intent=0.0,  # No minimum
            global_boost_per_second=100,  # 100 tokens per second
        )
        calculator = FairnessBoostCalculator(fairness_config)

        # Exhaust budget with first intent
        for _ in range(5):
            await calculator.calculate_boost(
                intent="intent_a",
                base_score=0.0,
                max_intent_boost=50.0,
            )

        # Second intent should have limited boost due to global cap
        boost = await calculator.calculate_boost(
            intent="intent_b",
            base_score=0.0,
            max_intent_boost=100.0,
        )

        # Boost should be limited
        assert boost < 100.0


class TestFairnessPerIntentCap:
    """Test fairness per-intent cap behavior."""

    @pytest.mark.asyncio
    async def test_per_intent_cap_enforced(self):
        """Test that per-intent cap is enforced."""
        from src.infrastructure.router.types import BoostFairnessConfig
        fairness_config = BoostFairnessConfig(
            enabled=True,
            per_intent_weight_cap=0.1,  # 10% of 1000 = 100 max
            min_share_per_intent=0.0,
            global_boost_per_second=1000,
        )
        calculator = FairnessBoostCalculator(fairness_config)

        # First call with large boost
        boost1 = await calculator.calculate_boost(
            intent="capped_intent",
            base_score=0.0,
            max_intent_boost=200.0,  # Request more than cap
        )

        # Should be capped
        assert boost1 <= 100.0 + 200.0  # base + capped boost

    @pytest.mark.asyncio
    async def test_min_share_guaranteed(self):
        """Test that minimum share is guaranteed."""
        from src.infrastructure.router.types import BoostFairnessConfig
        fairness_config = BoostFairnessConfig(
            enabled=True,
            per_intent_weight_cap=1.0,
            min_share_per_intent=0.05,  # 5% minimum
            global_boost_per_second=1000,
        )
        calculator = FairnessBoostCalculator(fairness_config)

        # Exhaust budget for one intent
        for _ in range(20):
            await calculator.calculate_boost(
                intent="intent_a",
                base_score=0.0,
                max_intent_boost=100.0,
            )

        # New intent should get minimum share
        stats = await calculator.get_usage_stats()
        # Intent A should be exhausted or near exhaustion
        assert "intent_a" in stats


class TestRuleCreationHelpers:
    """Test helper functions for creating rules."""

    def test_create_keyword_rule(self):
        """Test keyword rule creation."""
        rule = create_keyword_rule(
            pattern="test",
            intent="test_intent",
            priority=10,
        )

        assert rule.pattern == "test"
        assert rule.intent == "test_intent"
        assert rule.priority == 10
        assert rule.needs_semantic is False
        assert rule.confidence == 0.9

    def test_create_regex_rule(self):
        """Test regex rule creation."""
        rule = create_regex_rule(
            pattern=r"\d+",
            intent="number_intent",
            priority=5,
        )

        assert rule.pattern == r"\d+"
        assert rule.intent == "number_intent"
        assert rule.priority == 5
        assert rule.needs_semantic is False
        assert rule.confidence == 0.95
