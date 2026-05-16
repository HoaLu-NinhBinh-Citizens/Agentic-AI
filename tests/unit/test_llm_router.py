"""Unit tests for LLM Router."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from infrastructure.llm.router import LLMRouter, RouterConfig
from infrastructure.llm.provider import LLMProvider
from infrastructure.resilience.circuit_breaker import CircuitBreakerState


class MockProvider(LLMProvider):
    """Mock LLM provider for testing."""

    def __init__(self, name: str = "mock", supports_tools: bool = True):
        super().__init__(name)
        self._supports_tools = supports_tools

    async def stream_chat(self, messages, tools=None, temperature=0.1, max_tokens=None):
        return
        yield  # Make this a generator

    async def health_check(self) -> bool:
        return True

    def supports_tools(self) -> bool:
        return self._supports_tools


class TestRouterConfig:
    """Tests for RouterConfig."""

    def test_default_config(self):
        """Test default configuration."""
        config = RouterConfig()
        assert config.provider_order == ["local", "cloud"]
        assert config.fallback_enabled is True
        assert config.complexity_threshold == 0.6

    def test_config_from_dict(self):
        """Test creating config from dictionary."""
        config_dict = {
            "router": {
                "provider_order": ["local"],
                "complexity_threshold": 0.5,
            },
            "providers": {
                "local": {
                    "circuit_breaker": {"failure_threshold": 5}
                }
            }
        }
        config = RouterConfig.from_dict(config_dict)
        assert config.provider_order == ["local"]
        assert config.complexity_threshold == 0.5


class TestLLMRouter:
    """Tests for LLMRouter."""

    @pytest.fixture
    def router(self):
        """Create a fresh router."""
        return LLMRouter()

    @pytest.fixture
    def mock_provider(self):
        """Create a mock provider."""
        return MockProvider("test")

    def test_register_provider(self, router, mock_provider):
        """Test registering a provider."""
        router.register_provider("local", mock_provider)

        assert router.get_provider("local") == mock_provider
        assert "local" in router.get_provider_names()

    def test_register_provider_with_circuit_breaker(self, router, mock_provider):
        """Test registering a provider with circuit breaker."""
        cb_config = {"failure_threshold": 3, "window_seconds": 60}
        router.register_provider("local", mock_provider, cb_config)

        breaker = router.get_breaker("local")
        assert breaker is not None
        assert breaker.name == "llm_local"

    def test_is_provider_available(self, router, mock_provider):
        """Test checking provider availability."""
        router.register_provider("local", mock_provider)

        assert router.is_provider_available("local")
        assert not router.is_provider_available("nonexistent")

    def test_get_circuit_state(self, router, mock_provider):
        """Test getting circuit state."""
        router.register_provider("local", mock_provider)

        state = router.get_circuit_state("local")
        assert state == "closed"

    @pytest.mark.asyncio
    async def test_select_provider_client_hint(self, router):
        """Test provider selection respects client hint."""
        local = MockProvider("local")
        cloud = MockProvider("cloud")
        router.register_provider("local", local)
        router.register_provider("cloud", cloud)

        provider = await router.select_provider(
            message="test",
            tools=[],
            client_hint="cloud"
        )

        assert provider == cloud

    @pytest.mark.asyncio
    async def test_select_provider_low_complexity(self, router):
        """Test provider selection for low complexity (local)."""
        local = MockProvider("local")
        cloud = MockProvider("cloud")
        router.register_provider("local", local)
        router.register_provider("cloud", cloud)

        provider = await router.select_provider(
            message="hello",  # Simple message
            tools=[],
        )

        assert provider == local

    @pytest.mark.asyncio
    async def test_select_provider_high_complexity(self, router):
        """Test provider selection for high complexity (cloud)."""
        local = MockProvider("local")
        cloud = MockProvider("cloud")
        router.register_provider("local", local)
        router.register_provider("cloud", cloud)

        provider = await router.select_provider(
            message="Please analyze the architecture of this complex system and design a solution for optimizing performance",
            tools=[{"name": f"tool_{i}"} for i in range(20)],
        )

        assert provider == cloud

    @pytest.mark.asyncio
    async def test_select_provider_fallback(self, router):
        """Test provider fallback when primary is unavailable."""
        local = MockProvider("local")
        cloud = MockProvider("cloud")
        router.register_provider("local", local, {"failure_threshold": 1})
        router.register_provider("cloud", cloud)

        breaker = router.get_breaker("local")
        breaker._state = CircuitBreakerState.OPEN

        provider = await router.select_provider(message="test", tools=[])

        assert provider == cloud

    @pytest.mark.asyncio
    async def test_select_provider_all_unavailable(self, router):
        """Test fallback when all providers are unavailable."""
        local = MockProvider("local")
        cloud = MockProvider("cloud")
        router.register_provider("local", local, {"failure_threshold": 1})
        router.register_provider("cloud", cloud, {"failure_threshold": 1})

        router.get_breaker("local")._state = CircuitBreakerState.OPEN
        router.get_breaker("cloud")._state = CircuitBreakerState.OPEN

        provider = await router.select_provider(message="test", tools=[])

        assert provider == local  # Falls back to local anyway

    def test_record_success(self, router, mock_provider):
        """Test recording success."""
        router.register_provider("local", mock_provider, {"failure_threshold": 3})
        router.record_success("local")

    def test_record_failure(self, router, mock_provider):
        """Test recording failure."""
        router.register_provider("local", mock_provider, {"failure_threshold": 3})
        router.record_failure("local", Exception("test error"))

    def test_get_stats(self, router, mock_provider):
        """Test getting router statistics."""
        router.register_provider("local", mock_provider)

        stats = router.get_stats()

        assert "providers" in stats
        assert "config" in stats
        assert "local" in stats["providers"]

    @pytest.mark.asyncio
    async def test_health_check_all(self, router):
        """Test health checking all providers."""
        local = MockProvider("local")
        cloud = MockProvider("cloud")
        router.register_provider("local", local)
        router.register_provider("cloud", cloud)

        results = await router.health_check_all()

        assert results["local"] is True
        assert results["cloud"] is True

    def test_complexity_estimation(self, router):
        """Test complexity estimation."""
        simple = "hello world"
        complex_msg = "Please analyze and design an optimized architecture for the complex distributed system"

        tools = [{"name": f"tool_{i}"} for i in range(10)]

        simple_score = router._estimate_complexity(simple, [])
        complex_score = router._estimate_complexity(complex_msg, tools)

        assert complex_score > simple_score
        assert simple_score < 1.0
        assert complex_score <= 1.0
