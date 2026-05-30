"""LLM Provider Adapters - SDK-based adapters for OpenAI and Anthropic.

This module provides:
- LLMProvider abstract interface
- OpenAIAdapter using official openai SDK
- ClaudeAdapter using official anthropic SDK
- Environment variable based provider detection
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    """Response from LLM provider.

    Attributes:
        content: The generated text content
        model: Model identifier used
        tokens_used: Total tokens consumed
        finish_reason: Why generation stopped (stop, length, etc.)
        raw: Raw response data from provider
    """
    content: str
    model: str
    tokens_used: int = 0
    finish_reason: str = "stop"
    raw: Optional[dict] = None


class LLMProvider(ABC):
    """Abstract LLM provider interface.

    All concrete adapters must implement this interface to ensure
    consistent behavior across different LLM backends.
    """

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        """Generate response from LLM.

        Args:
            prompt: User prompt to send
            system_prompt: Optional system prompt for context
            temperature: Sampling temperature (0.0-2.0)
            max_tokens: Maximum tokens in response

        Returns:
            LLMResponse with generated content
        """
        pass

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the provider name for logging."""
        pass

    def is_available(self) -> bool:
        """Check if provider is configured and available."""
        return True


class OpenAIAdapter(LLMProvider):
    """OpenAI GPT adapter using official SDK.

    Supports GPT-4, GPT-4o, GPT-3.5-turbo and other OpenAI models.
    API key is read from OPENAI_API_KEY environment variable if not provided.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-4o-mini",
    ):
        """Initialize OpenAI adapter.

        Args:
            api_key: OpenAI API key (reads from OPENAI_API_KEY if None)
            model: Model to use (default: gpt-4o-mini for cost efficiency)
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model
        self._client = None

    @property
    def provider_name(self) -> str:
        return "openai"

    def is_available(self) -> bool:
        """Check if OpenAI API key is configured."""
        return bool(self.api_key)

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        """Generate response using OpenAI API.

        Args:
            prompt: User prompt
            system_prompt: Optional system instructions
            temperature: Sampling temperature
            max_tokens: Maximum response tokens

        Returns:
            LLMResponse with generated content
        """
        if not self.api_key:
            raise ValueError(
                "OpenAI API key not configured. "
                "Set OPENAI_API_KEY environment variable or pass api_key to constructor."
            )

        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=self.api_key)

            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            response = await client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            return LLMResponse(
                content=response.choices[0].message.content or "",
                model=response.model,
                tokens_used=response.usage.total_tokens if response.usage else 0,
                finish_reason=response.choices[0].finish_reason,
                raw=response.model_dump() if hasattr(response, "model_dump") else None,
            )

        except ImportError:
            logger.error(
                "OpenAI SDK not installed. Install with: pip install openai>=1.0.0"
            )
            raise
        except Exception as e:
            logger.error("OpenAI API error: %s", e)
            raise


class ClaudeAdapter(LLMProvider):
    """Anthropic Claude adapter using official SDK.

    Supports Claude-3.5 Sonnet, Claude-3 Opus, Claude-3 Haiku, and other Anthropic models.
    API key is read from ANTHROPIC_API_KEY environment variable if not provided.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "claude-sonnet-4-20250514",
    ):
        """Initialize Claude adapter.

        Args:
            api_key: Anthropic API key (reads from ANTHROPIC_API_KEY if None)
            model: Model to use (default: claude-sonnet-4 for balanced performance)
        """
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.model = model
        self._client = None

    @property
    def provider_name(self) -> str:
        return "anthropic"

    def is_available(self) -> bool:
        """Check if Anthropic API key is configured."""
        return bool(self.api_key)

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        """Generate response using Anthropic Claude API.

        Args:
            prompt: User prompt
            system_prompt: Optional system instructions
            temperature: Sampling temperature
            max_tokens: Maximum response tokens

        Returns:
            LLMResponse with generated content
        """
        if not self.api_key:
            raise ValueError(
                "Anthropic API key not configured. "
                "Set ANTHROPIC_API_KEY environment variable or pass api_key to constructor."
            )

        try:
            import anthropic

            client = anthropic.AsyncAnthropic(api_key=self.api_key)

            response = await client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
            )

            content_text = ""
            if response.content and len(response.content) > 0:
                content_block = response.content[0]
                if hasattr(content_block, "text"):
                    content_text = content_block.text

            return LLMResponse(
                content=content_text,
                model=self.model,
                tokens_used=(
                    response.usage.input_tokens + response.usage.output_tokens
                    if hasattr(response.usage, "input_tokens")
                    else 0
                ),
                finish_reason=str(response.stop_reason) if response.stop_reason else "stop",
                raw=response.model_dump() if hasattr(response, "model_dump") else None,
            )

        except ImportError:
            logger.error(
                "Anthropic SDK not installed. Install with: pip install anthropic>=0.20.0"
            )
            raise
        except Exception as e:
            logger.error("Anthropic API error: %s", e)
            raise


class MockLLMProvider(LLMProvider):
    """Mock LLM provider for testing without API calls.

    Returns predictable responses for testing purposes.
    """

    def __init__(self, response_text: str = "Mock response"):
        self.response_text = response_text

    @property
    def provider_name(self) -> str:
        return "mock"

    def is_available(self) -> bool:
        return True

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        """Return mock response."""
        return LLMResponse(
            content=f"{self.response_text}: {prompt[:50]}...",
            model="mock-model",
            tokens_used=len(prompt) // 4,
            finish_reason="stop",
        )


def create_llm_provider_from_env() -> Optional[LLMProvider]:
    """Create LLM provider from environment variables.

    Priority:
    1. OPENAI_API_KEY -> OpenAIAdapter
    2. ANTHROPIC_API_KEY -> ClaudeAdapter
    3. None (no provider configured)

    Returns:
        Configured LLMProvider or None if no API keys found
    """
    if os.getenv("OPENAI_API_KEY"):
        logger.info("Creating OpenAI provider from environment")
        return OpenAIAdapter()

    if os.getenv("ANTHROPIC_API_KEY"):
        logger.info("Creating Anthropic provider from environment")
        return ClaudeAdapter()

    logger.debug("No LLM API keys found in environment")
    return None


def create_llm_provider(
    provider: str,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> LLMProvider:
    """Create LLM provider by name.

    Args:
        provider: Provider name ("openai", "anthropic", "mock")
        api_key: Optional API key override
        model: Optional model override

    Returns:
        Configured LLMProvider

    Raises:
        ValueError: If provider name is unknown
    """
    provider = provider.lower()

    if provider == "openai":
        return OpenAIAdapter(api_key=api_key, model=model or "gpt-4o-mini")
    elif provider == "anthropic":
        return ClaudeAdapter(api_key=api_key, model=model or "claude-sonnet-4-20250514")
    elif provider == "mock":
        return MockLLMProvider()
    else:
        raise ValueError(f"Unknown provider: {provider}. Use 'openai', 'anthropic', or 'mock'")
