"""
OpenAI-compatible LLM client for code generation.

This module provides an OpenAI API-compatible LLM client that can be used as
a fallback or primary model when Ollama is unavailable or for tasks requiring
more powerful reasoning (e.g., GPT-4-class models).
"""

import asyncio
import json
import logging
import os
import time
from typing import AsyncIterator, Callable, List, Optional

import requests

from .streaming import (
    TokenAccumulator,
    StreamProgressCallback,
    estimate_tokens_sync,
    stream_openai_sse,
)

logger = logging.getLogger(__name__)


class OpenAILLM:
    """Connect to OpenAI-compatible API for code generation."""

    def __init__(
        self,
        model: str = "",
        api_key: str = "",
        base_url: str = "",
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ):
        self.model = model or os.environ.get("OPENAI_MODEL", "gpt-4o")
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.base_url = base_url or os.environ.get("OPENAI_API_BASE", "https://api.openai.com/v1")
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.connect_timeout_seconds = 15
        self.read_timeout_seconds = int(os.environ.get("OPENAI_READ_TIMEOUT", "120") or 120)
        self.max_retries = 2
        self.streaming_enabled = os.environ.get("OPENAI_STREAMING", "1").lower() in {"1", "true", "yes"}

    @property
    def is_configured(self) -> bool:
        """Check if the client is properly configured with an API key."""
        if not self.api_key:
            logger.debug("OpenAI LLM: No API key configured")
            return False
        if not self.base_url:
            logger.debug("OpenAI LLM: No base URL configured")
            return False
        return True

    async def generate(self, prompt: str, stream: bool = False) -> str:
        """Generate text from the model."""
        if stream:
            return await self._stream_generate_async(prompt)
        return await asyncio.to_thread(self._generate_sync, prompt)

    def _generate_sync(self, prompt: str) -> str:
        """Synchronous generation with retries."""
        prompt_chars = len(prompt)
        logger.info(
            "OpenAI LLM: Generating... model=%s prompt_chars=%d max_tokens=%d",
            self.model,
            prompt_chars,
            self.max_tokens,
        )

        last_error: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            started = time.perf_counter()
            adjusted_max_tokens = max(512, self.max_tokens // attempt)
            try:
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": self.temperature,
                    "max_tokens": adjusted_max_tokens,
                }
                response = requests.post(
                    f"{self.base_url.rstrip('/')}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=(self.connect_timeout_seconds, self._select_read_timeout(prompt_chars)),
                )
                response.raise_for_status()
                data = response.json()
                text = str(data.get("choices", [{}])[0].get("message", {}).get("content", ""))
                elapsed = time.perf_counter() - started
                logger.info(
                    "OpenAI LLM: Response received in %.1fs response_chars=%d attempt=%d/%d",
                    elapsed,
                    len(text),
                    attempt,
                    self.max_retries,
                )
                if not text.strip():
                    raise ValueError("OpenAI returned an empty response")
                return text

            except requests.exceptions.Timeout as exc:
                elapsed = time.perf_counter() - started
                logger.warning(
                    "OpenAI LLM timeout after %.1fs attempt=%d/%d prompt_chars=%d",
                    elapsed,
                    attempt,
                    self.max_retries,
                    prompt_chars,
                )
                last_error = exc

            except requests.exceptions.ConnectionError as exc:
                logger.error("OpenAI LLM connection error: Cannot reach %s", self.base_url)
                last_error = exc
                break

            except requests.exceptions.HTTPError as exc:
                if exc.response.status_code == 401:
                    logger.error("OpenAI LLM auth error: Invalid API key")
                elif exc.response.status_code == 429:
                    logger.error("OpenAI LLM rate limit hit")
                else:
                    logger.error("OpenAI LLM HTTP error: %s", exc)
                last_error = exc
                break

            except Exception as exc:
                elapsed = time.perf_counter() - started
                logger.error(
                    "OpenAI LLM error after %.1fs attempt=%d/%d: %s",
                    elapsed,
                    attempt,
                    self.max_retries,
                    exc,
                )
                last_error = exc
                break

        if last_error is None:
            raise RuntimeError("OpenAI LLM generation failed without a captured exception")
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
        logger.info(
            "OpenAI LLM: Streaming... model=%s prompt_chars=%d max_tokens=%d",
            self.model,
            len(prompt),
            self.max_tokens,
        )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": True,
        }

        last_error: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            started = time.perf_counter()
            stream = stream_openai_sse(
                f"{self.base_url.rstrip('/')}/chat/completions",
                headers,
                payload,
                timeout_seconds=self._select_read_timeout(len(prompt)),
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
                    "OpenAI LLM: Stream completed in %.1fs tokens=%d attempt=%d/%d",
                    elapsed,
                    tokens_yielded,
                    attempt,
                    self.max_retries,
                )
                return

            except Exception as exc:
                elapsed = time.perf_counter() - started
                logger.warning(
                    "OpenAI LLM stream error after %.1fs attempt=%d/%d: %s",
                    elapsed,
                    attempt,
                    self.max_retries,
                    exc,
                )
                last_error = exc
                if attempt >= self.max_retries:
                    break

        if last_error is None:
            last_error = RuntimeError("OpenAI streaming failed without a captured exception")
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

    def _select_read_timeout(self, prompt_chars: int) -> int:
        dynamic_timeout = 120 + int(prompt_chars / 50)
        configured_timeout = int(self.read_timeout_seconds)
        return min(max(configured_timeout, dynamic_timeout), 300)


class ModelRouter:
    """
    Router that intelligently switches between Ollama, OpenAI, Anthropic, and Gemini models.

    Decision logic:
    - CODE_GENERATION tasks: use Ollama for local-only operation
    - DOCUMENT_ANALYSIS tasks: use Ollama (local, fast, PDF understanding)
    - FIX_ERRORS tasks: use Ollama (local-only mode)
    - SIMPLE_TASKS: use Ollama (fast, cheap)
    - Falls back along the configured fallback chain when primary fails

    Fallback chain (configurable, default): ollama → openai → anthropic → gemini
    """

    def __init__(
        self,
        ollama_client=None,
        openai_client: Optional[OpenAILLM] = None,
        anthropic_client=None,
        gemini_client=None,
        fallback_order: Optional[list] = None,
    ):
        self.ollama = ollama_client
        self.openai = openai_client
        self.anthropic = anthropic_client
        self.gemini = gemini_client
        # Provider resolution order used by generate_with_fallback()
        self._fallback_order: list = fallback_order or ["ollama", "openai", "anthropic", "gemini"]
        self._last_used: Optional[str] = None

    @property
    def available_models(self) -> dict:
        """Return available model information for all configured providers."""
        return {
            "ollama": {
                "available": self.ollama is not None,
                "model": getattr(self.ollama, "model", None) if self.ollama else None,
            },
            "openai": {
                "available": self.openai is not None and self.openai.is_configured,
                "model": getattr(self.openai, "model", None) if self.openai else None,
            },
            "anthropic": {
                "available": self.anthropic is not None and getattr(self.anthropic, "is_configured", False),
                "model": getattr(self.anthropic, "model", None) if self.anthropic else None,
            },
            "gemini": {
                "available": self.gemini is not None and getattr(self.gemini, "is_configured", False),
                "model": getattr(self.gemini, "model", None) if self.gemini else None,
            },
        }

    @property
    def available_provider_names(self) -> list:
        """Return names of currently available (configured) providers."""
        return [
            name for name, info in self.available_models.items() if info["available"]
        ]

    async def generate(
        self,
        prompt: str,
        task_type: str = "auto",
        force_model: str = "",
        tools: Optional[List[dict]] = None,
    ) -> str:
        """
        Generate text with intelligent model selection.

        Args:
            prompt: The prompt to send to the model.
            task_type: One of "auto", "code_generation", "document_analysis",
                      "fix_errors", "simple", "complex_reasoning".
            force_model: Force a specific model ("ollama" or "openai").
            tools: Optional list of OpenAI-style tool/function schemas.

        Returns:
            Generated text from the selected model.
        """
        if tools and force_model in ("ollama", ""):
            return await self._generate_ollama_with_tools(prompt, tools)
        if force_model == "openai":
            return await self._generate_openai(prompt)
        if force_model == "ollama":
            return await self._generate_ollama(prompt)
        if force_model == "anthropic":
            return await self._generate_anthropic(prompt)
        if force_model == "gemini":
            return await self._generate_gemini(prompt)

        model = self._select_model(task_type, prompt)
        self._last_used = model
        logger.info("ModelRouter: Selected '%s' for task_type='%s'", model, task_type)

        if model == "openai":
            return await self._generate_openai(prompt)
        if model == "anthropic":
            return await self._generate_anthropic(prompt)
        if model == "gemini":
            return await self._generate_gemini(prompt)
        return await self._generate_ollama(prompt)

    async def generate_streaming(
        self,
        prompt: str,
        task_type: str = "auto",
        force_model: str = "",
        on_token: Optional[Callable[[str], None]] = None,
        progress_callback: Optional[StreamProgressCallback] = None,
    ) -> AsyncIterator[str]:
        """
        Streaming generate with model selection.

        Args:
            prompt: The input prompt.
            task_type: Task classification type.
            force_model: Force a specific model.
            on_token: Callback for each token.
            progress_callback: StreamProgressCallback for progress display.

        Yields:
            Individual tokens as they arrive.
        """
        if force_model == "openai":
            async for token in self._stream_openai(prompt, on_token=on_token, progress_callback=progress_callback):
                yield token
            return
        if force_model == "ollama":
            async for token in self._stream_ollama(prompt, on_token=on_token, progress_callback=progress_callback):
                yield token
            return
        if force_model == "anthropic":
            async for token in self._stream_anthropic(prompt, on_token=on_token, progress_callback=progress_callback):
                yield token
            return
        if force_model == "gemini":
            async for token in self._stream_gemini(prompt, on_token=on_token, progress_callback=progress_callback):
                yield token
            return

        model = self._select_model(task_type, prompt)
        self._last_used = model
        logger.info("ModelRouter: Streaming with '%s' for task_type='%s'", model, task_type)

        if model == "openai":
            async for token in self._stream_openai(prompt, on_token=on_token, progress_callback=progress_callback):
                yield token
        elif model == "anthropic":
            async for token in self._stream_anthropic(prompt, on_token=on_token, progress_callback=progress_callback):
                yield token
        elif model == "gemini":
            async for token in self._stream_gemini(prompt, on_token=on_token, progress_callback=progress_callback):
                yield token
        else:
            async for token in self._stream_ollama(prompt, on_token=on_token, progress_callback=progress_callback):
                yield token

    def _select_model(self, task_type: str, prompt: str) -> str:
        """Select the best model based on task type, prompt characteristics, and config."""
        # Check if local-only mode is enabled
        from src.core.config.config_loader import get_config
        cfg = get_config()
        if cfg.get("model_routing.local_only", True):
            return "ollama"

        if task_type == "code_generation":
            return self._prefer_ollama_for_code(prompt)
        if task_type == "fix_errors":
            return "ollama"
        if task_type == "document_analysis":
            return "ollama"
        if task_type == "simple":
            return "ollama"
        if task_type == "complex_reasoning":
            return "ollama"
        return self._prefer_ollama_for_code(prompt)

    def _prefer_ollama_for_code(self, prompt: str) -> str:
        """Prefer Ollama for local-only operation."""
        return "ollama"

    async def _generate_ollama(self, prompt: str) -> str:
        """Generate using Ollama."""
        if self.ollama is None:
            if self.openai and self.openai.is_configured:
                logger.warning("Ollama unavailable, falling back to OpenAI")
                return await self._generate_openai(prompt)
            raise RuntimeError("No LLM client available (Ollama not configured)")
        return await self.ollama.generate(prompt)

    async def _generate_ollama_with_tools(self, prompt: str, tools: List[dict]) -> str:
        """Generate using Ollama with tool/function calling."""
        if self.ollama is None:
            raise RuntimeError("Ollama not configured for tool calling")
        # Build messages from prompt: split at "System:" and "Assistant:" boundaries
        # Simple approach: prepend system if not in prompt
        messages = []
        if "System:" in prompt:
            parts = prompt.split("System:", 1)
            messages.append({"role": "system", "content": parts[1].split("Assistant:", 1)[0].strip()})
            rest = parts[1].split("Assistant:", 1)[1] if "Assistant:" in parts[1] else parts[1]
            messages.append({"role": "user", "content": rest.strip()})
        else:
            messages.append({"role": "user", "content": prompt})

        result = await self.ollama.generate_with_tools(messages, tools)
        # Return content, or serialize tool calls if present
        if result.get("tool_calls"):
            tool_calls_str = "\n".join(
                f"<tool_call>{json.dumps(tc)}</tool_call>"
                for tc in result["tool_calls"]
            )
            return f"{result['content']}\n\n{tool_calls_str}".strip()
        return result["content"]

    async def _generate_openai(self, prompt: str) -> str:
        """Generate using OpenAI."""
        if self.openai is None or not self.openai.is_configured:
            if self.ollama:
                logger.warning("OpenAI unavailable, falling back to Ollama")
                return await self._generate_ollama(prompt)
            raise RuntimeError("No LLM client available (OpenAI not configured)")
        return await self.openai.generate(prompt)

    async def _stream_ollama(
        self,
        prompt: str,
        on_token: Optional[Callable[[str], None]] = None,
        progress_callback: Optional[StreamProgressCallback] = None,
    ) -> AsyncIterator[str]:
        """Stream using Ollama."""
        if self.ollama is None:
            if self.openai and self.openai.is_configured:
                logger.warning("Ollama unavailable, falling back to OpenAI streaming")
                async for token in self._stream_openai(prompt, on_token=on_token, progress_callback=progress_callback):
                    yield token
                return
            raise RuntimeError("No LLM client available (Ollama not configured)")
        async for token in self.ollama.stream_generate(prompt, on_token=on_token, progress_callback=progress_callback):
            yield token

    async def _stream_openai(
        self,
        prompt: str,
        on_token: Optional[Callable[[str], None]] = None,
        progress_callback: Optional[StreamProgressCallback] = None,
    ) -> AsyncIterator[str]:
        """Stream using OpenAI."""
        if self.openai is None or not self.openai.is_configured:
            if self.ollama:
                logger.warning("OpenAI unavailable, falling back to Ollama streaming")
                async for token in self._stream_ollama(prompt, on_token=on_token, progress_callback=progress_callback):
                    yield token
                return
            raise RuntimeError("No LLM client available (OpenAI not configured)")
        async for token in self.openai.stream_generate(prompt, on_token=on_token, progress_callback=progress_callback):
            yield token

    async def _generate_anthropic(self, prompt: str) -> str:
        """Generate using Anthropic Claude."""
        if self.anthropic is None or not getattr(self.anthropic, "is_configured", False):
            raise RuntimeError("No LLM client available (Anthropic not configured)")
        return await self.anthropic.generate(prompt)

    async def _generate_gemini(self, prompt: str) -> str:
        """Generate using Google Gemini."""
        if self.gemini is None or not getattr(self.gemini, "is_configured", False):
            raise RuntimeError("No LLM client available (Gemini not configured)")
        return await self.gemini.generate(prompt)

    async def _stream_anthropic(
        self,
        prompt: str,
        on_token: Optional[Callable[[str], None]] = None,
        progress_callback: Optional[StreamProgressCallback] = None,
    ) -> AsyncIterator[str]:
        """Stream using Anthropic Claude."""
        if self.anthropic is None or not getattr(self.anthropic, "is_configured", False):
            raise RuntimeError("Anthropic not configured")
        async for token in self.anthropic.stream_generate(prompt, on_token=on_token, progress_callback=progress_callback):
            yield token

    async def _stream_gemini(
        self,
        prompt: str,
        on_token: Optional[Callable[[str], None]] = None,
        progress_callback: Optional[StreamProgressCallback] = None,
    ) -> AsyncIterator[str]:
        """Stream using Google Gemini."""
        if self.gemini is None or not getattr(self.gemini, "is_configured", False):
            raise RuntimeError("Gemini not configured")
        async for token in self.gemini.stream_generate(prompt, on_token=on_token, progress_callback=progress_callback):
            yield token

    async def generate_with_fallback(
        self,
        prompt: str,
        primary: str = "ollama",
        task_type: str = "auto",
        tools: Optional[List[dict]] = None,
    ) -> str:
        """
        Generate with automatic fallback chain if primary model fails.

        Tries providers in ``_fallback_order`` starting from ``primary``.  If
        a provider fails (any exception) the next available one is tried.

        Args:
            prompt: The prompt to send.
            primary: Preferred provider ("ollama", "openai", "anthropic", "gemini").
            task_type: Task classification.
            tools: Optional list of OpenAI-style tool/function schemas.

        Returns:
            Generated text from the first provider that succeeds.

        Raises:
            RuntimeError: If all configured providers fail.
        """
        # Build ordered candidate list: primary first, then rest of fallback_order
        order = [primary] + [p for p in self._fallback_order if p != primary]
        errors: list = []
        for provider in order:
            info = self.available_models.get(provider, {})
            if not info.get("available"):
                continue
            try:
                result = await self.generate(prompt, task_type=task_type, force_model=provider, tools=tools)
                if errors:
                    logger.info(
                        "ModelRouter: Fallback to '%s' succeeded after %d failure(s)",
                        provider, len(errors),
                    )
                return result
            except Exception as exc:
                logger.warning(
                    "ModelRouter: Provider '%s' failed: %s — trying next in chain",
                    provider, exc,
                )
                errors.append((provider, exc))

        error_summary = "; ".join(f"{p}: {e}" for p, e in errors)
        raise RuntimeError(
            f"All LLM providers failed. Tried: {[p for p, _ in errors]}. Errors: {error_summary}"
        )
