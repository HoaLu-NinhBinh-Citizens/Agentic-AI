import asyncio
import logging
import os
import re
import time
from typing import AsyncIterator, Callable, Optional

import requests

from src.core.config.agent_prompts import LOCAL_AGENT_RAG_BEHAVIOR_PROMPT

from .base import BaseLLM
from .streaming import (
    TokenAccumulator,
    StreamProgressCallback,
    estimate_tokens_sync,
    stream_ollama_sse,
)

logger = logging.getLogger(__name__)


class OllamaLLM(BaseLLM):
    """Connect to Ollama for code generation."""

    def __init__(self, model: str = "", url: str = "", keep_alive: Optional[str] = None):
        self.model = model or os.environ.get("CARV_OLLAMA_MODEL") or os.environ.get("OLLAMA_MODEL") or "llama3.1:latest"
        self.url = url or os.environ.get("CARV_OLLAMA_URL") or "http://localhost:11434"
        self.keep_alive = keep_alive if keep_alive is not None else self._parse_keep_alive(os.environ.get("CARV_OLLAMA_KEEP_ALIVE", "0"))
        self.connect_timeout_seconds = 10
        self.read_timeout_seconds = int(os.environ.get("CARV_OLLAMA_READ_TIMEOUT", "90") or 90)
        self.max_retries = 2
        self.streaming_enabled = os.environ.get("CARV_OLLAMA_STREAMING", "1").lower() in {"1", "true", "yes"}
        self.base_prompt = f"""{LOCAL_AGENT_RAG_BEHAVIOR_PROMPT}

You are an expert embedded C developer.
Write production-ready C code:
- Proper error handling
- Clear variable names
- STM32/ARM HAL conventions
- Avoid undefined behavior
    """

    async def generate(self, prompt: str, stream: bool = False) -> str:
        """
        Generate text from the model.

        Args:
            prompt: The input prompt.
            stream: If True, yields a StreamingResponse with an async token iterator.
                    If False (default), returns the complete text as a string.
        """
        if stream:
            return await self._stream_generate_async(prompt)
        return await asyncio.to_thread(self._generate_sync, prompt)

    def _generate_sync(self, prompt: str) -> str:
        """Synchronous non-streaming generation."""
        prompt_text = f"{self.base_prompt}\n\n{prompt}"
        prompt_chars = len(prompt_text)
        num_predict = self._select_num_predict(prompt)
        logger.info(
            "LLM: Generating code... model=%s prompt_chars=%d num_predict=%d",
            self.model,
            prompt_chars,
            num_predict,
        )

        last_error: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            started = time.perf_counter()
            try:
                response = requests.post(
                    f"{self.url}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt_text,
                        "temperature": 0.3,
                        "num_predict": num_predict,
                        "stream": False,
                        "keep_alive": self.keep_alive,
                    },
                    timeout=(self.connect_timeout_seconds, self._select_read_timeout(prompt_chars)),
                )
                response.raise_for_status()
                payload = response.json()
                text = str(payload.get("response", ""))
                elapsed = time.perf_counter() - started
                logger.info(
                    "LLM: Response received in %.1fs response_chars=%d attempt=%d/%d",
                    elapsed,
                    len(text),
                    attempt,
                    self.max_retries,
                )
                if not text.strip():
                    raise ValueError("Ollama returned an empty response")
                return text
            except requests.exceptions.Timeout as exc:
                elapsed = time.perf_counter() - started
                logger.warning(
                    "LLM timeout after %.1fs attempt=%d/%d prompt_chars=%d num_predict=%d",
                    elapsed,
                    attempt,
                    self.max_retries,
                    prompt_chars,
                    num_predict,
                )
                last_error = exc
                num_predict = max(512, num_predict // 2)
            except requests.exceptions.ConnectionError as exc:
                logger.error("LLM connection error: Cannot connect to Ollama at %s", self.url)
                logger.error("Please start Ollama: ollama serve")
                last_error = exc
                break
            except requests.exceptions.HTTPError as exc:
                if exc.response.status_code == 404:
                    logger.error("LLM error: Model '%s' not found", self.model)
                    logger.error("Pull model: ollama pull %s", self.model)
                else:
                    logger.error("LLM HTTP error: %s", exc)
                last_error = exc
                break
            except Exception as exc:
                elapsed = time.perf_counter() - started
                logger.error(
                    "LLM error after %.1fs attempt=%d/%d: %s",
                    elapsed,
                    attempt,
                    self.max_retries,
                    exc,
                )
                last_error = exc
                break

        if last_error is None:
            raise RuntimeError("Ollama generation failed without a captured exception")
        raise last_error

    async def stream_generate(
        self,
        prompt: str,
        on_token: Optional[Callable[[str], None]] = None,
        progress_callback: Optional[StreamProgressCallback] = None,
    ) -> AsyncIterator[str]:
        """
        Async streaming generator that yields tokens one by one.

        Args:
            prompt: The input prompt.
            on_token: Optional callback for each token.
            progress_callback: Optional StreamProgressCallback for progress display.

        Yields:
            Individual tokens as they arrive from the model.
        """
        prompt_text = f"{self.base_prompt}\n\n{prompt}"
        prompt_chars = len(prompt_text)
        num_predict = self._select_num_predict(prompt)
        logger.info(
            "LLM: Streaming... model=%s prompt_chars=%d num_predict=%d",
            self.model,
            prompt_chars,
            num_predict,
        )

        json_payload = {
            "model": self.model,
            "prompt": prompt_text,
            "temperature": 0.3,
            "num_predict": num_predict,
            "stream": True,
            "keep_alive": self.keep_alive,
        }

        last_error: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            started = time.perf_counter()
            stream = stream_ollama_sse(
                self.url,
                json_payload,
                timeout_seconds=self._select_read_timeout(prompt_chars),
            )

            try:
                tokens_yielded = 0
                token_stream = stream
                if progress_callback:
                    token_stream = self._merge_progress(stream, progress_callback)

                async for token in token_stream:
                    tokens_yielded += 1
                    if on_token:
                        try:
                            on_token(token)
                        except Exception:
                            pass
                    yield token

                elapsed = time.perf_counter() - started
                logger.info(
                    "LLM: Stream completed in %.1fs tokens=%d attempt=%d/%d",
                    elapsed,
                    tokens_yielded,
                    attempt,
                    self.max_retries,
                )
                return

            except Exception as exc:
                elapsed = time.perf_counter() - started
                logger.warning(
                    "LLM stream error after %.1fs attempt=%d/%d: %s",
                    elapsed,
                    attempt,
                    self.max_retries,
                    exc,
                )
                last_error = exc
                if attempt >= self.max_retries:
                    break

        if last_error is None:
            last_error = RuntimeError("Ollama streaming failed without a captured exception")
        raise last_error

    async def _stream_generate_async(self, prompt: str) -> str:
        """Stream and accumulate into a single string."""
        accumulator = TokenAccumulator()
        await accumulator.consume(self.stream_generate(prompt))
        return accumulator.text

    async def _merge_progress(
        self,
        stream: AsyncIterator[str],
        callback: StreamProgressCallback,
    ) -> AsyncIterator[str]:
        """Merge streamed tokens with progress callback."""
        async for token in stream:
            await callback(token)
            yield token

    def _select_num_predict(self, prompt: str) -> int:
        lowered = prompt.lower()
        if "[code]" in lowered or "file:" in lowered:
            return 1024
        if "reviewer" in lowered or "return json only" in lowered:
            return 768
        if "fix:" in lowered:
            return 896
        return 640

    def _select_read_timeout(self, prompt_chars: int) -> int:
        dynamic_timeout = 90 + int(prompt_chars / 100)
        configured_timeout = int(self.read_timeout_seconds)
        return min(max(configured_timeout, dynamic_timeout), 300)

    def _parse_keep_alive(self, value: str):
        text = str(value).strip()
        if re_match := re.fullmatch(r"-?\d+", text):
            return int(re_match.group(0))
        return text

    async def generate_with_tools(
        self,
        messages: list,
        tools: list,
        stream: bool = False,
    ) -> dict:
        """
        Generate using Ollama /api/chat with tool/function calling support.

        Args:
            messages: List of {"role": ..., "content": ...} message dicts.
            tools: List of OpenAI-style function definitions.
            stream: If True, yields streaming tokens; if False, returns full response.

        Returns:
            A dict with keys:
                - content: str (assistant text)
                - tool_calls: list of {"name": ..., "arguments": {...}} (if any)
                - finish_reason: str
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "stream": stream,
            "keep_alive": self.keep_alive,
        }
        timeout = (self.connect_timeout_seconds, self.read_timeout_seconds)

        last_error: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            started = time.perf_counter()
            try:
                response = requests.post(
                    f"{self.url}/api/chat",
                    json=payload,
                    timeout=timeout,
                )
                response.raise_for_status()
                payload_resp = response.json()
                elapsed = time.perf_counter() - started

                result = {
                    "content": str(payload_resp.get("message", {}).get("content", "")),
                    "tool_calls": [],
                    "finish_reason": str(payload_resp.get("done_reason", "stop")),
                }

                # Extract tool calls from Ollama response
                raw_message = payload_resp.get("message", {})
                if "tool_calls" in raw_message:
                    result["tool_calls"] = raw_message["tool_calls"]
                elif raw_message.get("type") == "tool":
                    # Some models return tool calls differently
                    tool_call = {
                        "name": raw_message.get("name", ""),
                        "arguments": raw_message.get("input", {}),
                    }
                    if tool_call["name"]:
                        result["tool_calls"] = [tool_call]

                logger.info(
                    "LLM (tools): Response in %.1fs chars=%d tool_calls=%d attempt=%d/%d",
                    elapsed,
                    len(result["content"]),
                    len(result["tool_calls"]),
                    attempt,
                    self.max_retries,
                )
                return result

            except requests.exceptions.Timeout as exc:
                logger.warning("LLM tools timeout attempt=%d/%d", attempt, self.max_retries)
                last_error = exc
            except requests.exceptions.ConnectionError as exc:
                logger.error("LLM connection error: Cannot connect to Ollama at %s", self.url)
                last_error = exc
                break
            except requests.exceptions.HTTPError as exc:
                if exc.response.status_code == 404:
                    logger.error("Model '%s' not found", self.model)
                last_error = exc
                break
            except Exception as exc:
                logger.error("LLM tools error attempt=%d/%d: %s", attempt, self.max_retries, exc)
                last_error = exc

        if last_error is None:
            last_error = RuntimeError("Ollama generate_with_tools failed without exception")
        raise last_error
