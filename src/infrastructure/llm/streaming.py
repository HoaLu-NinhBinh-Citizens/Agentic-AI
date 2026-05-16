"""
Async streaming utilities for LLM responses.

Provides:
- SSE (Server-Sent Events) parsing for Ollama
- Async token iterator for real-time response streaming
- Token tracking during streaming
- Fallback to non-streaming when SSE is unavailable
"""

import asyncio
import json
import logging
import re
import time
from typing import AsyncIterator, Callable, Optional

logger = logging.getLogger(__name__)


async def stream_ollama_sse(
    url: str,
    json_payload: dict,
    timeout_seconds: int = 120,
) -> AsyncIterator[str]:
    """
    Stream tokens from Ollama using SSE (Server-Sent Events).

    Yields individual tokens as they arrive from the server.
    Falls back to empty iterator on connection errors.
    """
    try:
        import aiohttp
    except ImportError:
        logger.warning("aiohttp not installed, streaming unavailable for Ollama")
        return

    connect_timeout = min(timeout_seconds, 30)
    read_timeout = timeout_seconds

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(
            total=timeout_seconds,
            connect=connect_timeout,
        )) as session:
            async with session.post(
                f"{url}/api/generate",
                json=json_payload,
                headers={"Content-Type": "application/json"},
            ) as response:
                response.raise_for_status()
                async for line in response.content:
                    if not line:
                        continue
                    decoded = line.decode("utf-8", errors="replace").strip()
                    if not decoded:
                        continue
                    # Ollama SSE format: data: {"response":"...", "done":false}\n\n
                    if decoded.startswith("data:"):
                        data_str = decoded[5:].strip()
                        try:
                            data = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue
                        token = str(data.get("response", ""))
                        if token:
                            yield token
                        if data.get("done", False):
                            break
    except asyncio.TimeoutError:
        logger.warning("Ollama SSE stream timed out after %ds", timeout_seconds)
    except aiohttp.ClientError as exc:
        logger.warning("Ollama SSE stream connection error: %s", exc)
    except Exception as exc:
        logger.warning("Ollama SSE stream error: %s", exc)


async def stream_openai_sse(
    url: str,
    headers: dict,
    json_payload: dict,
    timeout_seconds: int = 120,
) -> AsyncIterator[str]:
    """
    Stream tokens from OpenAI-compatible API using SSE.

    Yields individual tokens as they arrive from the server.
    """
    try:
        import aiohttp
    except ImportError:
        logger.warning("aiohttp not installed, streaming unavailable for OpenAI")
        return

    connect_timeout = min(timeout_seconds, 30)

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(
            total=timeout_seconds,
            connect=connect_timeout,
        )) as session:
            async with session.post(
                url,
                json=json_payload,
                headers=headers,
            ) as response:
                response.raise_for_status()
                async for line in response.content:
                    if not line:
                        continue
                    decoded = line.decode("utf-8", errors="replace").strip()
                    if not decoded:
                        continue
                    # OpenAI SSE format: data: {"choices":[{"delta":{"content":"..."}}]}\n\n
                    # or: data: [DONE]\n\n
                    if decoded.startswith("data:"):
                        data_str = decoded[5:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue
                        choices = data.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})
                            token = str(delta.get("content", ""))
                            if token:
                                yield token
    except asyncio.TimeoutError:
        logger.warning("OpenAI SSE stream timed out after %ds", timeout_seconds)
    except aiohttp.ClientError as exc:
        logger.warning("OpenAI SSE stream connection error: %s", exc)
    except Exception as exc:
        logger.warning("OpenAI SSE stream error: %s", exc)


class StreamingResponse:
    """Wrapper that provides both streaming and non-streaming access to LLM output."""

    def __init__(
        self,
        text: str = "",
        tokens_stream: Optional[AsyncIterator[str]] = None,
        model: str = "",
        token_count: int = 0,
    ):
        self._text = text
        self._tokens_stream = tokens_stream
        self._model = model
        self._token_count = token_count
        self._cached = False

    async def get_text(self) -> str:
        """Get the full text, consuming the stream if needed."""
        if self._cached:
            return self._text
        if self._tokens_stream:
            parts = []
            async for token in self._tokens_stream:
                parts.append(token)
            self._text = "".join(parts)
            self._cached = True
        return self._text

    def iter_tokens(self) -> Optional[AsyncIterator[str]]:
        """Return the token stream for real-time output."""
        return self._tokens_stream

    @property
    def token_count(self) -> int:
        return self._token_count

    @property
    def model(self) -> str:
        return self._model

    def __repr__(self) -> str:
        preview = self._text[:100] if self._text else "(stream pending)"
        return f"StreamingResponse(text={preview!r}..., tokens={self._token_count})"


class TokenAccumulator:
    """Accumulates streamed tokens and tracks token count."""

    def __init__(self):
        self._parts: list[str] = []
        self._token_count = 0
        self._char_count = 0
        self._start_time = time.perf_counter()

    async def consume(self, stream: AsyncIterator[str]) -> str:
        """Consume an async token stream and accumulate all tokens."""
        async for token in stream:
            self._parts.append(token)
            self._token_count += 1
            self._char_count += len(token)
        return "".join(self._parts)

    def consume_sync(self, text: str):
        """Consume a synchronous text response."""
        self._parts = [text]
        self._token_count = max(1, len(text) // 4)
        self._char_count = len(text)

    @property
    def text(self) -> str:
        return "".join(self._parts)

    @property
    def token_count(self) -> int:
        return self._token_count

    @property
    def char_count(self) -> int:
        return self._char_count

    @property
    def elapsed(self) -> float:
        return time.perf_counter() - self._start_time

    @property
    def tokens_per_second(self) -> float:
        elapsed = self.elapsed
        if elapsed <= 0:
            return 0.0
        return self._token_count / elapsed


class StreamProgressCallback:
    """
    Callback that prints streamed tokens with progress info.

    Integrates with tqdm for progress bar display.
    """

    def __init__(
        self,
        prefix: str = "",
        show_progress: bool = False,
        print_fn: Optional[Callable[[str], None]] = None,
    ):
        self.prefix = prefix
        self.show_progress = show_progress
        self._print_fn = print_fn or (lambda s: print(s, end="", flush=True))
        self._tokens = 0
        self._start_time = time.perf_counter()
        self._buffer = ""
        self._last_flush = 0
        self._flush_interval = 0.1  # seconds

    async def __call__(self, token: str) -> None:
        """Called for each streamed token."""
        self._tokens += 1
        self._buffer += token

        # Flush every ~100ms to avoid excessive I/O
        now = time.perf_counter()
        should_flush = (
            now - self._last_flush > self._flush_interval
            or token in {".", "\n", " ", ":\n"}
        )
        if should_flush and self._buffer:
            self._print_fn(self._buffer)
            self._buffer = ""
            self._last_flush = now

    def flush(self):
        """Flush any remaining buffered tokens."""
        if self._buffer:
            self._print_fn(self._buffer)
            self._buffer = ""

    async def finish(self) -> dict:
        """Finalize and return stats."""
        self.flush()
        elapsed = time.perf_counter() - self._start_time
        stats = {
            "tokens": self._tokens,
            "elapsed_s": round(elapsed, 2),
            "tps": round(self._tokens / elapsed, 1) if elapsed > 0 else 0,
        }
        if self.show_progress:
            print()  # newline after progress
        return stats


def estimate_tokens_sync(text: str) -> int:
    """
    Fast synchronous token estimate without tiktoken.

    Used when async/aiohttp are not available.
    """
    if not text:
        return 0
    words = text.split()
    code_tokens = len(re.findall(r"[(){}\[\];:,=<>+\-*/&|!@#$%^]", text))
    string_count = len(re.findall(r"['\"`].*?['\"`]", text, re.DOTALL))
    newline_count = text.count("\n")
    return max(1, int(
        len(words) * 0.25
        + code_tokens * 0.5
        + string_count * 0.125
        + newline_count * 0.25
    ))
