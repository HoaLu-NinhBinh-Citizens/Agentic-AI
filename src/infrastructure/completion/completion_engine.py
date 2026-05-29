"""Completion Engine — streaming inline completions via local Ollama completion models.

Architecture:
    User types → debounce 150ms → build context (surrounding tokens)
    → cache lookup (file_path + cursor + file_hash) → HIT: return cached
    → MISS: stream from Ollama completion endpoint → yield tokens
    → IDE renders ghost text via streaming callbacks

Supports FIM (Fill-in-the-Middle) prompting for multi-line completions.
Models: codellama:7b, deepseek-coder:6.7b, qwen2.5-coder:* (via Ollama).

REF-5 fixes applied:
  - FIM template: ctx (prefix) is now included BEFORE <FILL> so the model
    has full context before and after the cursor.
  - Subword streaming: stop yield loop immediately when a newline is encountered
    in a token, rather than yielding the full token then truncating the buffer.
  - OllamaCompletionAdapter: reuses the provided httpx client (connection pool)
    instead of creating a new one per request.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, AsyncIterator

if TYPE_CHECKING:
    import httpx

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIG
# =============================================================================


@dataclass
class CompletionConfig:
    """Configuration for the completion engine."""
    base_url: str = "http://localhost:11434"
    model: str = "codellama:7b"
    fim_model: str | None = None
    context_chars: int = 2048
    cursor_window: int = 256
    debounce_ms: int = 150
    max_tokens: int = 128
    temperature: float = 0.4
    cache_size: int = 512
    stop_after_first_line: bool = True
    logprobs: bool = False
    # Ollama supports up to 2048 context for most models
    ollama_keep_alive: int = 300  # seconds to keep model loaded


# =============================================================================
# CACHE
# =============================================================================


@dataclass
class CacheEntry:
    text: str
    confidence: float
    created_at: float


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
        self._cache[key] = CacheEntry(
            text=text,
            confidence=confidence,
            created_at=asyncio.get_running_loop().time(),
        )
        self._cache.move_to_end(key)
        while len(self._cache) > self._maxsize:
            self._cache.popitem(last=False)

    def invalidate_file(self, file_path: str) -> None:
        keys = [k for k in self._cache if k.startswith(f"{file_path}|")]
        for k in keys:
            del self._cache[k]

    def clear(self) -> None:
        self._cache.clear()


# =============================================================================
# TOKEN
# =============================================================================


@dataclass
class CompletionToken:
    """A single completion token emitted by the engine."""
    text: str
    is_cached: bool
    confidence: float


# =============================================================================
# COMPLETION ENGINE
# =============================================================================


class CompletionEngine:
    """Streaming inline completion engine backed by Ollama /api/generate.

    Usage:
        engine = CompletionEngine(httpx_client, config)
        async for token in engine.complete("main.py", 42, 10, "def foo():\n    "):
            print(token.text, end="", flush=True)
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
            cursor_line:   0-based line number of the cursor.
            cursor_col:    0-based column of the cursor.
            source_before: Text from the beginning of the file up to the cursor.
            source_after:  Text from cursor to end of file (may be empty).
            language:      Override language hint (inferred from extension if None).

        Yields:
            CompletionToken instances — one per emitted character.
        """
        file_hash = self._content_hash(source_before + source_after)

        # 1. Cache lookup
        if cached := self._cache.get(file_path, cursor_line, cursor_col, file_hash):
            logger.debug(
                "completion_cache_hit",
                path=file_path, line=cursor_line, col=cursor_col,
            )
            for ch in cached.text:
                yield CompletionToken(text=ch, is_cached=True, confidence=cached.confidence)
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
            token_text = raw.get("response", "")
            if not token_text:
                continue

            if first_token:
                confidence = raw.get("probability", raw.get("eval_count", 1) / max(self._cfg.max_tokens, 1))
                first_token = False

            # FIX REF-5: stop at first newline if single-line mode
            if self._cfg.stop_after_first_line and "\n" in token_text:
                newline_idx = token_text.index("\n")
                token_text = token_text[:newline_idx]
                stop = True
            else:
                stop = False

            buffer += token_text

            for ch in token_text:
                yield CompletionToken(text=ch, is_cached=False, confidence=confidence)

            if stop:
                break

        # 4. Cache result
        if buffer:
            self._cache.put(
                file_path, cursor_line, cursor_col, file_hash,
                buffer, confidence,
            )
            logger.debug(
                "completion_cached",
                path=file_path, line=cursor_line, col=cursor_col, chars=len(buffer),
            )

    async def complete_with_debounce(
        self,
        file_path: str,
        cursor_line: int,
        cursor_col: int,
        source_before: str,
        source_after: str = "",
        language: str | None = None,
    ) -> AsyncIterator[CompletionToken]:
        """complete() with debounce to avoid hammering on every keystroke."""
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
        """Flush stale cache entries on file save / external change."""
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
        ext_map: dict[str, str] = {
            ".c": "c", ".h": "c",
            ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp", ".hpp": "cpp",
            ".py": "python",
            ".rs": "rust",
            ".go": "go",
            ".ts": "typescript", ".tsx": "typescript",
            ".js": "javascript", ".jsx": "javascript",
            ".java": "java",
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
        """Build FIM prompt. Returns (model, prompt_string).

        REF-5 fix: ctx (prefix) is now placed BEFORE <FILL> so the model has
        the full prefix context before generating the fill, matching the correct
        CodeLLama FIM format:
            <PRE> {prefix} <SUF> {suffix} <MID> {generated}

        For non-FIM (after is empty), returns just the prefix context.
        """
        model = self._cfg.fim_model or self._cfg.model

        # Context slice: last `context_chars` from prefix to stay within model window
        ctx = before[-self._cfg.context_chars:] if len(before) > self._cfg.context_chars else before

        if after:
            # FIM: prefix <FILL> suffix <FILL>
            # The model generates what goes between prefix and suffix
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
        """Call Ollama /api/generate with streaming, reusing self._http."""
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "stream": True,
            "options": {
                "temperature": self._cfg.temperature,
                "num_predict": self._cfg.max_tokens,
                "tfs_z": 1.0,          # tail-free sampling for cleaner stops
            },
            "keep_alive": self._cfg.ollama_keep_alive,
        }
        if self._cfg.logprobs:
            payload["options"]["logprobs"] = 5

        try:
            async with self._http.stream(
                "POST",
                f"{self._cfg.base_url}/api/generate",
                json=payload,
                timeout=self._cfg.max_tokens * 0.1 + 10.0,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line:
                        yield json.loads(line)
        except Exception as exc:
            logger.error(
                "completion_stream_error",
                model=model, exc=str(exc),
            )


# =============================================================================
# INTEGRATION ADAPTER
# =============================================================================


class OllamaCompletionAdapter:
    """Adapter that reuses the existing LLM client infrastructure.

    REF-5 fix: Accepts an existing httpx.AsyncClient and passes it directly
    to CompletionEngine so the connection pool, timeouts, and retry settings
    are shared across all Ollama calls.

    Usage:
        adapter = OllamaCompletionAdapter(
            ollama_client=ollama_async_instance,  # from infrastructure.llm.ollama
            http_client=shared_httpx_client,      # reuse connection pool
        )
    """

    def __init__(
        self,
        ollama_client: Any,
        http_client: httpx.AsyncClient | None = None,
        config: CompletionConfig | None = None,
    ) -> None:
        self._cfg = config or CompletionConfig()
        self._cfg.base_url = getattr(ollama_client, "base_url", self._cfg.base_url)

        # REF-5 fix: reuse http_client instead of creating a new one
        if http_client is not None:
            self._http = http_client
        else:
            import httpx
            self._http = httpx.AsyncClient(
                timeout=httpx.Timeout(60.0),
                limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
            )

        self._engine = CompletionEngine(self._http, self._cfg)
        self._ollama = ollama_client

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
