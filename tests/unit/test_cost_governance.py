"""Unit tests for Cost Governance module - Phase 5.7."""

import pytest

from core.cost_governance import (
    TokenBudget,
    BudgetConfig,
    BudgetResult,
    AdaptiveRouter,
    RoutingPolicy,
    ModelTier,
    ModelInfo,
    InferencePolicy,
    CacheStrategy,
    TierConfig,
    InferencePolicyManager,
    EmbeddingBudget,
    EmbeddingCostConfig,
    CostObserver,
    CostMetrics,
)


class TestTokenBudget:
    """Tests for TokenBudget."""

    @pytest.mark.asyncio
    async def test_initial_state(self):
        """Test budget starts empty."""
        budget = TokenBudget()
        used, limit = await budget.get_session_usage("session1")
        assert used == 0
        assert limit == 100000

    @pytest.mark.asyncio
    async def test_consume_tokens(self):
        """Test consuming tokens."""
        budget = TokenBudget()
        result = await budget.check_and_consume("session1", 1000)
        assert result.allowed is True
        assert result.remaining_tokens == 99000

    @pytest.mark.asyncio
    async def test_budget_exceeded(self):
        """Test budget exceeded."""
        budget = TokenBudget(BudgetConfig(max_tokens=5000))
        result = await budget.check_and_consume("session1", 6000)
        assert result.allowed is False

    @pytest.mark.asyncio
    async def test_warning_threshold(self):
        """Test warning threshold."""
        budget = TokenBudget(BudgetConfig(max_tokens=10000, warning_threshold=0.8))
        result = await budget.check_and_consume("session1", 8500)
        assert result.allowed is True
        assert result.usage_percent >= 0.8

    @pytest.mark.asyncio
    async def test_user_aggregation(self):
        """Test user token aggregation."""
        budget = TokenBudget()
        await budget.check_and_consume("session1", 1000, user_id="user1")
        await budget.check_and_consume("session2", 2000, user_id="user1")
        user_usage = await budget.get_user_usage("user1")
        assert user_usage == 3000

    @pytest.mark.asyncio
    async def test_check_without_consume(self):
        """Test check without consuming."""
        budget = TokenBudget(BudgetConfig(max_tokens=10000))
        await budget.check_and_consume("session1", 9500)
        result = await budget.check("session1", 1000)
        assert result.allowed is False

    @pytest.mark.asyncio
    async def test_reset_session(self):
        """Test resetting session."""
        budget = TokenBudget()
        await budget.check_and_consume("session1", 5000)
        await budget.reset_session("session1")
        used, _ = await budget.get_session_usage("session1")
        assert used == 0

    @pytest.mark.asyncio
    async def test_stats(self):
        """Test getting statistics."""
        budget = TokenBudget()
        await budget.check_and_consume("session1", 1000)
        stats = await budget.get_stats()
        assert stats["sessions"] == 1
        assert stats["total_session_usage"] == 1000


class TestAdaptiveRouter:
    """Tests for AdaptiveRouter."""

    def test_register_model(self):
        """Test registering a model."""
        router = AdaptiveRouter()
        model = ModelInfo(
            name="gpt-4",
            tier=ModelTier.ACCURATE,
            cost_per_token=0.03,
            quality_score=0.95,
            latency_ms=1000,
            max_tokens=8000,
        )
        router.register_model(model)
        assert router.get_model("gpt-4") is not None

    def test_get_models_by_tier(self):
        """Test filtering by tier."""
        router = AdaptiveRouter()
        router.register_model(ModelInfo("fast", ModelTier.FAST, 0.001, 0.7, 50, 4000))
        router.register_model(ModelInfo("accurate", ModelTier.ACCURATE, 0.03, 0.95, 1000, 32000))
        models = router.get_models_by_tier(ModelTier.FAST)
        assert len(models) == 1
        assert models[0].name == "fast"

    @pytest.mark.asyncio
    async def test_route_cheapest(self):
        """Test cheapest routing."""
        router = AdaptiveRouter(policy=RoutingPolicy.CHEAPEST)
        router.register_model(ModelInfo("cheap", ModelTier.FAST, 0.001, 0.7, 50, 4000))
        router.register_model(ModelInfo("expensive", ModelTier.ACCURATE, 0.03, 0.95, 1000, 32000))

        decision = await router.route()
        assert decision.model_name == "cheap"

    @pytest.mark.asyncio
    async def test_route_quality_first(self):
        """Test quality-first routing."""
        router = AdaptiveRouter(policy=RoutingPolicy.QUALITY_FIRST)
        router.register_model(ModelInfo("fast", ModelTier.FAST, 0.001, 0.7, 50, 4000))
        router.register_model(ModelInfo("smart", ModelTier.ACCURATE, 0.03, 0.95, 1000, 32000))

        decision = await router.route()
        assert decision.model_name == "smart"

    @pytest.mark.asyncio
    async def test_route_with_min_quality(self):
        """Test routing with minimum quality."""
        router = AdaptiveRouter()
        router.register_model(ModelInfo("low", ModelTier.FAST, 0.001, 0.6, 50, 4000))
        router.register_model(ModelInfo("high", ModelTier.ACCURATE, 0.03, 0.95, 1000, 32000))

        decision = await router.route(min_quality=0.8)
        assert decision.model_name == "high"

    @pytest.mark.asyncio
    async def test_route_no_match(self):
        """Test routing when no model matches."""
        router = AdaptiveRouter()
        router.register_model(ModelInfo("low", ModelTier.FAST, 0.001, 0.6, 50, 4000))

        decision = await router.route(min_quality=0.99)
        assert decision.model_name == ""

    def test_stats(self):
        """Test getting statistics."""
        router = AdaptiveRouter()
        router.register_model(ModelInfo("model1", ModelTier.FAST, 0.001, 0.7, 50, 4000))
        stats = router.get_stats()
        assert stats["models_registered"] == 1


class TestInferencePolicy:
    """Tests for InferencePolicy."""

    @pytest.mark.asyncio
    async def test_get_default_policy(self):
        """Test getting default policy."""
        manager = InferencePolicyManager()
        policy = await manager.get_policy()
        assert policy.default_tier == "balanced"

    @pytest.mark.asyncio
    async def test_register_policy(self):
        """Test registering a named policy."""
        manager = InferencePolicyManager()
        policy = InferencePolicy(default_tier="fast", cache_strategy=CacheStrategy.TTL)
        await manager.register_policy("fast_policy", policy)
        retrieved = await manager.get_policy("fast_policy")
        assert retrieved.default_tier == "fast"

    @pytest.mark.asyncio
    async def test_get_cache_strategy(self):
        """Test getting cache strategy."""
        manager = InferencePolicyManager(InferencePolicy(cache_strategy=CacheStrategy.SEMANTIC))
        strategy = await manager.get_cache_strategy()
        assert strategy == CacheStrategy.SEMANTIC

    def test_tier_config(self):
        """Test tier configuration."""
        policy = InferencePolicy()
        tier_config = policy.get_tier_config("fast")
        assert tier_config.tier_name == "fast"


class TestEmbeddingBudget:
    """Tests for EmbeddingBudget."""

    @pytest.mark.asyncio
    async def test_record_embedding(self):
        """Test recording embedding usage."""
        budget = EmbeddingBudget()
        allowed, cost = await budget.check_and_record(1000)
        assert allowed is True
        assert cost > 0

    @pytest.mark.asyncio
    async def test_daily_limit(self):
        """Test daily token limit."""
        budget = EmbeddingBudget(max_daily_tokens=5000)
        await budget.check_and_record(3000)
        allowed, _ = await budget.check_and_record(3000)
        assert allowed is False

    @pytest.mark.asyncio
    async def test_rerank_cost(self):
        """Test rerank cost calculation."""
        budget = EmbeddingBudget()
        allowed, cost = await budget.check_and_record(100, is_rerank=True)
        assert allowed is True
        assert cost > 0

    @pytest.mark.asyncio
    async def test_batch_size_check(self):
        """Test batch size validation."""
        budget = EmbeddingBudget()
        allowed, _ = await budget.check_batch(50)
        assert allowed is True

        allowed, _ = await budget.check_batch(200)
        assert allowed is False

    @pytest.mark.asyncio
    async def test_estimate_cost(self):
        """Test cost estimation."""
        budget = EmbeddingBudget()
        cost = await budget.estimate_cost(1000)
        assert cost > 0

    @pytest.mark.asyncio
    async def test_stats(self):
        """Test getting statistics."""
        budget = EmbeddingBudget()
        await budget.check_and_record(1000)
        stats = await budget.get_stats()
        assert stats["usage"]["embedding_calls"] == 1


class TestCostObserver:
    """Tests for CostObserver."""

    @pytest.mark.asyncio
    async def test_record_cost(self):
        """Test recording cost."""
        observer = CostObserver()
        await observer.record_cost("session1", 0.05, 1000)
        metrics = await observer.get_metrics()
        assert metrics.total_cost == 0.05
        assert metrics.total_tokens == 1000

    @pytest.mark.asyncio
    async def test_record_cache_hit(self):
        """Test recording cache hit."""
        observer = CostObserver()
        await observer.record_cache_hit()
        await observer.record_cache_hit()
        await observer.record_cache_miss()
        metrics = await observer.get_metrics()
        assert metrics.cache_hit_rate == pytest.approx(2/3, rel=0.01)

    @pytest.mark.asyncio
    async def test_session_cost(self):
        """Test getting session cost."""
        observer = CostObserver()
        await observer.record_cost("session1", 0.05, 1000)
        await observer.record_cost("session1", 0.03, 500)
        cost = await observer.get_session_cost("session1")
        assert cost == 0.08

    @pytest.mark.asyncio
    async def test_model_usage(self):
        """Test tracking model usage."""
        observer = CostObserver()
        await observer.record_cost("session1", 0.05, 1000, model_name="gpt-4")
        await observer.record_cost("session2", 0.03, 500, model_name="gpt-4")
        usage = await observer.get_model_usage()
        assert usage["gpt-4"] == 2

    @pytest.mark.asyncio
    async def test_top_sessions(self):
        """Test getting top sessions."""
        observer = CostObserver()
        await observer.record_cost("session1", 0.05, 1000)
        await observer.record_cost("session2", 0.10, 2000)
        await observer.record_cost("session3", 0.03, 500)
        top = await observer.get_top_sessions(2)
        assert top[0][0] == "session2"
        assert top[1][0] == "session1"

    @pytest.mark.asyncio
    async def test_reset(self):
        """Test resetting metrics."""
        observer = CostObserver()
        await observer.record_cost("session1", 0.05, 1000)
        await observer.reset()
        metrics = await observer.get_metrics()
        assert metrics.total_cost == 0.0

    @pytest.mark.asyncio
    async def test_stats(self):
        """Test getting statistics."""
        observer = CostObserver()
        await observer.record_cost("session1", 0.05, 1000)
        stats = await observer.get_stats()
        assert stats["total_cost"] == 0.05
        assert stats["total_requests"] == 1
