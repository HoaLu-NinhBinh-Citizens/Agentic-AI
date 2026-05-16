"""LLM-specific metrics for observability.

Provides metrics for LLM requests, token usage, provider performance, and tool calls.
"""

from __future__ import annotations

import logging
from typing import Any

from infrastructure.observability.metrics import MetricsRegistry

logger = logging.getLogger(__name__)

METRIC_LLM_REQUEST_TOTAL = "llm_request_total"
METRIC_LLM_REQUEST_DURATION = "llm_request_duration_ms"
METRIC_LLM_TOKEN_USAGE = "llm_token_usage_total"
METRIC_PROVIDER_FALLBACK = "provider_fallback_total"
METRIC_TOOL_CALL_FAILURE = "tool_call_failure_total"
METRIC_TOOL_CALL_DURATION = "tool_call_duration_ms"

DURATION_BUCKETS_MS = [100, 250, 500, 1000, 2500, 5000, 10000, 30000, 60000, 120000]


class LLMMetrics:
    """LLM-specific metrics recorder.

    Provides convenience methods for recording LLM-related metrics.
    """

    def __init__(self, registry: MetricsRegistry | None = None) -> None:
        """Initialize LLM metrics.

        Args:
            registry: Metrics registry instance (uses singleton if None).
        """
        self._registry = registry or MetricsRegistry.get_instance()
        self._setup_histogram_buckets()

    def _setup_histogram_buckets(self) -> None:
        """Setup histogram bucket configurations."""
        self._registry.set_histogram_buckets(METRIC_LLM_REQUEST_DURATION, DURATION_BUCKETS_MS)
        self._registry.set_histogram_buckets(METRIC_TOOL_CALL_DURATION, DURATION_BUCKETS_MS)

    async def record_llm_request(
        self,
        provider: str,
        success: bool,
        duration_ms: float,
        tokens_used: int | None = None,
        finish_reason: str | None = None,
    ) -> None:
        """Record an LLM request.

        Args:
            provider: Provider name (e.g., 'ollama', 'groq').
            success: Whether the request succeeded.
            duration_ms: Request duration in milliseconds.
            tokens_used: Total tokens used.
            finish_reason: Reason for completion (stop, tool_calls, etc.).
        """
        tags = {"provider": provider, "success": str(success).lower()}

        await self._registry.inc_counter(METRIC_LLM_REQUEST_TOTAL, tags)

        await self._registry.observe_histogram(
            METRIC_LLM_REQUEST_DURATION,
            duration_ms / 1000.0,
            {"provider": provider},
        )

        if tokens_used is not None:
            await self._registry.inc_counter(
                METRIC_LLM_TOKEN_USAGE,
                {"provider": provider, "type": "total"},
                tokens_used,
            )

    async def record_token_usage(
        self,
        provider: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
    ) -> None:
        """Record token usage breakdown.

        Args:
            provider: Provider name.
            prompt_tokens: Number of prompt tokens.
            completion_tokens: Number of completion tokens.
        """
        if prompt_tokens > 0:
            await self._registry.inc_counter(
                METRIC_LLM_TOKEN_USAGE,
                {"provider": provider, "type": "prompt"},
                prompt_tokens,
            )

        if completion_tokens > 0:
            await self._registry.inc_counter(
                METRIC_LLM_TOKEN_USAGE,
                {"provider": provider, "type": "completion"},
                completion_tokens,
            )

    async def record_provider_fallback(
        self,
        from_provider: str,
        to_provider: str,
    ) -> None:
        """Record a provider fallback event.

        Args:
            from_provider: Provider that failed.
            to_provider: Provider that was used as fallback.
        """
        await self._registry.inc_counter(
            METRIC_PROVIDER_FALLBACK,
            {"from": from_provider, "to": to_provider},
        )

    async def record_tool_call(
        self,
        tool_name: str,
        success: bool,
        duration_ms: float,
        error_code: str | None = None,
    ) -> None:
        """Record a tool call execution.

        Args:
            tool_name: Name of the tool.
            success: Whether the call succeeded.
            duration_ms: Execution duration in milliseconds.
            error_code: Error code if failed.
        """
        tags = {"tool": tool_name, "success": str(success).lower()}
        if error_code:
            tags["error_code"] = error_code

        await self._registry.inc_counter("tool_calls_total", tags)

        await self._registry.observe_histogram(
            METRIC_TOOL_CALL_DURATION,
            duration_ms / 1000.0,
            {"tool": tool_name},
        )

    async def record_tool_failure(
        self,
        tool_name: str,
        error_code: str,
    ) -> None:
        """Record a tool call failure.

        Args:
            tool_name: Name of the tool.
            error_code: Error code.
        """
        await self._registry.inc_counter(
            METRIC_TOOL_CALL_FAILURE,
            {"tool": tool_name, "error_code": error_code},
        )

    async def record_provider_circuit_open(self, provider: str) -> None:
        """Record when a provider's circuit breaker opens.

        Args:
            provider: Provider name.
        """
        await self._registry.inc_counter(
            "provider_circuit_breaker_total",
            {"provider": provider, "action": "open"},
        )

    async def record_provider_circuit_close(self, provider: str) -> None:
        """Record when a provider's circuit breaker closes.

        Args:
            provider: Provider name.
        """
        await self._registry.inc_counter(
            "provider_circuit_breaker_total",
            {"provider": provider, "action": "close"},
        )


_llm_metrics: LLMMetrics | None = None


def get_llm_metrics() -> LLMMetrics:
    """Get the global LLM metrics instance.

    Returns:
        LLMMetrics instance.
    """
    global _llm_metrics
    if _llm_metrics is None:
        _llm_metrics = LLMMetrics()
    return _llm_metrics
