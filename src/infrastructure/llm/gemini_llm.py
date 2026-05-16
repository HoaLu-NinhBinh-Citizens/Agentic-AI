"""
Google Gemini LLM adapter for src.

Ported from Hermes Agent's multi-provider pattern.
Supports Gemini 2.0 Flash, Gemini 1.5 Pro, and other Gemini models.
Uses the Google Generative Language REST API directly — no SDK required.
"""

import asyncio
import json
import logging
import os
import time
from typing import AsyncIterator, Callable, Optional

import requests

from .base import BaseLLM
from .streaming import TokenAccumulator, StreamProgressCallback

logger = logging.getLogger(__name__)

_GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
_DEFAULT_MODEL = "gemini-2.0-flash"


class GeminiLLM(BaseLLM):
    """Google Gemini adapter following the same interface as OllamaLLM / OpenAILLM.

    Configuration priority (high → low):
    1. Constructor args
    2. Environment variables: ``GEMINI_API_KEY``, ``GEMINI_MODEL``
    3. Hardcoded defaults
    """

    def __init__(
        self,
        model: str = "",
        api_key: str = "",
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ):
        self.model = model or os.environ.get("GEMINI_MODEL", _DEFAULT_MODEL)
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.connect_timeout_seconds = 15
        self.read_timeout_seconds = int(os.environ.get("GEMINI_READ_TIMEOUT", "120") or 120)
        self.max_retries = 2

    @property
    def is_configured(self) -> bool:
        """True when an API key is available."""
        return bool(self.api_key)

    def _api_url(self, stream: bool = False) -> str:
        action = "streamGenerateContent" if stream else "generateContent"
        return f"{_GEMINI_API_BASE}/{self.model}:{action}?key={self.api_key}"

    def _payload(self, prompt: str) -> dict:
        return {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": self.temperature,
                "maxOutputTokens": self.max_tokens,
            },
        }

    def _select_read_timeout(self, prompt_chars: int) -> int:
        dynamic = 120 + int(prompt_chars / 50)
        return min(max(self.read_timeout_seconds, dynamic), 300)

    # ------------------------------------------------------------------
    # Public interface (mirrors OllamaLLM / OpenAILLM)
    # ------------------------------------------------------------------

    async def generate(self, prompt: str, stream: bool = False) -> str:
        """Generate text from Gemini. Returns the full response as a string."""
        if stream:
            return await self._stream_generate_async(prompt)
        return await asyncio.to_thread(self._generate_sync, prompt)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _generate_sync(self, prompt: str) -> str:
        """Blocking REST call to the Gemini GenerateContent API."""
        prompt_chars = len(prompt)
        logger.info(
            "Gemini LLM: Generating... model=%s prompt_chars=%d max_tokens=%d",
            self.model, prompt_chars, self.max_tokens,
        )
        last_error: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):
            started = time.perf_counter()
            try:
                response = requests.post(
                    self._api_url(),
                    headers={"Content-Type": "application/json"},
                    json=self._payload(prompt),
                    timeout=(self.connect_timeout_seconds, self._select_read_timeout(prompt_chars)),
                )
                response.raise_for_status()
                data = response.json()
                # Gemini response: {"candidates": [{"content": {"parts": [{"text": "..."}]}}]}
                candidates = data.get("candidates", [])
                text_parts = []
                for candidate in candidates:
                    parts = candidate.get("content", {}).get("parts", [])
                    for part in parts:
                        if isinstance(part.get("text"), str):
                            text_parts.append(part["text"])
                text = "".join(text_parts)
                elapsed = time.perf_counter() - started
                logger.info(
                    "Gemini LLM: Response received in %.1fs response_chars=%d attempt=%d/%d",
                    elapsed, len(text), attempt, self.max_retries,
                )
                if not text.strip():
                    finish_reason = (
                        candidates[0].get("finishReason", "UNKNOWN") if candidates else "NO_CANDIDATES"
                    )
                    raise ValueError(
                        f"Gemini returned an empty response (finishReason={finish_reason})"
                    )
                return text

            except requests.exceptions.Timeout as exc:
                elapsed = time.perf_counter() - started
                logger.warning(
                    "Gemini LLM timeout after %.1fs attempt=%d/%d",
                    elapsed, attempt, self.max_retries,
                )
                last_error = exc

            except requests.exceptions.ConnectionError as exc:
                logger.error("Gemini LLM: Cannot reach %s", _GEMINI_API_BASE)
                last_error = exc
                break

            except requests.exceptions.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else 0
                if status == 400:
                    body = {}
                    try:
                        body = exc.response.json()
                    except Exception:
                        pass
                    logger.error("Gemini LLM bad request: %s", body.get("error", {}).get("message", exc))
                elif status == 403:
                    logger.error("Gemini LLM: API key not authorized or quota exceeded")
                elif status == 429:
                    logger.error("Gemini LLM: Rate limit hit")
                else:
                    logger.error("Gemini LLM HTTP error %s: %s", status, exc)
                last_error = exc
                break

            except Exception as exc:
                elapsed = time.perf_counter() - started
                logger.error(
                    "Gemini LLM error after %.1fs attempt=%d/%d: %s",
                    elapsed, attempt, self.max_retries, exc,
                )
                last_error = exc
                break

        if last_error is None:
            raise RuntimeError("Gemini generation failed without a captured exception")
        raise last_error

    async def stream_generate(
        self,
        prompt: str,
        on_token: Optional[Callable[[str], None]] = None,
        progress_callback: Optional[StreamProgressCallback] = None,
    ) -> AsyncIterator[str]:
        """Async streaming generator using Gemini SSE."""
        try:
            import aiohttp
        except ImportError:
            logger.warning("aiohttp not installed; falling back to non-streaming Gemini")
            result = await asyncio.to_thread(self._generate_sync, prompt)
            yield result
            return

        logger.info(
            "Gemini LLM: Streaming... model=%s prompt_chars=%d", self.model, len(prompt)
        )

        timeout = aiohttp.ClientTimeout(
            total=self._select_read_timeout(len(prompt)), connect=15
        )
        url = self._api_url(stream=True)
        headers = {"Content-Type": "application/json"}

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, headers=headers, json=self._payload(prompt)) as resp:
                    resp.raise_for_status()
                    # Gemini streaming returns a JSON array of chunks separated by newlines
                    # Each chunk is a complete GenerateContentResponse JSON object
                    buffer = ""
                    async for raw in resp.content:
                        buffer += raw.decode("utf-8", errors="replace")
                        # Process complete JSON objects separated by commas/newlines
                        while True:
                            chunk_text, remaining = self._try_extract_json(buffer)
                            if chunk_text is None:
                                break
                            buffer = remaining
                            try:
                                chunk = json.loads(chunk_text)
                            except json.JSONDecodeError:
                                continue
                            candidates = chunk.get("candidates", [])
                            for candidate in candidates:
                                parts = candidate.get("content", {}).get("parts", [])
                                for part in parts:
                                    token = part.get("text", "")
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
            logger.error("Gemini LLM stream error: %s", exc)
            raise

    @staticmethod
    def _try_extract_json(buffer: str) -> tuple[Optional[str], str]:
        """Try to extract the next complete JSON object from buffer.

        Returns (json_str, remaining_buffer) or (None, buffer) if incomplete.
        Handles Gemini's streaming format which wraps chunks in a JSON array.
        """
        # Strip leading whitespace, '[', and ','
        stripped = buffer.lstrip(" \n\r\t[,")
        if not stripped:
            return None, buffer
        # Try to parse a complete JSON object
        if stripped[0] != "{":
            # Might be the closing ']' of the array
            return None, ""
        depth = 0
        in_string = False
        escape_next = False
        for i, ch in enumerate(stripped):
            if escape_next:
                escape_next = False
                continue
            if ch == "\\" and in_string:
                escape_next = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return stripped[: i + 1], stripped[i + 1 :]
        return None, buffer

    async def _stream_generate_async(self, prompt: str) -> str:
        accumulator = TokenAccumulator()
        await accumulator.consume(self.stream_generate(prompt))
        return accumulator.text
