"""Unit tests for LLM providers."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.infrastructure.llm.providers_extended import (
    Provider,
    ProviderConfig,
    MultiProviderClient,
    GroqClient,
    PerplexityClient,
    PROVIDER_MODELS,
)


class TestProviderEnum:
    """Tests for Provider enum."""

    def test_all_providers(self):
        """Test all providers defined."""
        assert Provider.OLLAMA in Provider
        assert Provider.OPENAI in Provider
        assert Provider.ANTHROPIC in Provider
        assert Provider.GROQ in Provider
        assert Provider.COHERE in Provider
        assert Provider.MISTRAL in Provider
        assert Provider.VERTEX in Provider
        assert Provider.BEDROCK in Provider


class TestProviderModels:
    """Tests for provider models."""

    def test_groq_models(self):
        """Test Groq models."""
        assert "llama-3.3-70b-versatile" in PROVIDER_MODELS[Provider.GROQ]

    def test_openai_models(self):
        """Test OpenAI models."""
        assert "gpt-4o" in PROVIDER_MODELS[Provider.OPENAI]

    def test_anthropic_models(self):
        """Test Anthropic models."""
        assert "claude-opus-4-5" in PROVIDER_MODELS[Provider.ANTHROPIC]


class TestProviderConfig:
    """Tests for ProviderConfig."""

    def test_create_config(self):
        """Test creating config."""
        config = ProviderConfig(
            provider=Provider.GROQ,
            api_key="test-key",
            model="llama-3.3-70b-versatile",
            max_tokens=4096,
            temperature=0.7,
        )
        
        assert config.provider == Provider.GROQ
        assert config.api_key == "test-key"
        assert config.max_tokens == 4096


class TestMultiProviderClient:
    """Tests for MultiProviderClient."""

    def test_create_client(self):
        """Test creating client."""
        client = MultiProviderClient()
        
        assert len(client._configs) == 0
        assert len(client._clients) == 0

    def test_configure(self):
        """Test configuring a provider."""
        client = MultiProviderClient()
        config = ProviderConfig(
            provider=Provider.GROQ,
            api_key="test-key",
        )
        
        client.configure(config)
        
        assert Provider.GROQ in client._configs
        assert Provider.GROQ in client._clients

    def test_get_default_url(self):
        """Test getting default URLs."""
        client = MultiProviderClient()
        
        assert "api.groq.com" in client._get_default_url(Provider.GROQ)
        assert "api.openai.com" in client._get_default_url(Provider.OPENAI)
        assert "api.anthropic.com" in client._get_default_url(Provider.ANTHROPIC)

    def test_get_headers(self):
        """Test getting headers."""
        client = MultiProviderClient()
        
        headers = client._get_headers(Provider.GROQ, "test-key")
        assert "Authorization" in headers
        
        headers = client._get_headers(Provider.ANTHROPIC, "test-key")
        assert "x-api-key" in headers


class TestGroqClient:
    """Tests for GroqClient."""

    def test_create_client(self):
        """Test creating Groq client."""
        client = GroqClient("test-api-key")
        
        assert client.api_key == "test-api-key"
        assert "groq.com" in client.base_url


class TestPerplexityClient:
    """Tests for PerplexityClient."""

    def test_create_client(self):
        """Test creating Perplexity client."""
        client = PerplexityClient("test-api-key")
        
        assert client.api_key == "test-api-key"
        assert "perplexity.ai" in client.base_url
