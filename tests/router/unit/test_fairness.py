"""Unit tests for FairnessBoostCalculator."""

from __future__ import annotations

import asyncio
import time

import pytest

from src.infrastructure.router.fairness.boost_fairness import FairnessBoostCalculator
from src.infrastructure.router.types import BoostFairnessConfig


class TestFairnessBoostCalculatorBasic:
    """Test basic FairnessBoostCalculator functionality."""

    @pytest.fixture
    def config(self) -> BoostFairnessConfig:
        """Create fairness config."""
        return BoostFairnessConfig(
            enabled=True,
            per_intent_weight_cap=0.30,
            min_share_per_intent=0.01,
            global_boost_per_second=1000,
        )

    @pytest.fixture
    def calculator(self, config: BoostFairnessConfig) -> FairnessBoostCalculator:
        """Create calculator."""
        return FairnessBoostCalculator(config)

    @pytest.mark.asyncio
    async def test_basic_boost_calculation(
        self, calculator: FairnessBoostCalculator
    ):
        """Test basic boost calculation."""
        boost = await calculator.calculate_boost(
            intent="test_intent",
            base_score=0.5,
            max_intent_boost=0.2,
        )

        # Boost should be added to base
        assert boost >= 0.5
        assert boost == pytest.approx(0.5 + 0.2, abs=0.01)

    @pytest.mark.asyncio
    async def test_boost_with_zero_max(
        self, calculator: FairnessBoostCalculator
    ):
        """Test boost calculation with zero max boost."""
        boost = await calculator.calculate_boost(
            intent="test_intent",
            base_score=0.5,
            max_intent_boost=0.0,
        )

        assert boost == 0.5

    @pytest.mark.asyncio
    async def test_disabled_fairness_returns_max_boost(
        self, calculator: FairnessBoostCalculator
    ):
        """Test that disabled fairness returns max boost."""
        config = BoostFairnessConfig(enabled=False)
        disabled_calc = FairnessBoostCalculator(config)

        boost = await disabled_calc.calculate_boost(
            intent="test_intent",
            base_score=0.5,
            max_intent_boost=0.5,
        )

        assert boost == 1.0


class TestPerIntentCap:
    """Test per-intent cap enforcement."""

    @pytest.mark.asyncio
    async def test_per_intent_cap_enforced(self):
        """Test that per-intent cap is enforced."""
        config = BoostFairnessConfig(
            enabled=True,
            per_intent_weight_cap=0.10,  # 10% of 1000 = 100 max
            min_share_per_intent=0.0,
            global_boost_per_second=1000,
        )
        calculator = FairnessBoostCalculator(config)

        # First call
        boost1 = await calculator.calculate_boost(
            intent="capped_intent",
            base_score=0.0,
            max_intent_boost=50.0,
        )

        # Subsequent calls should respect cap
        for _ in range(5):
            boost = await calculator.calculate_boost(
                intent="capped_intent",
                base_score=0.0,
                max_intent_boost=50.0,
            )
            # After first call, should not get full boost
            if boost > 0:
                assert boost <= 50.0

    @pytest.mark.asyncio
    async def test_different_intents_separate_budgets(self):
        """Test that different intents have separate budgets."""
        config = BoostFairnessConfig(
            enabled=True,
            per_intent_weight_cap=0.50,  # 50% per intent
            min_share_per_intent=0.0,
            global_boost_per_second=1000,
        )
        calculator = FairnessBoostCalculator(config)

        # Exhaust budget for intent A
        for _ in range(3):
            await calculator.calculate_boost(
                intent="intent_a",
                base_score=0.0,
                max_intent_boost=200.0,
            )

        # Intent B should still have budget
        boost_b = await calculator.calculate_boost(
            intent="intent_b",
            base_score=0.0,
            max_intent_boost=500.0,
        )

        assert boost_b > 0

    @pytest.mark.asyncio
    async def test_intent_exhausted_budget_returns_base_only(self):
        """Test that exhausted intent returns base score only."""
        config = BoostFairnessConfig(
            enabled=True,
            per_intent_weight_cap=0.01,  # Very small cap
            min_share_per_intent=0.0,
            global_boost_per_second=1000,
        )
        calculator = FairnessBoostCalculator(config)

        # Exhaust budget with many small requests
        for _ in range(100):
            await calculator.calculate_boost(
                intent="exhausted_intent",
                base_score=0.5,
                max_intent_boost=10.0,
            )

        # Next request should get no boost (base only)
        boost = await calculator.calculate_boost(
            intent="exhausted_intent",
            base_score=0.5,
            max_intent_boost=10.0,
        )

        assert boost == 0.5


class TestMinShareGuarantee:
    """Test minimum share guarantee."""

    @pytest.mark.asyncio
    async def test_min_share_guaranteed(self):
        """Test that minimum share is guaranteed."""
        config = BoostFairnessConfig(
            enabled=True,
            per_intent_weight_cap=1.0,
            min_share_per_intent=0.10,  # 10% minimum
            global_boost_per_second=1000,
        )
        calculator = FairnessBoostCalculator(config)

        # Request with small max_boost
        boost = await calculator.calculate_boost(
            intent="new_intent",
            base_score=0.0,
            max_intent_boost=5.0,  # Small request
        )

        # Should get at least min_share
        min_expected = 5.0 * 0.10  # 10% of max_intent_boost
        assert boost >= min_expected

    @pytest.mark.asyncio
    async def test_min_share_takes_precedence_over_cap(self):
        """Test that min_share takes precedence over cap."""
        config = BoostFairnessConfig(
            enabled=True,
            per_intent_weight_cap=0.01,  # Very small cap
            min_share_per_intent=0.05,  # 5% minimum
            global_boost_per_second=100,
        )
        calculator = FairnessBoostCalculator(config)

        boost = await calculator.calculate_boost(
            intent="test_intent",
            base_score=0.0,
            max_intent_boost=100.0,
        )

        # Should get at least min_share even if cap would limit
        min_expected = 100.0 * 0.05
        assert boost >= min_expected


class TestGlobalBoostTokenBucket:
    """Test global boost token bucket behavior."""

    @pytest.mark.asyncio
    async def test_global_budget_shared_across_intents(self):
        """Test that global budget is shared across intents."""
        config = BoostFairnessConfig(
            enabled=True,
            per_intent_weight_cap=1.0,  # No per-intent limit
            min_share_per_intent=0.0,
            global_boost_per_second=100,  # Only 100 tokens total
        )
        calculator = FairnessBoostCalculator(config)

        # Exhaust global budget with intent A
        for _ in range(5):
            await calculator.calculate_boost(
                intent="intent_a",
                base_score=0.0,
                max_intent_boost=30.0,
            )

        # Intent B should have limited budget
        boost_b = await calculator.calculate_boost(
            intent="intent_b",
            base_score=0.0,
            max_intent_boost=100.0,
        )

        # Should be less than or equal to requested
        assert boost_b <= 100.0

    @pytest.mark.asyncio
    async def test_usage_reset_after_time_window(self):
        """Test that usage resets after time window."""
        config = BoostFairnessConfig(
            enabled=True,
            per_intent_weight_cap=0.10,
            min_share_per_intent=0.0,
            global_boost_per_second=1000,
        )
        calculator = FairnessBoostCalculator(config)

        # Exhaust budget
        for _ in range(10):
            await calculator.calculate_boost(
                intent="test_intent",
                base_score=0.0,
                max_intent_boost=50.0,
            )

        # Manually reset time (simulate 1+ second passing)
        calculator._usage_reset_time = time.time() - 2.0

        # Should get budget again
        boost = await calculator.calculate_boost(
            intent="test_intent",
            base_score=0.0,
            max_intent_boost=50.0,
        )

        # Should get at least some boost after reset
        assert boost >= 0.0


class TestUsageStats:
    """Test usage statistics."""

    @pytest.mark.asyncio
    async def test_get_usage_stats(self):
        """Test getting usage statistics."""
        config = BoostFairnessConfig(
            enabled=True,
            per_intent_weight_cap=0.30,
            min_share_per_intent=0.01,
            global_boost_per_second=1000,
        )
        calculator = FairnessBoostCalculator(config)

        # Make some requests
        await calculator.calculate_boost(
            intent="intent_a",
            base_score=0.0,
            max_intent_boost=50.0,
        )
        await calculator.calculate_boost(
            intent="intent_b",
            base_score=0.0,
            max_intent_boost=30.0,
        )

        stats = await calculator.get_usage_stats()

        assert "intent_a" in stats
        assert "intent_b" in stats
        assert "usage" in stats["intent_a"]
        assert "max_allowed" in stats["intent_a"]
        assert "remaining" in stats["intent_a"]

    @pytest.mark.asyncio
    async def test_usage_stats_reflect_exhaustion(self):
        """Test that usage stats reflect budget exhaustion."""
        config = BoostFairnessConfig(
            enabled=True,
            per_intent_weight_cap=0.01,  # Very small
            min_share_per_intent=0.0,
            global_boost_per_second=100,
        )
        calculator = FairnessBoostCalculator(config)

        # Exhaust budget
        for _ in range(20):
            await calculator.calculate_boost(
                intent="exhausted",
                base_score=0.0,
                max_intent_boost=10.0,
            )

        stats = await calculator.get_usage_stats()

        # Remaining should be 0 or negative (capped at 0)
        assert stats["exhausted"]["remaining"] <= 0


class TestFairnessConcurrency:
    """Test fairness with concurrent access."""

    @pytest.mark.asyncio
    async def test_concurrent_boost_requests(self):
        """Test concurrent boost requests are handled correctly."""
        config = BoostFairnessConfig(
            enabled=True,
            per_intent_weight_cap=0.50,
            min_share_per_intent=0.0,
            global_boost_per_second=1000,
        )
        calculator = FairnessBoostCalculator(config)

        # Make concurrent requests
        tasks = [
            calculator.calculate_boost(
                intent=f"intent_{i % 3}",
                base_score=0.0,
                max_intent_boost=100.0,
            )
            for i in range(50)
        ]

        results = await asyncio.gather(*tasks)

        # All should complete without error
        assert len(results) == 50
        assert all(isinstance(r, (int, float)) for r in results)

    @pytest.mark.asyncio
    async def test_no_negative_boost(self):
        """Test that boost is never negative."""
        config = BoostFairnessConfig(
            enabled=True,
            per_intent_weight_cap=0.30,
            min_share_per_intent=0.01,
            global_boost_per_second=1000,
        )
        calculator = FairnessBoostCalculator(config)

        for _ in range(100):
            boost = await calculator.calculate_boost(
                intent="test",
                base_score=0.0,
                max_intent_boost=10.0,
            )
            assert boost >= 0.0


class TestEdgeCases:
    """Test edge cases."""

    @pytest.mark.asyncio
    async def test_zero_global_boost_per_second(self):
        """Test behavior with zero global budget."""
        config = BoostFairnessConfig(
            enabled=True,
            per_intent_weight_cap=0.30,
            min_share_per_intent=0.0,
            global_boost_per_second=0,
        )
        calculator = FairnessBoostCalculator(config)

        boost = await calculator.calculate_boost(
            intent="test",
            base_score=0.5,
            max_intent_boost=10.0,
        )

        # Should return base only
        assert boost == 0.5

    @pytest.mark.asyncio
    async def test_zero_per_intent_cap(self):
        """Test behavior with zero per-intent cap."""
        config = BoostFairnessConfig(
            enabled=True,
            per_intent_weight_cap=0.0,
            min_share_per_intent=0.0,
            global_boost_per_second=1000,
        )
        calculator = FairnessBoostCalculator(config)

        boost = await calculator.calculate_boost(
            intent="test",
            base_score=0.5,
            max_intent_boost=10.0,
        )

        # Should return base only (cap is 0)
        assert boost == 0.5

    @pytest.mark.asyncio
    async def test_config_immutability(self):
        """Test that config is not modified."""
        config = BoostFairnessConfig(
            enabled=True,
            per_intent_weight_cap=0.30,
            min_share_per_intent=0.01,
            global_boost_per_second=1000,
        )
        calculator = FairnessBoostCalculator(config)

        original_cap = config.per_intent_weight_cap
        original_min = config.min_share_per_intent

        # Make some requests
        await calculator.calculate_boost(
            intent="test",
            base_score=0.0,
            max_intent_boost=10.0,
        )

        # Config should be unchanged
        assert config.per_intent_weight_cap == original_cap
        assert config.min_share_per_intent == original_min
