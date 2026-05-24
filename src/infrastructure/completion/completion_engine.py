"""Completion Engine — inline ghost text via local Ollama completion models.

Architecture:
    User types → debounce 150ms → build context (surrounding tokens)
    → cache lookup (file_path + cursor + file_hash) → HIT: return cached
    → MISS: stream from Ollama completion endpoint → yield tokens
    → IDE renders ghost text via streaming callbacks

Supports FIM (Fill-in-the-Middle) prompting for multi-line completions.
Models: codellama:7b, deepseek-coder:6.7b, qwen2.5-coder:* (via Ollama).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, AsyncIterator

if TYPE_CHECKING:
    import httpx

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIG
# =============================================================================


@dataclass
class CompletionConfig:
    """Configuration for the completion engine."""
    # Ollama endpoint
    base_url: str = "http://localhost:11434"
    # Completion model — must support /api/generate endpoint
    model: str = "codellama:7b"
    # FIM model override; if None uses `model`
    fim_model: str | None = None
    # Context window sent to model (tokens, approximated as chars / 4)
    context_chars: int = 2048          # ~512 tokens
    # Prefix / suffix window around cursor (chars)
    cursor_window: int = 256
    # Debounce delay before triggering completion (ms)
    debounce_ms: int = 150
    # Max new tokens to generate
    max_tokens: int = 128
    # Temperature for completion
    temperature: float = 0.4
    # Cache size (LRU entries)
    cache_size: int = 512
    # Stop sequences (newline after first line = single-line mode)
    stop_after_first_line: bool = True
    # Logprobs (for confidence scoring — Ollama >= 0.1.20)
    logprobs: bool = False


# =============================================================================
# CACHE
# =============================================================================


@dataclass
class CacheEntry:
    """Cached completion result."""
    text: str
    confidence: float       # 0.0–1.0, from first-token logprob if available
    created_at: float       # time.time()


class CompletionCache:
    """LRU cache keyed by (file_path, cursor_line, cursor_col, file_hash)."""

    def __init__(self, maxsize: int = 512):
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._maxsize = maxsize

    def _make_key(
        self,
        file_path: str,
        cursor_line: int,
        cursor_col: int,
        file_hash: str,
    ) -> str:
        return f"{file_path}|{cursor_line}|{cursor_col}|{file_hash}"

    def get(
        self,
        file_path: str,
        cursor_line: int,
        cursor_col: int,
        file_hash: str,
    ) -> CacheEntry | None:
        key = self._make_key(file_path, cursor_line, cursor_col, file_hash)
        entry = self._cache.get(key)
        if entry is not None:
            self._cache.move_to_end(key)
        return entry

    def put(
        self,
        file_path: str,
        cursor_line: int,
        cursor_col: int,
        file_hash: str,
        text: str,
        confidence: float = 1.0,
    ) -> None:
        key = self._make_key(file_path, cursor_line, cursor_col, file_hash)
        self._cache[key] = CacheEntry(text=text, confidence=confidence,
                                      created_at=asyncio.get_event_loop().time())
        self._cache.move_to_end(key)
        while len(self._cache) > self._maxsize:
            self._cache.popitem(last=False)

    def invalidate_file(self, file_path: str) -> None:
        """Remove all cache entries for a specific file (called on save)."""
        keys = [k for k in self._cache if k.startswith(f"{file_path}|")]
        for k in keys:
            del self._cache[k]

    def clear(self) -> None:
        self._cache.clear()


# =============================================================================
# COMPLETION ENGINE
# =============================================================================


class CompletionEngine:
    """Streaming inline completion engine backed by Ollama /api/generate.

    Usage:
        engine = CompletionEngine(httpx_client, config)
        async for token in engine.complete("main.py", 42, 10, "def foo():\\n    "):
            print(token, end="", flush=True)
    """

    def __init__(
        self,
        http_client: httpx.AsyncClient,
        config: CompletionConfig | None = None,
    ) -> None:
        self._http = http_client
        self._cfg = config or CompletionConfig()
        self._cache = CompletionCache(maxsize=self._cfg.cache_size)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def complete(
        self,
        file_path: str,
        cursor_line: int,
        cursor_col: int,
        source_before: str,
        source_after: str = "",
        language: str | None = None,
    ) -> AsyncIterator[CompletionToken]:
        """Stream completion tokens for the cursor position.

        Args:
            file_path:     Absolute path of the file being edited.
            cursor_line:    0-based line number of the cursor.
            cursor_col:     0-based column of the cursor.
            source_before:  Text from the beginning of the file up to the cursor.
            source_after:   Text from cursor to end of file (may be empty).
            language:       Override language hint (inferred from extension if None).

        Yields:
            CompletionToken instances — one per emitted token.
        """
        file_hash = self._content_hash(source_before + source_after)

        # 1. Cache lookup
        if cached := self._cache.get(file_path, cursor_line, cursor_col, file_hash):
            logger.debug("completion_cache_hit", path=file_path,
                         line=cursor_line, col=cursor_col)
            for ch in cached.text:
                yield CompletionToken(text=ch, is_cached=True,
                                      confidence=cached.confidence)
            return

        # 2. Build prompt
        model, prompt = self._build_prompt(
            source_before, source_after,
            self._detect_language(file_path, language),
        )

        # 3. Stream from Ollama
        confidence = 0.0
        buffer = ""
        first_token = True

        async for raw in self._stream_generate(model, prompt):
            # raw: {"response": "...", "done": bool, "completion_reason"?}
            token_text = raw.get("response", "")
            if not token_text:
                continue

            if first_token:
                # first token logprob as confidence proxy (Ollama may include it)
                confidence = raw.get("probability", 1.0)
                first_token = False

            buffer += token_text

            # Stop sequences
            stop = False
            if self._cfg.stop_after_first_line and "\n" in token_text:
                buffer = buffer[:buffer.index("\n")]
                stop = True

            for ch in token_text[: token_text.index("\n") + 1 if "\n" in token_text else None]:
                yield CompletionToken(text=ch, is_cached=False, confidence=confidence)

            if stop:
                break

        # 4. Cache result
        if buffer:
            self._cache.put(file_path, cursor_line, cursor_col, file_hash,
                            buffer, confidence)
            logger.debug("completion_cached", path=file_path,
                         line=cursor_line, col=cursor_col, chars=len(buffer))

    async def complete_with_debounce(
        self,
        file_path: str,
        cursor_line: int,
        cursor_col: int,
        source_before: str,
        source_after: str = "",
        language: str | None = None,
    ) -> AsyncIterator[CompletionToken]:
        """complete() wrapped with debounce to avoid hammering on every keystroke."""
        try:
            await asyncio.sleep(self._cfg.debounce_ms / 1000.0)
        except asyncio.CancelledError:
            return

        async for token in self.complete(
            file_path, cursor_line, cursor_col,
            source_before, source_after, language,
        ):
            yield token

    def invalidate(self, file_path: str) -> None:
        """Call on file save / external change to flush stale entries."""
        self._cache.invalidate_file(file_path)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _content_hash(content: str) -> str:
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    @staticmethod
    def _detect_language(file_path: str, override: str | None) -> str:
        if override:
            return override
        ext_map = {
            ".c": "c", ".h": "c",
            ".py": "python",
            ".rs": "rust",
            ".go": "go",
            ".ts": "typescript", ".tsx": "typescript",
            ".js": "javascript",
            ".java": "java",
            ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp", ".hpp": "cpp",
            ".sh": "bash",
            ".yaml": "yaml", ".yml": "yaml",
            ".json": "json",
            ".toml": "toml",
            ".md": "markdown",
        }
        return ext_map.get(Path(file_path).suffix.lower(), "text")

    def _build_prompt(
        self,
        before: str,
        after: str,
        language: str,
    ) -> tuple[str, str]:
        """Build FIM prompt. Returns (model, prompt_string)."""
        model = self._cfg.fim_model or self._cfg.model

        # Context slice: grab last `context_chars` from `before`
        ctx = before[-self._cfg.context_chars:] if len(before) > self._cfg.context_chars else before

        if after:
            # FIM: prefix | <FILL> suffix <FILL> (CodeLLama format)
            prompt = (
                f"{ctx}"
                f"<FILL>"
                f"{after}"
                f"<FILL>"
            )
        else:
            # Simple completion (cursor at end of file)
            prompt = ctx

        return model, prompt

    async def _stream_generate(
        self,
        model: str,
        prompt: str,
    ) -> AsyncIterator[dict]:
        """Call Ollama /api/generate with streaming."""
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": True,
            "options": {
                "temperature": self._cfg.temperature,
                "num_predict": self._cfg.max_tokens,
            },
        }
        # Add logprobs if supported
        if self._cfg.logprobs:
            payload["options"]["logprobs"] = 5

        try:
            async with self._http.stream("POST",
                                          f"{self._cfg.base_url}/api/generate",
                                          json=payload,
                                          timeout=30.0) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line:
                        import json as _json
                        yield _json.loads(line)
        except httpx.HTTPStatusError as exc:
            logger.error("completion_http_error", status=exc.response.status_code,
                         detail=exc.response.text[:200])
        except Exception as exc:
            logger.error("completion_stream_error", exc=str(exc))


# =============================================================================
# TOKEN
# =============================================================================


@dataclass
class CompletionToken:
    """A single completion token emitted by the engine."""
    text: str           # The token character
    is_cached: bool     # True if served from cache
    confidence: float   # 0.0–1.0 (first-token probability proxy)


# =============================================================================
# INTEGRATION ADAPTER — wires completion into the existing LLM client
# =============================================================================


class OllamaCompletionAdapter:
    """Adapter that reuses the existing LLM client infrastructure.

    Wraps an existing OllamaAsync client (from infrastructure.llm.ollama)
    so completion shares connection pool, auth, and base URL settings.
    """

    def __init__(self, ollama_client: Any, config: CompletionConfig | None = None):
        """
        Args:
            ollama_client: Instance of `OllamaAsync` from infrastructure.llm.ollama.
            config:        CompletionConfig (reads from ollama_client.base_url if None).
        """
        import httpx
        self._cfg = config or CompletionConfig()
        self._cfg.base_url = getattr(ollama_client, "base_url",
                                    self._cfg.base_url)
        self._engine = CompletionEngine(httpx.AsyncClient(), self._cfg)
        self._ollama = ollama_client  # kept for reference; engine uses HTTP directly

    async def complete(
        self,
        file_path: str,
        cursor_line: int,
        cursor_col: int,
        source_before: str,
        source_after: str = "",
        language: str | None = None,
    ) -> AsyncIterator[CompletionToken]:
        """Streaming completion (same signature as CompletionEngine.complete)."""
        async for token in self._engine.complete(
            file_path, cursor_line, cursor_col,
            source_before, source_after, language,
        ):
            yield token

    def invalidate(self, file_path: str) -> None:
        self._engine.invalidate(file_path)
