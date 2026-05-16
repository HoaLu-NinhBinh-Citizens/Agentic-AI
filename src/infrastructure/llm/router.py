"""LLM Router with circuit breakers per provider.

Routes requests to appropriate LLM providers based on complexity,
availability, and circuit breaker state.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from infrastructure.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerState,
)

from .provider import LLMProvider

logger = logging.getLogger(__name__)


@dataclass
class RouterConfig:
    """Configuration for the LLM router."""

    provider_order: list[str] = field(default_factory=lambda: ["local", "cloud"])
    fallback_enabled: bool = True
    complexity_threshold: float = 0.6
    keyword_weights: dict[str, float] = field(default_factory=lambda: {
        "analyze": 0.3,
        "design": 0.3,
        "debug": 0.25,
        "optimize": 0.25,
        "refactor": 0.3,
        "architecture": 0.35,
        "complex": 0.2,
        "advanced": 0.2,
        "detailed": 0.15,
    })

    @classmethod
    def from_dict(cls, config: dict[str, Any]) -> RouterConfig:
        """Create config from dictionary.

        Args:
            config: Configuration dictionary.

        Returns:
            RouterConfig instance.
        """
        router_config = config.get("router", {})
        providers_config = config.get("providers", {})

        keyword_weights = router_config.get("keyword_weights", {})

        local_breaker_config = providers_config.get("local", {}).get("circuit_breaker", {})
        cloud_breaker_config = providers_config.get("cloud", {}).get("circuit_breaker", {})

        return cls(
            provider_order=router_config.get("provider_order", ["local", "cloud"]),
            fallback_enabled=router_config.get("fallback_enabled", True),
            complexity_threshold=router_config.get("complexity_threshold", 0.6),
            keyword_weights=keyword_weights,
        )


class LLMRouter:
    """Routes LLM requests to appropriate providers with circuit breakers.

    Uses content complexity analysis and provider availability to select
    the best provider for each request.
    """

    def __init__(self, config: RouterConfig | None = None) -> None:
        """Initialize the router.

        Args:
            config: Router configuration.
        """
        self._config = config or RouterConfig()
        self._providers: dict[str, LLMProvider] = {}
        self._breakers: dict[str, CircuitBreaker] = {}
        self._breaker_configs: dict[str, dict[str, Any]] = {}

    def register_provider(
        self,
        name: str,
        provider: LLMProvider,
        circuit_breaker_config: dict[str, Any] | None = None,
    ) -> None:
        """Register a provider with the router.

        Args:
            name: Provider identifier (e.g., 'local', 'cloud').
            provider: LLM provider instance.
            circuit_breaker_config: Optional circuit breaker configuration.
        """
        self._providers[name] = provider

        if circuit_breaker_config:
            self._breaker_configs[name] = circuit_breaker_config
            self._breakers[name] = CircuitBreaker(
                name=f"llm_{name}",
                failure_threshold=circuit_breaker_config.get("failure_threshold", 3),
                window_seconds=circuit_breaker_config.get("window_seconds", 60),
                timeout_seconds=circuit_breaker_config.get("timeout_seconds", 30),
            )
            logger.info("Registered provider '%s' with circuit breaker", name)
        else:
            self._breakers[name] = CircuitBreaker(name=f"llm_{name}")
            logger.info("Registered provider '%s' without circuit breaker", name)

    def get_provider_names(self) -> list[str]:
        """Get list of registered provider names.

        Returns:
            List of provider names.
        """
        return list(self._providers.keys())

    def get_provider(self, name: str) -> LLMProvider | None:
        """Get a provider by name.

        Args:
            name: Provider name.

        Returns:
            Provider instance or None.
        """
        return self._providers.get(name)

    def get_breaker(self, name: str) -> CircuitBreaker | None:
        """Get circuit breaker for a provider.

        Args:
            name: Provider name.

        Returns:
            Circuit breaker or None.
        """
        return self._breakers.get(name)

    def is_provider_available(self, name: str) -> bool:
        """Check if a provider is available.

        Args:
            name: Provider name.

        Returns:
            True if provider is registered and circuit is closed.
        """
        if name not in self._providers:
            return False
        breaker = self._breakers.get(name)
        if breaker is None:
            return True
        return breaker.state != CircuitBreakerState.OPEN

    def get_circuit_state(self, name: str) -> str:
        """Get circuit state for a provider.

        Args:
            name: Provider name.

        Returns:
            Circuit state as string.
        """
        breaker = self._breakers.get(name)
        if breaker is None:
            return "unknown"
        return breaker.state.value

    async def select_provider(
        self,
        message: str,
        tools: list[dict[str, Any]] | None = None,
        client_hint: str | None = None,
    ) -> LLMProvider | None:
        """Select the best provider for a request.

        Args:
            message: The user's message.
            tools: Available tools for the request.
            client_hint: Optional client-specified provider preference.

        Returns:
            Selected provider or None if no provider is available.
        """
        if client_hint and client_hint in self._providers:
            if self.is_provider_available(client_hint):
                logger.info("Using client-specified provider: %s", client_hint)
                return self._providers[client_hint]
            logger.warning("Client requested unavailable provider: %s", client_hint)

        complexity = self._estimate_complexity(message, tools or [])

        if complexity < self._config.complexity_threshold:
            for name in self._config.provider_order:
                if name == "local" and name in self._providers:
                    if self.is_provider_available(name):
                        logger.info("Selected local provider (low complexity: %.2f)", complexity)
                        return self._providers[name]

        for name in self._config.provider_order:
            if name == "cloud" and name in self._providers:
                if self.is_provider_available(name):
                    logger.info("Selected cloud provider (high complexity: %.2f)", complexity)
                    return self._providers[name]

        for name, provider in self._providers.items():
            if self.is_provider_available(name):
                logger.info("Selected fallback provider: %s", name)
                return provider

        local = self._providers.get("local")
        if local:
            logger.warning("All providers unavailable, falling back to local")
            return local

        return None

    def _estimate_complexity(self, message: str, tools: list[dict[str, Any]]) -> float:
        """Estimate request complexity based on content and tools.

        Args:
            message: User message.
            tools: Available tools.

        Returns:
            Complexity score between 0 and 1.
        """
        score = 0.0
        msg_lower = message.lower()

        for keyword, weight in self._config.keyword_weights.items():
            if keyword in msg_lower:
                score += weight

        score += min(len(tools) * 0.05, 0.3)

        score += min(len(message) / 1000, 0.2)

        return min(score, 1.0)

    def record_success(self, provider_name: str) -> None:
        """Record a successful call for a provider.

        Args:
            provider_name: Name of the provider.
        """
        breaker = self._breakers.get(provider_name)
        if breaker:
            logger.debug("Recording success for provider: %s", provider_name)

    def record_failure(self, provider_name: str, error: Exception | None = None) -> None:
        """Record a failed call for a provider.

        Args:
            provider_name: Name of the provider.
            error: Optional exception that caused the failure.
        """
        breaker = self._breakers.get(provider_name)
        if breaker:
            error_msg = str(error) if error else "unknown"
            logger.warning(
                "Recording failure for provider %s: %s",
                provider_name,
                error_msg,
            )

    def get_stats(self) -> dict[str, Any]:
        """Get router statistics.

        Returns:
            Dictionary with provider states and circuit breaker stats.
        """
        stats = {
            "providers": {},
            "config": {
                "complexity_threshold": self._config.complexity_threshold,
                "fallback_enabled": self._config.fallback_enabled,
                "provider_order": self._config.provider_order,
            },
        }

        for name, provider in self._providers.items():
            breaker = self._breakers.get(name)
            stats["providers"][name] = {
                "available": self.is_provider_available(name),
                "circuit_state": self.get_circuit_state(name),
                "failure_count": breaker.failure_count if breaker else 0,
            }

        return stats

    async def health_check_all(self) -> dict[str, bool]:
        """Check health of all registered providers.

        Returns:
            Dictionary mapping provider names to health status.
        """
        results = {}
        for name, provider in self._providers.items():
            try:
                healthy = await provider.health_check()
                results[name] = healthy
            except Exception as e:
                logger.warning("Health check failed for %s: %s", name, str(e))
                results[name] = False
        return results
