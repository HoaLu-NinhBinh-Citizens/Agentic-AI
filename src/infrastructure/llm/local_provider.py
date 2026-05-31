"""Local LLM provider using Ollama or llama.cpp server.

Enables offline AI_SUPPORT operation with local models.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, AsyncIterator, Optional

import httpx

logger = logging.getLogger(__name__)


# Alias for compatibility with __init__.py exports
LLMConfig = None  # Will be set after class definition


@dataclass
class LocalModelInfo:
    """Information about a local model.

    Attributes:
        name: Model name
        size: Model size in bytes
        modified_at: Last modification timestamp
        digest: Model digest
    """
    name: str
    size: int = 0
    modified_at: Optional[str] = None
    digest: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LocalModelInfo":
        """Create from Ollama API response dict."""
        return cls(
            name=data.get("name", "unknown"),
            size=data.get("size", 0),
            modified_at=data.get("modified_at"),
            digest=data.get("digest"),
        )


@dataclass
class _LocalLLMConfig:
    """Configuration for local LLM provider.

    Attributes:
        base_url: Base URL for the local LLM server (default: Ollama at localhost:11434)
        model: Default model name (default: llama3.2)
        api_key: Optional API key for authenticated servers
        timeout: Request timeout in seconds
        max_tokens: Maximum tokens to generate
        temperature: Sampling temperature (0.0-2.0)
    """
    base_url: str = "http://localhost:11434"
    model: str = "llama3.2"
    api_key: Optional[str] = None
    timeout: int = 120
    max_tokens: int = 4096
    temperature: float = 0.7


# Public alias
LocalLLMConfig = _LocalLLMConfig


@dataclass
class LocalLLMResponse:
    """Response from local LLM provider.

    Attributes:
        content: Generated text content
        model: Model identifier used
        prompt_tokens: Number of tokens in the prompt
        completion_tokens: Number of tokens generated
        total_tokens: Total tokens used
        finish_reason: Why generation stopped (stop, length, etc.)
    """
    content: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    finish_reason: str = "stop"

    @property
    def tokens_used(self) -> int:
        """Alias for total_tokens for compatibility."""
        return self.total_tokens


@dataclass
class LocalLLMChunk:
    """A chunk in a streaming response.

    Attributes:
        content: Text content of the chunk
        is_final: Whether this is the final chunk
    """
    content: str
    is_final: bool = False


@dataclass
class LocalLLMTool:
    """Tool definition for function calling.

    Attributes:
        name: Tool name
        description: Tool description
        parameters: JSON Schema for parameters
    """
    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)


class LocalLLMProvider:
    """Local LLM provider supporting Ollama and llama.cpp-compatible APIs.

    This provider enables offline operation by connecting to locally running
    LLM servers like Ollama or llama.cpp server.

    Features:
    - Non-streaming and streaming completion
    - Function/tool calling support (Ollama format)
    - Configurable timeouts and parameters
    - Health checking
    """

    def __init__(self, config: Optional[LocalLLMConfig] = None) -> None:
        """Initialize the local LLM provider.

        Args:
            config: Optional configuration. Uses defaults if not provided.
        """
        self.config = config or LocalLLMConfig()
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def provider_name(self) -> str:
        """Return the provider name for logging."""
        return f"local:{self.config.model}"

    @property
    def name(self) -> str:
        """Return the provider name (alias for compatibility)."""
        return self.provider_name

    def is_available(self) -> bool:
        """Check if the provider is configured."""
        return True

    async def initialize(self) -> None:
        """Initialize HTTP client and check connection."""
        self._client = httpx.AsyncClient(
            base_url=self.config.base_url,
            timeout=self.config.timeout,
            headers=_build_headers(self.config.api_key),
        )
        try:
            response = await self._client.get("/api/tags")
            if response.status_code == 200:
                data = response.json()
                models = data.get("models", [])
                model_names = [m.get("name", "unknown") for m in models]
                logger.info(
                    "Local LLM connected to %s. Available models: %s",
                    self.config.base_url,
                    model_names,
                )
            else:
                logger.warning(
                    "Local LLM returned unexpected status: %s",
                    response.status_code,
                )
        except httpx.ConnectError:
            logger.warning(
                "Local LLM not available at %s. Start with: ollama serve",
                self.config.base_url,
            )
        except Exception as e:
            logger.error("Error connecting to local LLM: %s", e)

    async def complete(
        self,
        messages: list[dict[str, str]],
        tools: Optional[list[LocalLLMTool]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> LocalLLMResponse:
        """Send completion request to local LLM.

        Args:
            messages: List of message dicts with 'role' and 'content'
            tools: Optional list of tool definitions
            temperature: Sampling temperature override
            max_tokens: Maximum tokens override
            **kwargs: Additional parameters

        Returns:
            LocalLLMResponse with generated content

        Raises:
            RuntimeError: If the request fails
        """
        if not self._client:
            await self.initialize()

        payload = self._build_payload(
            messages,
            tools=tools,
            stream=False,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

        try:
            response = await self._client.post("/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()

            content = data.get("message", {}).get("content", "")

            return LocalLLMResponse(
                content=content,
                model=self.config.model,
                prompt_tokens=data.get("prompt_eval_count", 0),
                completion_tokens=data.get("eval_count", 0),
                total_tokens=data.get("prompt_eval_count", 0) + data.get("eval_count", 0),
                finish_reason=data.get("done_reason", "stop"),
            )
        except httpx.HTTPStatusError as e:
            logger.error(
                "Local LLM HTTP error: %s - %s",
                e.response.status_code,
                e.response.text,
            )
            raise RuntimeError(f"Local LLM request failed: {e.response.status_code}") from e
        except Exception as e:
            logger.error("Local LLM error: %s", e)
            raise RuntimeError(f"Local LLM request failed: {e}") from e

    async def stream(
        self,
        messages: list[dict[str, str]],
        tools: Optional[list[LocalLLMTool]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> AsyncIterator[LocalLLMChunk]:
        """Stream completion from local LLM.

        Args:
            messages: List of message dicts with 'role' and 'content'
            tools: Optional list of tool definitions
            temperature: Sampling temperature override
            max_tokens: Maximum tokens override
            **kwargs: Additional parameters

        Yields:
            LocalLLMChunk objects representing the response
        """
        if not self._client:
            await self.initialize()

        payload = self._build_payload(
            messages,
            tools=tools,
            stream=True,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

        try:
            async with self._client.stream("POST", "/api/chat", json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        content = data.get("message", {}).get("content", "")
                        is_final = data.get("done", False)

                        if content or is_final:
                            yield LocalLLMChunk(content=content, is_final=is_final)
                    except json.JSONDecodeError:
                        logger.warning("Failed to parse streaming response: %s", line)
                        continue
        except Exception as e:
            logger.error("Local LLM streaming error: %s", e)
            raise RuntimeError(f"Local LLM streaming failed: {e}") from e

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncIterator[Any]:
        """Stream chat completion with tool call support (provider.py interface).

        This method provides compatibility with the LLMProvider interface
        from src/infrastructure/llm/provider.py.

        Args:
            messages: List of message dicts with 'role' and 'content'
            tools: Optional list of tool definitions
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate

        Yields:
            StreamEvent objects representing the response
        """
        from src.infrastructure.llm.provider import StreamEvent, StreamEventType

        # Convert tools to LocalLLMTool format
        local_tools: list[LocalLLMTool] | None = None
        if tools:
            local_tools = [
                LocalLLMTool(
                    name=t.get("name", t.get("function", {}).get("name", "")),
                    description=t.get("description", t.get("function", {}).get("description", "")),
                    parameters=t.get("parameters", t.get("function", {}).get("parameters", {})),
                )
                for t in tools
            ]

        async for chunk in self.stream(
            messages,
            tools=local_tools,
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            if chunk.content:
                yield StreamEvent.token(chunk.content)
            if chunk.is_final:
                yield StreamEvent.done("stop")

    def _build_payload(
        self,
        messages: list[dict[str, str]],
        tools: list[LocalLLMTool] | None = None,
        stream: bool = False,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Build request payload for Ollama API.

        Args:
            messages: List of message dicts
            tools: Optional list of tools
            stream: Whether to stream the response
            temperature: Temperature setting
            max_tokens: Maximum tokens setting
            **kwargs: Additional options

        Returns:
            Request payload dict
        """
        ollama_messages = []
        for msg in messages:
            role = msg.get("role", "user")
            if role == "system":
                role = "system"
            elif role == "assistant":
                role = "assistant"
            else:
                role = "user"

            ollama_messages.append({
                "role": role,
                "content": msg.get("content", ""),
            })

        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": ollama_messages,
            "stream": stream,
            "options": {
                "temperature": temperature if temperature is not None else self.config.temperature,
                "num_predict": max_tokens if max_tokens is not None else self.config.max_tokens,
            },
        }

        # Handle tools if provided
        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                    }
                }
                for tool in tools
            ]

        return payload

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> LocalLLMResponse:
        """Generate response (adapters.py interface compatibility).

        Args:
            prompt: User prompt
            system_prompt: Optional system instructions
            temperature: Sampling temperature
            max_tokens: Maximum response tokens

        Returns:
            LocalLLMResponse with generated content
        """
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        return await self.complete(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    async def health_check(self) -> bool:
        """Check if local LLM is available.

        Returns:
            True if the server responds successfully
        """
        if not self._client:
            await self.initialize()

        if not self._client:
            return False

        try:
            response = await self._client.get("/api/tags")
            return response.status_code == 200
        except Exception:
            return False

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    def __repr__(self) -> str:
        return f"LocalLLMProvider(model={self.config.model}, url={self.config.base_url})"


def _build_headers(api_key: Optional[str]) -> dict[str, str]:
    """Build HTTP headers for the request.

    Args:
        api_key: Optional API key

    Returns:
        Headers dict
    """
    headers: dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


async def create_local_provider(
    base_url: Optional[str] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
) -> LocalLLMProvider:
    """Create and initialize a local LLM provider.

    Args:
        base_url: Optional server URL override
        model: Optional model override
        api_key: Optional API key

    Returns:
        Initialized LocalLLMProvider
    """
    config = _LocalLLMConfig(
        base_url=base_url or "http://localhost:11434",
        model=model or "llama3.2",
        api_key=api_key,
    )
    provider = LocalLLMProvider(config)
    await provider.initialize()
    return provider


# Alias for __init__.py compatibility
LocalLLMConfig = _LocalLLMConfig  # type: ignore[misc, assignment]
