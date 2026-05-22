"""Cost Governance - token budget, adaptive routing, model tiering, embedding budget.

This module provides cost governance for AI operations:
- Token budget management (per-session, per-user limits)
- Adaptive routing (route to cheapest model meeting quality threshold)
- Inference policy (cache strategy, model tiering)
- Embedding budget (RAG cost control, rerank budget)
- Cost observability (metrics: cost_per_session, model_tier_usage, cache_hit_rate)
"""

from .token_budget import TokenBudget, BudgetConfig, BudgetResult
from .adaptive_routing import AdaptiveRouter, RoutingPolicy, ModelTier
from .inference_policy import InferencePolicy, CacheStrategy, TierConfig
from .embedding_budget import EmbeddingBudget, EmbeddingCostConfig
from .cost_observability import CostObserver, CostMetrics

__all__ = [
    "TokenBudget",
    "BudgetConfig",
    "BudgetResult",
    "AdaptiveRouter",
    "RoutingPolicy",
    "ModelTier",
    "InferencePolicy",
    "CacheStrategy",
    "TierConfig",
    "EmbeddingBudget",
    "EmbeddingCostConfig",
    "CostObserver",
    "CostMetrics",
]
