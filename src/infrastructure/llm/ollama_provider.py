"""Ollama provider implementation with streaming and tool call support."""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator

import httpx

from .provider import LLMProvider, StreamEvent
from .tool_accumulator import ToolCallAccumulator

logger = logging.getLogger(__name__)


class OllamaProvider(LLMProvider):
    """Ollama provider for local LLM inference.

    Supports streaming responses and tool calling with qwen2.5-coder models.
    """

    def __init__(
        self,
        name: str = "ollama",
        base_url: str = "http://localhost:11434",
        model: str = "qwen2.5-coder:7b",
        temperature: float = 0.1,
        max_tokens: int = 4096,
        timeout: float = 120.0,
        config: LLMProviderConfig | None = None,
    ) -> None:
        """Initialize Ollama provider.

        Args:
            name: Provider identifier.
            base_url: Ollama server URL.
            model: Model name to use.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens to generate.
            timeout: Request timeout in seconds (DEPRECATED: use config instead).
            config: Provider configuration with timeouts.
        """
        # Use config or create one from timeout
        if config is None:
            config = LLMProviderConfig(
                connect_timeout=min(15.0, timeout / 4),
                read_timeout=timeout,
                total_timeout=timeout * 1.5,
            )
        super().__init__(name, config)
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client with timeout configuration."""
        if self._client is None:
            # FIX: Use configurable timeouts from LLMProviderConfig
            connect_timeout, read_timeout = self.get_timeout()
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(
                    connect=connect_timeout,
                    read=read_timeout,
                    write=30.0,
                    pool=60.0,
                )
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def health_check(self) -> bool:
        """Check if Ollama server is available.

        Returns:
            True if server is healthy.
        """
        try:
            client = self._get_client()
            response = await client.get(f"{self._base_url}/api/tags")
            return response.status_code == 200
        except Exception as e:
            logger.warning("Ollama health check failed: %s", str(e))
            return False

    async def list_models(self) -> list[dict[str, Any]]:
        """List available models.

        Returns:
            List of model information dicts.
        """
        try:
            client = self._get_client()
            response = await client.get(f"{self._base_url}/api/tags")
            if response.status_code == 200:
                data = response.json()
                return data.get("models", [])
            return []
        except Exception as e:
            logger.error("Failed to list models: %s", str(e))
            return []

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Stream chat completion from Ollama.

        Args:
            messages: List of message dicts.
            tools: Optional list of tool definitions.
            temperature: Override default temperature.
            max_tokens: Override default max tokens.

        Yields:
            StreamEvent objects.
        """
        temp = temperature if temperature is not None else self._temperature
        maxt = max_tokens if max_tokens is not None else self._max_tokens

        request_body: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "stream": True,
            "temperature": temp,
            "options": {
                "num_predict": maxt,
            },
        }

        if tools:
            request_body["tools"] = tools

        try:
            client = self._get_client()
            async with client.stream(
                "POST",
                f"{self._base_url}/api/chat",
                json=request_body,
            ) as response:
                if response.status_code != 200:
                    yield StreamEvent.error(
                        "HTTP_ERROR",
                        f"Ollama returned status {response.status_code}",
                    )
                    return

                buffer = ""
                tool_accumulator = ToolCallAccumulator()

                async for line in response.aiter_lines():
                    if not line.strip():
                        continue

                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    message = chunk.get("message", {})
                    content = message.get("content", "")

                    if content:
                        yield StreamEvent.token(content)

                    tool_calls = chunk.get("tool_calls", [])
                    for tc in tool_calls:
                        func = tc.get("function", {})
                        yield StreamEvent.tool_call_start(
                            index=tc.get("index", 0),
                            call_id=tc.get("id", f"call_{tc.get('index', 0)}"),
                            function_name=func.get("name", ""),
                        )
                        args_str = json.dumps(func.get("arguments", {}))
                        yield StreamEvent.tool_call_delta(
                            index=tc.get("index", 0),
                            call_id=tc.get("id", ""),
                            function_name=func.get("name", ""),
                            arguments=args_str,
                        )

                    done = chunk.get("done", False)
                    if done:
                        finish_reason = chunk.get("done_reason", "stop")
                        completion_tokens = chunk.get("eval_count", 0)
                        yield StreamEvent.done(
                            finish_reason=finish_reason,
                            completion_tokens=completion_tokens,
                        )
                        break

        except httpx.TimeoutException as e:
            logger.error("Ollama request timed out: %s", str(e))
            yield StreamEvent.error("TIMEOUT", f"Request timed out: {str(e)}")
        except httpx.ConnectError as e:
            logger.error("Ollama connection failed: %s", str(e))
            yield StreamEvent.error("CONNECTION_ERROR", f"Connection failed: {str(e)}")
        except Exception as e:
            logger.error("Ollama stream error: %s", str(e))
            yield StreamEvent.error("STREAM_ERROR", str(e))

    def supports_tools(self) -> bool:
        """Check if Ollama supports tool calling.

        Note: Tool calling support depends on model and Ollama version.
        """
        return True

    def supports_streaming(self) -> bool:
        """Ollama supports streaming."""
        return True
