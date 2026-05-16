"""Groq provider implementation with streaming and tool call support.

Groq provides fast inference with a free tier. Uses OpenAI-compatible API.
"""

from __future__ import annotations

import logging
import os
from typing import Any, AsyncIterator

import httpx

from .provider import LLMProvider, StreamEvent
from .tool_accumulator import ToolCallAccumulator

logger = logging.getLogger(__name__)


class GroqProvider(LLMProvider):
    """Groq provider for fast cloud LLM inference.

    Uses OpenAI-compatible API with Groq's fast inference engine.
    """

    def __init__(
        self,
        name: str = "groq",
        api_key: str | None = None,
        api_key_env: str = "GROQ_API_KEY",
        model: str = "llama-3.3-70b-versatile",
        base_url: str = "https://api.groq.com/openai/v1",
        temperature: float = 0.1,
        max_tokens: int = 4096,
        timeout: float = 60.0,
    ) -> None:
        """Initialize Groq provider.

        Args:
            name: Provider identifier.
            api_key: Groq API key (or use api_key_env).
            api_key_env: Environment variable name for API key.
            model: Model name to use.
            base_url: API base URL.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens to generate.
            timeout: Request timeout in seconds.
        """
        super().__init__(name)
        self._api_key = api_key or os.getenv(api_key_env, "")
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    def _get_headers(self) -> dict[str, str]:
        """Get request headers with authentication."""
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    async def health_check(self) -> bool:
        """Check if Groq API is available.

        Returns:
            True if API is healthy.
        """
        if not self._api_key:
            logger.warning("Groq API key not configured")
            return False

        try:
            client = self._get_client()
            response = await client.get(
                f"{self._base_url}/models",
                headers=self._get_headers(),
            )
            return response.status_code == 200
        except Exception as e:
            logger.warning("Groq health check failed: %s", str(e))
            return False

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Stream chat completion from Groq.

        Args:
            messages: List of message dicts.
            tools: Optional list of tool definitions.
            temperature: Override default temperature.
            max_tokens: Override default max tokens.

        Yields:
            StreamEvent objects.
        """
        if not self._api_key:
            yield StreamEvent.error("AUTH_ERROR", "Groq API key not configured")
            return

        temp = temperature if temperature is not None else self._temperature
        maxt = max_tokens if max_tokens is not None else self._max_tokens

        request_body: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "stream": True,
            "temperature": temp,
            "max_tokens": maxt,
        }

        if tools:
            request_body["tools"] = tools
            request_body["tool_choice"] = "auto"

        try:
            client = self._get_client()
            async with client.stream(
                "POST",
                f"{self._base_url}/chat/completions",
                json=request_body,
                headers=self._get_headers(),
            ) as response:
                if response.status_code != 200:
                    error_text = await response.atext()
                    yield StreamEvent.error(
                        "HTTP_ERROR",
                        f"Groq returned status {response.status_code}: {error_text}",
                    )
                    return

                tool_accumulator = ToolCallAccumulator()

                async for line in response.aiter_lines():
                    if not line.strip() or not line.startswith("data: "):
                        continue

                    data = line[6:].strip()
                    if data == "[DONE]":
                        for tool_call in tool_accumulator.finalize():
                            pass
                        yield StreamEvent.done(finish_reason="stop")
                        return

                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue

                    choices = chunk.get("choices", [])
                    if not choices:
                        continue

                    choice = choices[0]
                    delta = choice.get("delta", {})

                    content = delta.get("content", "")
                    if content:
                        yield StreamEvent.token(content)

                    tool_calls = delta.get("tool_calls", [])
                    for tc in tool_calls:
                        idx = tc.get("index", 0)
                        func = tc.get("function", {})

                        if func.get("name"):
                            yield StreamEvent.tool_call_start(
                                index=idx,
                                call_id=tc.get("id", f"call_{idx}"),
                                function_name=func["name"],
                            )

                        args_str = func.get("arguments", "")
                        if args_str:
                            yield StreamEvent.tool_call_delta(
                                index=idx,
                                call_id=tc.get("id", ""),
                                function_name=func.get("name", ""),
                                arguments=args_str,
                            )

                    finish_reason = choice.get("finish_reason")
                    if finish_reason in ("stop", "tool_calls"):
                        usage = chunk.get("usage", {})
                        completion_tokens = usage.get("completion_tokens", 0)
                        yield StreamEvent.done(
                            finish_reason=finish_reason or "stop",
                            completion_tokens=completion_tokens,
                        )
                        return

        except httpx.TimeoutException as e:
            logger.error("Groq request timed out: %s", str(e))
            yield StreamEvent.error("TIMEOUT", f"Request timed out: {str(e)}")
        except httpx.ConnectError as e:
            logger.error("Groq connection failed: %s", str(e))
            yield StreamEvent.error("CONNECTION_ERROR", f"Connection failed: {str(e)}")
        except Exception as e:
            logger.error("Groq stream error: %s", str(e))
            yield StreamEvent.error("STREAM_ERROR", str(e))

    def supports_tools(self) -> bool:
        """Groq supports tool calling."""
        return True

    def supports_streaming(self) -> bool:
        """Groq supports streaming."""
        return True
