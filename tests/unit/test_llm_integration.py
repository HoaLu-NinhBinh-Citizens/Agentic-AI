"""Tests for LLM integration adapters and providers."""

from __future__ import annotations

import os
import pytest

from src.infrastructure.llm.adapters import (
    LLMProvider,
    LLMResponse,
    OpenAIAdapter,
    ClaudeAdapter,
    MockLLMProvider,
    create_llm_provider_from_env,
    create_llm_provider,
)


class TestLLMResponse:
    """Tests for LLMResponse dataclass."""

    def test_response_creation(self):
        """Test basic LLMResponse creation."""
        response = LLMResponse(
            content="Hello, world!",
            model="gpt-4",
            tokens_used=100,
            finish_reason="stop",
        )
        assert response.content == "Hello, world!"
        assert response.model == "gpt-4"
        assert response.tokens_used == 100
        assert response.finish_reason == "stop"

    def test_response_defaults(self):
        """Test LLMResponse default values."""
        response = LLMResponse(content="Test", model="test-model")
        assert response.tokens_used == 0
        assert response.finish_reason == "stop"
        assert response.raw is None


class TestMockLLMProvider:
    """Tests for MockLLMProvider."""

    @pytest.mark.asyncio
    async def test_mock_provider_generate(self):
        """Test mock provider returns predictable response."""
        provider = MockLLMProvider(response_text="Mock response")
        response = await provider.generate("Tell me something")

        assert "Mock response" in response.content
        assert response.model == "mock-model"
        assert response.tokens_used > 0

    @pytest.mark.asyncio
    async def test_mock_provider_with_system(self):
        """Test mock provider with system prompt."""
        provider = MockLLMProvider(response_text="Custom")
        response = await provider.generate(
            prompt="Hello",
            system_prompt="You are a helpful assistant",
        )
        assert "Custom" in response.content


class TestCreateLLMProvider:
    """Tests for provider factory functions."""

    def test_create_openai_provider(self):
        """Test creating OpenAI provider."""
        provider = create_llm_provider("openai", api_key="test-key")
        assert isinstance(provider, OpenAIAdapter)
        assert provider.api_key == "test-key"

    def test_create_anthropic_provider(self):
        """Test creating Anthropic provider."""
        provider = create_llm_provider("anthropic", api_key="test-key")
        assert isinstance(provider, ClaudeAdapter)
        assert provider.api_key == "test-key"

    def test_create_mock_provider(self):
        """Test creating mock provider."""
        provider = create_llm_provider("mock")
        assert isinstance(provider, MockLLMProvider)

    def test_create_provider_with_custom_model(self):
        """Test creating provider with custom model."""
        provider = create_llm_provider("openai", model="gpt-4o")
        assert provider.model == "gpt-4o"

    def test_create_invalid_provider_raises(self):
        """Test creating invalid provider raises ValueError."""
        with pytest.raises(ValueError, match="Unknown provider"):
            create_llm_provider("invalid")


class TestCreateLLMProviderFromEnv:
    """Tests for environment-based provider creation."""

    def test_create_from_env_no_keys(self):
        """Test returns None when no API keys set."""
        # Save original env vars
        original_openai = os.environ.pop("OPENAI_API_KEY", None)
        original_anthropic = os.environ.pop("ANTHROPIC_API_KEY", None)

        try:
            provider = create_llm_provider_from_env()
            # Should return None or Mock if no keys
            assert provider is None or isinstance(provider, MockLLMProvider)
        finally:
            # Restore env vars
            if original_openai:
                os.environ["OPENAI_API_KEY"] = original_openai
            if original_anthropic:
                os.environ["ANTHROPIC_API_KEY"] = original_anthropic

    def test_create_from_env_with_openai_key(self):
        """Test creates OpenAI provider when key is set."""
        original = os.environ.get("OPENAI_API_KEY")
        os.environ["OPENAI_API_KEY"] = "test-openai-key"

        try:
            provider = create_llm_provider_from_env()
            assert provider is not None
            assert isinstance(provider, OpenAIAdapter)
            assert provider.api_key == "test-openai-key"
        finally:
            if original:
                os.environ["OPENAI_API_KEY"] = original
            else:
                os.environ.pop("OPENAI_API_KEY", None)

    def test_create_from_env_with_anthropic_key(self):
        """Test creates Anthropic provider when key is set."""
        original_openai = os.environ.pop("OPENAI_API_KEY", None)
        original = os.environ.get("ANTHROPIC_API_KEY")
        os.environ["ANTHROPIC_API_KEY"] = "test-anthropic-key"

        try:
            provider = create_llm_provider_from_env()
            assert provider is not None
            assert isinstance(provider, ClaudeAdapter)
            assert provider.api_key == "test-anthropic-key"
        finally:
            if original:
                os.environ["ANTHROPIC_API_KEY"] = original
            else:
                os.environ.pop("ANTHROPIC_API_KEY", None)
            if original_openai:
                os.environ["OPENAI_API_KEY"] = original_openai


@pytest.mark.asyncio
class TestOpenAIAdapter:
    """Tests for OpenAI adapter (with mock mode when no key)."""

    async def test_openai_adapter_without_key_raises(self):
        """Test OpenAI adapter raises when no API key."""
        original = os.environ.pop("OPENAI_API_KEY", None)
        adapter = OpenAIAdapter()

        try:
            with pytest.raises(ValueError, match="API key not configured"):
                await adapter.generate("test prompt")
        finally:
            if original:
                os.environ["OPENAI_API_KEY"] = original

    async def test_openai_adapter_availability(self):
        """Test availability check."""
        original = os.environ.pop("OPENAI_API_KEY", None)
        adapter = OpenAIAdapter()

        # Should not be available without key
        assert not adapter.is_available()

        if original:
            os.environ["OPENAI_API_KEY"] = original

        adapter_with_key = OpenAIAdapter(api_key="test-key")
        assert adapter_with_key.is_available()


@pytest.mark.asyncio
class TestClaudeAdapter:
    """Tests for Anthropic Claude adapter."""

    async def test_claude_adapter_without_key_raises(self):
        """Test Claude adapter raises when no API key."""
        original = os.environ.pop("ANTHROPIC_API_KEY", None)
        adapter = ClaudeAdapter()

        try:
            with pytest.raises(ValueError, match="API key not configured"):
                await adapter.generate("test prompt")
        finally:
            if original:
                os.environ["ANTHROPIC_API_KEY"] = original

    async def test_claude_adapter_availability(self):
        """Test availability check."""
        original = os.environ.pop("ANTHROPIC_API_KEY", None)
        adapter = ClaudeAdapter()

        assert not adapter.is_available()

        if original:
            os.environ["ANTHROPIC_API_KEY"] = original

        adapter_with_key = ClaudeAdapter(api_key="test-key")
        assert adapter_with_key.is_available()
