"""LLM Provider - Unified interface for OpenAI, Anthropic, and local models.

This module provides:
- OpenAI integration (GPT-4, GPT-3.5)
- Anthropic integration (Claude)
- Streaming support
- Function calling
- Vision support
"""

from __future__ import annotations

import asyncio
import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, AsyncGenerator, Callable, Optional

import aiohttp
import structlog

logger = structlog.get_logger(__name__)


class ModelProvider(Enum):
    """Supported LLM providers."""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"  # Local
    LMSTUDIO = "lmstudio"  # Local


@dataclass
class LLMConfig:
    """Configuration for LLM provider."""
    provider: ModelProvider = ModelProvider.OPENAI
    model: str = "gpt-4"
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    max_tokens: int = 4096
    temperature: float = 0.7
    timeout: float = 60.0
    streaming: bool = True
    
    # Rate limiting
    max_requests_per_minute: int = 60
    max_tokens_per_minute: int = 90000


@dataclass
class Message:
    """A chat message."""
    role: str  # "system", "user", "assistant", "tool"
    content: str
    name: Optional[str] = None
    tool_calls: Optional[list[dict[str, Any]]] = None
    tool_call_id: Optional[str] = None


@dataclass
class FunctionCall:
    """A function call from LLM."""
    name: str
    arguments: dict[str, Any]
    call_id: Optional[str] = None


@dataclass
class LLMResponse:
    """Response from LLM."""
    content: str
    model: str
    finish_reason: str
    usage: dict[str, int] = field(default_factory=lambda: {"prompt": 0, "completion": 0, "total": 0})
    function_call: Optional[FunctionCall] = None
    raw: Optional[dict[str, Any]] = None


@dataclass
class StreamChunk:
    """A streaming chunk."""
    content: str
    done: bool = False
    usage: Optional[dict[str, int]] = None


class BaseLLMProvider(ABC):
    """Abstract base for LLM providers."""
    
    def __init__(self, config: LLMConfig):
        self.config = config
    
    @abstractmethod
    async def generate(self, messages: list[Message], **kwargs) -> LLMResponse:
        """Generate a response."""
        pass
    
    @abstractmethod
    async def stream(self, messages: list[Message], **kwargs) -> AsyncGenerator[StreamChunk, None]:
        """Stream a response."""
        pass
    
    @abstractmethod
    async def count_tokens(self, text: str) -> int:
        """Count tokens in text."""
        pass


class OpenAIProvider(BaseLLMProvider):
    """OpenAI API provider."""
    
    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self.api_key = config.api_key or os.getenv("OPENAI_API_KEY")
        self.base_url = config.base_url or "https://api.openai.com/v1"
        
        if not self.api_key:
            logger.warning("OPENAI_API_KEY not set, using mock mode")
    
    def _get_headers(self) -> dict[str, str]:
        """Get request headers."""
        if not self.api_key:
            raise ValueError("API key is not set. Cannot create authorization headers.")
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
    
    async def generate(self, messages: list[Message], **kwargs) -> LLMResponse:
        """Generate response from OpenAI."""
        if not self.api_key:
            return self._mock_response(messages)
        
        url = f"{self.base_url}/chat/completions"
        headers = self._get_headers()
        
        payload = {
            "model": self.config.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "temperature": kwargs.get("temperature", self.config.temperature),
            "stream": False,
        }
        
        # Add function calling if provided
        if "functions" in kwargs:
            payload["functions"] = kwargs["functions"]
            payload["function_call"] = kwargs.get("function_call", "auto")
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers, timeout=self.config.timeout) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    logger.error(f"OpenAI API error: {error}")
                    raise Exception(f"OpenAI API error: {resp.status}")
                
                data = await resp.json()
                return self._parse_response(data)
    
    async def stream(self, messages: list[Message], **kwargs) -> AsyncGenerator[StreamChunk, None]:
        """Stream response from OpenAI."""
        if not self.api_key:
            # Mock streaming
            content = "This is a mock response from the local AI agent."
            for char in content:
                yield StreamChunk(content=char)
                await asyncio.sleep(0.01)
            yield StreamChunk(content="", done=True)
            return
        
        url = f"{self.base_url}/chat/completions"
        headers = self._get_headers()
        
        payload = {
            "model": self.config.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "temperature": kwargs.get("temperature", self.config.temperature),
            "stream": True,
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers, timeout=self.config.timeout) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    logger.error(f"OpenAI streaming error: {error}")
                    raise Exception(f"OpenAI streaming error: {resp.status}")
                
                async for line in resp.content:
                    line = line.decode().strip()
                    if not line or line == "data: [DONE]":
                        continue
                    
                    if line.startswith("data: "):
                        data = json.loads(line[6:])
                        delta = data.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")
                        
                        if content:
                            yield StreamChunk(content=content)
                        
                        if data.get("choices", [{}])[0].get("finish_reason"):
                            yield StreamChunk(content="", done=True)
    
    async def count_tokens(self, text: str) -> int:
        """Estimate token count (simplified)."""
        # Rough estimate: ~4 chars per token
        return len(text) // 4
    
    def _parse_response(self, data: dict[str, Any]) -> LLMResponse:
        """Parse OpenAI response."""
        choice = data["choices"][0]
        message = choice["message"]
        
        content = message.get("content", "")
        function_call = None
        
        if "function_call" in message:
            fc = message["function_call"]
            function_call = FunctionCall(
                name=fc["name"],
                arguments=json.loads(fc["arguments"]),
            )
        
        return LLMResponse(
            content=content,
            model=data.get("model", self.config.model),
            finish_reason=choice.get("finish_reason", "stop"),
            usage=data.get("usage", {}),
            function_call=function_call,
            raw=data,
        )
    
    def _mock_response(self, messages: list[Message]) -> LLMResponse:
        """Generate mock response for testing."""
        last_message = messages[-1].content if messages else ""
        
        content = f"Mock response to: {last_message[:100]}..."
        
        return LLMResponse(
            content=content,
            model="mock-model",
            finish_reason="stop",
            usage={"prompt": 100, "completion": 50, "total": 150},
        )


class AnthropicProvider(BaseLLMProvider):
    """Anthropic Claude API provider."""
    
    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self.api_key = config.api_key or os.getenv("ANTHROPIC_API_KEY")
        self.base_url = "https://api.anthropic.com/v1"
        
        if not self.api_key:
            logger.warning("ANTHROPIC_API_KEY not set")
    
    def _get_headers(self) -> dict[str, str]:
        """Get request headers."""
        return {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }
    
    async def generate(self, messages: list[Message], **kwargs) -> LLMResponse:
        """Generate response from Anthropic."""
        if not self.api_key:
            return self._mock_response(messages)
        
        url = f"{self.base_url}/messages"
        headers = self._get_headers()
        
        # Convert messages format
        system = ""
        chat_messages = []
        for m in messages:
            if m.role == "system":
                system = m.content
            else:
                chat_messages.append({
                    "role": m.role,
                    "content": m.content,
                })
        
        payload = {
            "model": self.config.model,
            "messages": chat_messages,
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "temperature": kwargs.get("temperature", self.config.temperature),
            "system": system,
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers, timeout=self.config.timeout) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    logger.error(f"Anthropic API error: {error}")
                    raise Exception(f"Anthropic API error: {resp.status}")
                
                data = await resp.json()
                return LLMResponse(
                    content=data.get("content", [{}])[0].get("text", ""),
                    model=data.get("model", self.config.model),
                    finish_reason=data.get("stop_reason", "stop"),
                    usage=data.get("usage", {}),
                    raw=data,
                )
    
    async def stream(self, messages: list[Message], **kwargs) -> AsyncGenerator[StreamChunk, None]:
        """Stream response from Anthropic."""
        # Anthropic streaming implementation
        yield StreamChunk(content="Anthropic streaming not yet implemented", done=True)
    
    async def count_tokens(self, text: str) -> int:
        """Estimate token count."""
        return len(text) // 4
    
    def _mock_response(self, messages: list[Message]) -> LLMResponse:
        """Generate mock response."""
        return LLMResponse(
            content="Claude mock response",
            model="claude-mock",
            finish_reason="stop",
        )


class OllamaProvider(BaseLLMProvider):
    """Ollama local LLM provider."""
    
    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self.base_url = config.base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    
    async def generate(self, messages: list[Message], **kwargs) -> LLMResponse:
        """Generate from Ollama."""
        url = f"{self.base_url}/api/chat"
        
        payload = {
            "model": self.config.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=self.config.timeout) as resp:
                data = await resp.json()
                return LLMResponse(
                    content=data.get("message", {}).get("content", ""),
                    model=data.get("model", self.config.model),
                    finish_reason="stop",
                )
    
    async def stream(self, messages: list[Message], **kwargs) -> AsyncGenerator[StreamChunk, None]:
        """Stream from Ollama."""
        url = f"{self.base_url}/api/chat"
        
        payload = {
            "model": self.config.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": True,
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=self.config.timeout) as resp:
                async for line in resp.content:
                    data = json.loads(line)
                    content = data.get("message", {}).get("content", "")
                    if content:
                        yield StreamChunk(content=content)
                    if data.get("done"):
                        yield StreamChunk(content="", done=True)
    
    async def count_tokens(self, text: str) -> int:
        """Estimate tokens."""
        return len(text) // 4


class LLMManager:
    """
    Unified LLM manager supporting multiple providers.
    
    Usage:
        # OpenAI
        manager = LLMManager(provider="openai", model="gpt-4")
        response = await manager.generate("Hello!")
        
        # Anthropic
        manager = LLMManager(provider="anthropic", model="claude-3-opus")
        response = await manager.generate("Hello!")
        
        # Ollama (local)
        manager = LLMManager(provider="ollama", model="llama2")
        response = await manager.generate("Hello!")
        
        # Stream
        async for chunk in manager.stream("Hello!"):
            print(chunk.content, end="")
    """
    
    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or LLMConfig()
        self._provider: Optional[BaseLLMProvider] = None
        self._init_provider()
    
    def _init_provider(self) -> None:
        """Initialize the provider based on config."""
        if self.config.provider == ModelProvider.OPENAI:
            self._provider = OpenAIProvider(self.config)
        elif self.config.provider == ModelProvider.ANTHROPIC:
            self._provider = AnthropicProvider(self.config)
        elif self.config.provider == ModelProvider.OLLAMA:
            self._provider = OllamaProvider(self.config)
        else:
            raise ValueError(f"Unknown provider: {self.config.provider}")
    
    def switch_provider(self, provider: ModelProvider, **kwargs) -> None:
        """Switch to a different provider."""
        self.config.provider = provider
        for key, value in kwargs.items():
            setattr(self.config, key, value)
        self._init_provider()
    
    async def generate(
        self,
        prompt: str,
        system: str = "",
        **kwargs,
    ) -> LLMResponse:
        """Generate a response."""
        messages = []
        if system:
            messages.append(Message(role="system", content=system))
        messages.append(Message(role="user", content=prompt))
        
        return await self._provider.generate(messages, **kwargs)
    
    async def chat(
        self,
        messages: list[Message],
        **kwargs,
    ) -> LLMResponse:
        """Chat with messages."""
        return await self._provider.generate(messages, **kwargs)
    
    async def stream(
        self,
        prompt: str,
        system: str = "",
        **kwargs,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Stream a response."""
        messages = []
        if system:
            messages.append(Message(role="system", content=system))
        messages.append(Message(role="user", content=prompt))
        
        async for chunk in self._provider.stream(messages, **kwargs):
            yield chunk
    
    async def count_tokens(self, text: str) -> int:
        """Count tokens."""
        return await self._provider.count_tokens(text)
    
    async def embed(self, text: str) -> list[float]:
        """Get embeddings (OpenAI only)."""
        if self.config.provider != ModelProvider.OPENAI:
            raise NotImplementedError("Embeddings only supported for OpenAI")
        if not self.config.api_key:
            raise ValueError("API key is not set. Cannot generate embeddings.")

        url = "https://api.openai.com/v1/embeddings"
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "text-embedding-ada-002",
            "input": text,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                data = await resp.json()
                return data["data"][0]["embedding"]


# Global instance
_llm_manager: Optional[LLMManager] = None


def get_llm_manager() -> LLMManager:
    """Get global LLM manager."""
    global _llm_manager
    if _llm_manager is None:
        _llm_manager = LLMManager()
    return _llm_manager


def create_llm_manager(
    provider: str = "openai",
    model: str = "gpt-4",
    api_key: Optional[str] = None,
    **kwargs,
) -> LLMManager:
    """Create a new LLM manager."""
    config = LLMConfig(
        provider=ModelProvider(provider),
        model=model,
        api_key=api_key,
        **kwargs,
    )
    return LLMManager(config)



if __name__ == "__main__":
    async def demo():
        print("LLM Manager Demo")
        print("=" * 40)
        
        # Test OpenAI (will use mock if no API key)
        manager = create_llm_manager("openai", "gpt-4")
        
        print(f"Provider: {manager.config.provider.value}")
        print(f"Model: {manager.config.model}")
        print()
        
        # Generate
        response = await manager.generate(
            "What is the capital of Vietnam?",
            system="You are a helpful assistant."
        )
        print(f"Response: {response.content}")
        print(f"Model: {response.model}")
        print(f"Usage: {response.usage}")
        print()
        
        # Stream (mock)
        print("Streaming:")
        async for chunk in manager.stream("Count to 5"):
            if chunk.content:
                print(chunk.content, end="", flush=True)
        print()
    
    asyncio.run(demo())
