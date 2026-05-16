"""
Token Accounting Tracker

Provides comprehensive token usage tracking and accounting for LLM API calls.
This module monitors token consumption, calculates costs, and provides
budget management for AI_support agent operations.

Features:
- Per-request token counting
- Cost calculation and budgeting
- Usage analytics and reporting
- Token budget enforcement
- Provider-specific pricing

Usage:
    from src.infrastructure.metrics.token_tracker import TokenTracker, TokenBudget

    tracker = TokenTracker()

    # Track a request
    tracker.track_request(
        provider="openai",
        model="gpt-4",
        prompt_tokens=100,
        completion_tokens=50,
    )

    # Check budget
    if tracker.is_over_budget():
        print("Budget exceeded!")
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class TokenUnit(Enum):
    """Token counting units."""
    TOKENS = "tokens"
    CHARACTERS = "characters"
    WORDS = "words"


@dataclass
class TokenUsage:
    """Token usage record for a single request."""
    timestamp: datetime
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    latency_ms: float
    request_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TokenBudget:
    """Token budget configuration."""
    name: str
    max_tokens: int
    max_cost_usd: float
    period_hours: float = 24.0
    alert_threshold: float = 0.8  # Alert at 80% usage


@dataclass
class TokenReport:
    """Token usage report."""
    timestamp: datetime
    period_start: datetime
    period_end: datetime
    total_requests: int
    total_prompt_tokens: int
    total_completion_tokens: int
    total_tokens: int
    total_cost_usd: float
    avg_tokens_per_request: float
    avg_cost_per_request: float
    avg_latency_ms: float
    by_provider: Dict[str, Dict[str, int]]
    by_model: Dict[str, Dict[str, int]]
    budget_status: Dict[str, Any] = field(default_factory=dict)


class PricingModel:
    """Pricing model for different LLM providers."""

    # Default pricing (per 1M tokens)
    DEFAULT_PRICING = {
        "openai": {
            "gpt-4": {"prompt": 30.0, "completion": 60.0},
            "gpt-4-turbo": {"prompt": 10.0, "completion": 30.0},
            "gpt-3.5-turbo": {"prompt": 0.5, "completion": 1.5},
        },
        "anthropic": {
            "claude-3-opus": {"prompt": 15.0, "completion": 75.0},
            "claude-3-sonnet": {"prompt": 3.0, "completion": 15.0},
            "claude-3-haiku": {"prompt": 0.25, "completion": 1.25},
        },
        "google": {
            "gemini-pro": {"prompt": 1.25, "completion": 5.0},
            "gemini-ultra": {"prompt": 7.0, "completion": 21.0},
        },
    }

    @classmethod
    def get_cost(
        cls,
        provider: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> float:
        """Calculate cost for a request."""
        pricing = cls.DEFAULT_PRICING.get(provider, {}).get(model, {})

        if not pricing:
            # Default to GPT-3.5 pricing if unknown
            pricing = {"prompt": 0.5, "completion": 1.5}
            logger.warning(f"Unknown provider/model: {provider}/{model}, using default pricing")

        prompt_cost = (prompt_tokens / 1_000_000) * pricing["prompt"]
        completion_cost = (completion_tokens / 1_000_000) * pricing["completion"]

        return round(prompt_cost + completion_cost, 6)

    @classmethod
    def set_pricing(
        cls,
        provider: str,
        model: str,
        prompt_price_per_million: float,
        completion_price_per_million: float,
    ) -> None:
        """Set custom pricing for a provider/model."""
        if provider not in cls.DEFAULT_PRICING:
            cls.DEFAULT_PRICING[provider] = {}
        cls.DEFAULT_PRICING[provider][model] = {
            "prompt": prompt_price_per_million,
            "completion": completion_price_per_million,
        }


class TokenTracker:
    """
    Token usage tracker for src.

    Tracks token usage across all LLM providers and provides:
    - Real-time usage monitoring
    - Cost calculation and budgeting
    - Usage analytics and reporting
    - Budget alerts and enforcement

    Usage:
        tracker = TokenTracker()

        # Track usage
        tracker.track_request(
            provider="openai",
            model="gpt-4",
            prompt_tokens=100,
            completion_tokens=50,
        )

        # Get report
        report = tracker.get_report()
        print(f"Total cost: ${report.total_cost_usd:.4f}")
    """

    def __init__(
        self,
        budgets: Optional[List[TokenBudget]] = None,
        enable_cost_calculation: bool = True,
        max_history: int = 10000,
    ):
        """
        Initialize token tracker.

        Args:
            budgets: Optional list of budgets to enforce
            enable_cost_calculation: Whether to calculate costs
            max_history: Maximum history records to keep
        """
        self.budgets = {b.name: b for b in budgets} if budgets else {}
        self.enable_cost_calculation = enable_cost_calculation
        self.max_history = max_history

        self._usage_history: List[TokenUsage] = []
        self._lock = asyncio.Lock()

        # Real-time counters
        self._total_prompt_tokens = 0
        self._total_completion_tokens = 0
        self._total_cost_usd = 0.0
        self._total_requests = 0

        # Alert callbacks
        self._alert_callbacks: List[Callable[[str, Any], None]] = []

    def track_request(
        self,
        provider: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        latency_ms: float = 0.0,
        request_id: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TokenUsage:
        """
        Track a token usage request.

        Args:
            provider: LLM provider (openai, anthropic, etc.)
            model: Model name
            prompt_tokens: Number of prompt tokens
            completion_tokens: Number of completion tokens
            latency_ms: Request latency in milliseconds
            request_id: Optional request identifier
            metadata: Optional metadata

        Returns:
            TokenUsage record
        """
        total_tokens = prompt_tokens + completion_tokens

        # Calculate cost if enabled
        cost = 0.0
        if self.enable_cost_calculation:
            cost = PricingModel.get_cost(provider, model, prompt_tokens, completion_tokens)

        usage = TokenUsage(
            timestamp=datetime.now(),
            provider=provider,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost_usd=cost,
            latency_ms=latency_ms,
            request_id=request_id,
            metadata=metadata or {},
        )

        # Update counters
        self._total_prompt_tokens += prompt_tokens
        self._total_completion_tokens += completion_tokens
        self._total_cost_usd += cost
        self._total_requests += 1

        # Add to history
        self._usage_history.append(usage)
        if len(self._usage_history) > self.max_history:
            self._usage_history.pop(0)

        # Check budgets
        self._check_budget_alerts(usage)

        logger.debug(
            f"Token usage: {provider}/{model} - "
            f"{total_tokens} tokens (${cost:.6f})"
        )

        return usage

    async def track_request_async(
        self,
        provider: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        latency_ms: float = 0.0,
        request_id: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TokenUsage:
        """Async version of track_request."""
        async with self._lock:
            return self.track_request(
                provider=provider,
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                latency_ms=latency_ms,
                request_id=request_id,
                metadata=metadata,
            )

    def _check_budget_alerts(self, usage: TokenUsage) -> None:
        """Check if any budget thresholds are crossed."""
        for budget_name, budget in self.budgets.items():
            usage_key = f"{budget_name}_tokens"
            cost_key = f"{budget_name}_cost"

            # Calculate period usage
            period_start = datetime.now() - timedelta(hours=budget.period_hours)
            period_usage = [
                u for u in self._usage_history
                if u.timestamp >= period_start
            ]

            period_tokens = sum(u.total_tokens for u in period_usage)
            period_cost = sum(u.cost_usd for u in period_usage)

            # Check threshold
            token_threshold = budget.max_tokens * budget.alert_threshold
            cost_threshold = budget.max_cost_usd * budget.alert_threshold

            if period_tokens >= token_threshold or period_cost >= cost_threshold:
                alert_msg = (
                    f"Budget alert: {budget_name} at "
                    f"{period_tokens}/{budget.max_tokens} tokens, "
                    f"${period_cost:.4f}/${budget.max_cost_usd:.4f}"
                )
                logger.warning(alert_msg)

                for callback in self._alert_callbacks:
                    try:
                        callback(budget_name, {
                            "type": "budget_alert",
                            "budget": budget_name,
                            "tokens_used": period_tokens,
                            "tokens_max": budget.max_tokens,
                            "cost_used": period_cost,
                            "cost_max": budget.max_cost_usd,
                        })
                    except Exception as e:
                        logger.error(f"Alert callback error: {e}")

    def register_alert_callback(
        self,
        callback: Callable[[str, Any], None]
    ) -> None:
        """Register callback for budget alerts."""
        self._alert_callbacks.append(callback)

    def is_over_budget(self, budget_name: str) -> bool:
        """Check if a budget is exceeded."""
        if budget_name not in self.budgets:
            return False

        budget = self.budgets[budget_name]
        period_start = datetime.now() - timedelta(hours=budget.period_hours)

        period_usage = [
            u for u in self._usage_history
            if u.timestamp >= period_start
        ]

        period_tokens = sum(u.total_tokens for u in period_usage)
        period_cost = sum(u.cost_usd for u in period_usage)

        return period_tokens >= budget.max_tokens or period_cost >= budget.max_cost_usd

    def get_budget_status(self, budget_name: str) -> Dict[str, Any]:
        """Get current status of a budget."""
        if budget_name not in self.budgets:
            return {"exists": False}

        budget = self.budgets[budget_name]
        period_start = datetime.now() - timedelta(hours=budget.period_hours)

        period_usage = [
            u for u in self._usage_history
            if u.timestamp >= period_start
        ]

        period_tokens = sum(u.total_tokens for u in period_usage)
        period_cost = sum(u.cost_usd for u in period_usage)

        return {
            "exists": True,
            "name": budget_name,
            "period_hours": budget.period_hours,
            "tokens_used": period_tokens,
            "tokens_max": budget.max_tokens,
            "tokens_percent": (period_tokens / budget.max_tokens * 100) if budget.max_tokens > 0 else 0,
            "cost_used": period_cost,
            "cost_max": budget.max_cost_usd,
            "cost_percent": (period_cost / budget.max_cost_usd * 100) if budget.max_cost_usd > 0 else 0,
            "is_over": period_tokens >= budget.max_tokens or period_cost >= budget.max_cost_usd,
            "requests_count": len(period_usage),
        }

    def get_report(
        self,
        period_hours: Optional[float] = None,
    ) -> TokenReport:
        """
        Get token usage report.

        Args:
            period_hours: Optional period to report (None = all time)

        Returns:
            TokenReport with usage statistics
        """
        if period_hours:
            period_start = datetime.now() - timedelta(hours=period_hours)
            usage_list = [
                u for u in self._usage_history
                if u.timestamp >= period_start
            ]
        else:
            period_start = self._usage_history[0].timestamp if self._usage_history else datetime.now()
            usage_list = self._usage_history

        if not usage_list:
            return TokenReport(
                timestamp=datetime.now(),
                period_start=period_start,
                period_end=datetime.now(),
                total_requests=0,
                total_prompt_tokens=0,
                total_completion_tokens=0,
                total_tokens=0,
                total_cost_usd=0.0,
                avg_tokens_per_request=0.0,
                avg_cost_per_request=0.0,
                avg_latency_ms=0.0,
                by_provider={},
                by_model={},
            )

        # Aggregate by provider and model
        by_provider: Dict[str, Dict[str, int]] = {}
        by_model: Dict[str, Dict[str, int]] = {}

        for usage in usage_list:
            # By provider
            if usage.provider not in by_provider:
                by_provider[usage.provider] = {
                    "requests": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                }
            by_provider[usage.provider]["requests"] += 1
            by_provider[usage.provider]["prompt_tokens"] += usage.prompt_tokens
            by_provider[usage.provider]["completion_tokens"] += usage.completion_tokens
            by_provider[usage.provider]["total_tokens"] += usage.total_tokens

            # By model
            key = f"{usage.provider}/{usage.model}"
            if key not in by_model:
                by_model[key] = {
                    "requests": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                }
            by_model[key]["requests"] += 1
            by_model[key]["prompt_tokens"] += usage.prompt_tokens
            by_model[key]["completion_tokens"] += usage.completion_tokens
            by_model[key]["total_tokens"] += usage.total_tokens

        total_prompt = sum(u.prompt_tokens for u in usage_list)
        total_completion = sum(u.completion_tokens for u in usage_list)
        total_cost = sum(u.cost_usd for u in usage_list)
        total_latency = sum(u.latency_ms for u in usage_list)
        count = len(usage_list)

        return TokenReport(
            timestamp=datetime.now(),
            period_start=period_start,
            period_end=datetime.now(),
            total_requests=count,
            total_prompt_tokens=total_prompt,
            total_completion_tokens=total_completion,
            total_tokens=total_prompt + total_completion,
            total_cost_usd=total_cost,
            avg_tokens_per_request=(total_prompt + total_completion) / count if count > 0 else 0,
            avg_cost_per_request=total_cost / count if count > 0 else 0,
            avg_latency_ms=total_latency / count if count > 0 else 0,
            by_provider=by_provider,
            by_model=by_model,
            budget_status={
                name: self.get_budget_status(name)
                for name in self.budgets
            },
        )

    def get_live_stats(self) -> Dict[str, Any]:
        """Get live statistics without full report."""
        return {
            "total_requests": self._total_requests,
            "total_prompt_tokens": self._total_prompt_tokens,
            "total_completion_tokens": self._total_completion_tokens,
            "total_tokens": self._total_prompt_tokens + self._total_completion_tokens,
            "total_cost_usd": round(self._total_cost_usd, 6),
            "history_size": len(self._usage_history),
            "budgets": {
                name: self.get_budget_status(name)
                for name in self.budgets
            },
        }

    def reset(self) -> None:
        """Reset all counters and history."""
        self._usage_history.clear()
        self._total_prompt_tokens = 0
        self._total_completion_tokens = 0
        self._total_cost_usd = 0.0
        self._total_requests = 0
        logger.info("Token tracker reset")


class TokenEstimator:
    """Estimate token count for text without API call."""

    # Rough estimates (characters per token varies by language)
    CHARS_PER_TOKEN_EN = 4.0
    CHARS_PER_TOKEN_OTHER = 2.5

    @classmethod
    def estimate_tokens(
        cls,
        text: str,
        language: str = "en",
    ) -> int:
        """Estimate token count for text."""
        chars_per_token = (
            cls.CHARS_PER_TOKEN_EN
            if language.lower() == "en"
            else cls.CHARS_PER_TOKEN_OTHER
        )
        return int(len(text) / chars_per_token)

    @classmethod
    def estimate_cost(
        cls,
        text: str,
        provider: str,
        model: str,
        language: str = "en",
    ) -> float:
        """Estimate cost for generating text."""
        tokens = cls.estimate_tokens(text, language)
        return PricingModel.get_cost(provider, model, 0, tokens)
