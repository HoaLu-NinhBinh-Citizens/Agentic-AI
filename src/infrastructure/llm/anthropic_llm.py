"""
Anthropic Claude LLM adapter for src.

Ported from Hermes Agent's multi-provider pattern.
Supports Claude-3.5 Sonnet, Claude-3 Opus, and other Claude models.
No extra SDK required — uses the Anthropic HTTP API directly via requests,
consistent with the existing Ollama and OpenAI adapters.
"""

import asyncio
import logging
import os
import time
from typing import AsyncIterator, Callable, Optional

import requests

from .base import BaseLLM
from .streaming import TokenAccumulator, StreamProgressCallback

logger = logging.getLogger(__name__)

_ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
_ANTHROPIC_API_VERSION = "2023-06-01"
_DEFAULT_MODEL = "claude-sonnet-4-5"


class AnthropicLLM(BaseLLM):
    """Anthropic Claude adapter following the same interface as OllamaLLM / OpenAILLM.

    Configuration priority (high → low):
    1. Constructor args
    2. Environment variables: ``ANTHROPIC_API_KEY``, ``ANTHROPIC_MODEL``
    3. Hardcoded defaults
    """

    def __init__(
        self,
        model: str = "",
        api_key: str = "",
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ):
        self.model = model or os.environ.get("ANTHROPIC_MODEL", _DEFAULT_MODEL)
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.connect_timeout_seconds = 15
        self.read_timeout_seconds = int(os.environ.get("ANTHROPIC_READ_TIMEOUT", "120") or 120)
        self.max_retries = 2

    @property
    def is_configured(self) -> bool:
        """True when an API key is available."""
        return bool(self.api_key)

    # ------------------------------------------------------------------
    # Public interface (mirrors OllamaLLM / OpenAILLM)
    # ------------------------------------------------------------------

    async def generate(self, prompt: str, stream: bool = False) -> str:
        """Generate text from Claude.  Returns the full response as a string."""
        if stream:
            return await self._stream_generate_async(prompt)
        return await asyncio.to_thread(self._generate_sync, prompt)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _headers(self) -> dict:
        return {
            "x-api-key": self.api_key,
            "anthropic-version": _ANTHROPIC_API_VERSION,
            "content-type": "application/json",
        }

    def _payload(self, prompt: str, stream: bool = False) -> dict:
        return {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "messages": [{"role": "user", "content": prompt}],
            "stream": stream,
        }

    def _select_read_timeout(self, prompt_chars: int) -> int:
        dynamic = 120 + int(prompt_chars / 50)
        return min(max(self.read_timeout_seconds, dynamic), 300)

    def _generate_sync(self, prompt: str) -> str:
        """Blocking REST call to the Anthropic Messages API."""
        prompt_chars = len(prompt)
        logger.info(
            "Anthropic LLM: Generating... model=%s prompt_chars=%d max_tokens=%d",
            self.model,
            prompt_chars,
            self.max_tokens,
        )
        last_error: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):
            started = time.perf_counter()
            try:
                response = requests.post(
                    _ANTHROPIC_API_URL,
                    headers=self._headers(),
                    json=self._payload(prompt),
                    timeout=(self.connect_timeout_seconds, self._select_read_timeout(prompt_chars)),
                )
                response.raise_for_status()
                data = response.json()
                # Anthropic response: {"content": [{"type": "text", "text": "..."}], ...}
                content_blocks = data.get("content", [])
                text = "".join(
                    block.get("text", "")
                    for block in content_blocks
                    if block.get("type") == "text"
                )
                elapsed = time.perf_counter() - started
                logger.info(
                    "Anthropic LLM: Response received in %.1fs response_chars=%d attempt=%d/%d",
                    elapsed,
                    len(text),
                    attempt,
                    self.max_retries,
                )
                if not text.strip():
                    raise ValueError("Anthropic returned an empty response")
                return text

            except requests.exceptions.Timeout as exc:
                elapsed = time.perf_counter() - started
                logger.warning(
                    "Anthropic LLM timeout after %.1fs attempt=%d/%d",
                    elapsed, attempt, self.max_retries,
                )
                last_error = exc

            except requests.exceptions.ConnectionError as exc:
                logger.error("Anthropic LLM: Cannot reach %s", _ANTHROPIC_API_URL)
                last_error = exc
                break

            except requests.exceptions.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else 0
                if status == 401:
                    logger.error("Anthropic LLM auth error: Invalid API key")
                elif status == 429:
                    logger.error("Anthropic LLM: Rate limit hit")
                elif status == 529:
                    logger.error("Anthropic LLM: API overloaded")
                else:
                    logger.error("Anthropic LLM HTTP error %s: %s", status, exc)
                last_error = exc
                break

            except Exception as exc:
                elapsed = time.perf_counter() - started
                logger.error(
                    "Anthropic LLM error after %.1fs attempt=%d/%d: %s",
                    elapsed, attempt, self.max_retries, exc,
                )
                last_error = exc
                break

        if last_error is None:
            raise RuntimeError("Anthropic generation failed without a captured exception")
        raise last_error

    async def stream_generate(
        self,
        prompt: str,
        on_token: Optional[Callable[[str], None]] = None,
        progress_callback: Optional[StreamProgressCallback] = None,
    ) -> AsyncIterator[str]:
        """Async streaming generator using Anthropic SSE."""
        try:
            import aiohttp
        except ImportError:
            logger.warning("aiohttp not installed; falling back to non-streaming")
            result = await asyncio.to_thread(self._generate_sync, prompt)
            yield result
            return

        logger.info(
            "Anthropic LLM: Streaming... model=%s prompt_chars=%d",
            self.model, len(prompt),
        )

        timeout = aiohttp.ClientTimeout(total=self._select_read_timeout(len(prompt)), connect=15)
        headers = self._headers()
        payload = self._payload(prompt, stream=True)

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(_ANTHROPIC_API_URL, headers=headers, json=payload) as resp:
                    resp.raise_for_status()
                    async for raw_line in resp.content:
                        line = raw_line.decode("utf-8", errors="replace").strip()
                        if not line or not line.startswith("data:"):
                            continue
                        data_str = line[5:].strip()
                        if data_str == "[DONE]" or not data_str:
                            continue
                        try:
                            import json as _json
                            chunk = _json.loads(data_str)
                        except Exception:
                            continue
                        # Anthropic streaming event types
                        if chunk.get("type") == "content_block_delta":
                            token = chunk.get("delta", {}).get("text", "")
                        elif chunk.get("type") == "message_delta":
                            # stop_reason etc — skip
                            continue
                        else:
                            continue
                        if not token:
                            continue
                        if on_token:
                            try:
                                on_token(token)
                            except Exception:
                                pass
                        if progress_callback:
                            await progress_callback(token)
                        yield token
        except Exception as exc:
            logger.error("Anthropic LLM stream error: %s", exc)
            raise

    async def _stream_generate_async(self, prompt: str) -> str:
        accumulator = TokenAccumulator()
        await accumulator.consume(self.stream_generate(prompt))
        return accumulator.text
