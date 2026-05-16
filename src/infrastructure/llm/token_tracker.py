"""
Token tracking utilities for LLM prompts and responses.

Provides:
- tiktoken-based counting for OpenAI models
- Heuristic approximation for Ollama models
- Prompt truncation before context overflow
- Token budget management
"""

import logging
import os
import re
import math
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Approximate tokens per token for common encodings
TOKENS_PER_TOKEN_RATIO = {
    "cl100k_base": 0.25,     # GPT-4 / Claude
    "p50k_base": 0.25,       # GPT-3.5 / Codex
    "r50k_base": 0.25,       # GPT-3
    "default": 0.25,          # fallback
}

# Context window sizes per model family
CONTEXT_WINDOWS = {
    # OpenAI
    "gpt-4o": 128000,
    "gpt-4o-mini": 128000,
    "gpt-4-turbo": 128000,
    "gpt-4": 8192,
    "gpt-4-32k": 32768,
    "gpt-3.5-turbo": 16385,
    "gpt-3.5-turbo-16k": 16385,
    # Ollama (conservative)
    "llama3.1": 128000,
    "llama3": 8192,
    "llama2": 4096,
    "mistral": 8192,
    "mixtral": 32768,
    "codellama": 16384,
    "nomic-embed-text":  8192,
    # default
    "default": 4096,
}

# Safety margin: leave this many tokens for the response
RESPONSE_SAFETY_MARGIN = 512


class TokenCounter:
    """
    Unified token counting interface supporting:
    - tiktoken for OpenAI models
    - Heuristic approximation for Ollama models
    """

    def __init__(self, model: str = ""):
        self.model = (model or os.environ.get("OPENAI_MODEL", "gpt-4o")).lower()
        self._tiktoken_encoder = None
        self._encoding_name = ""
        self._init_encoder()

    def _init_encoder(self):
        """Initialize tiktoken encoder if available."""
        try:
            import tiktoken
            encoding_name = self._detect_encoding()
            if encoding_name:
                self._tiktoken_encoder = tiktoken.get_encoding(encoding_name)
                self._encoding_name = encoding_name
                logger.debug("TokenCounter: tiktoken encoder '%s' loaded for model '%s'", encoding_name, self.model)
        except ImportError:
            logger.debug("TokenCounter: tiktoken not available, using heuristic estimation")
        except Exception as exc:
            logger.warning("TokenCounter: Failed to load tiktoken: %s", exc)

    def _detect_encoding(self) -> str:
        """Map model name to tiktoken encoding name."""
        model = self.model
        if "gpt-4o" in model or "gpt-4-turbo" in model:
            return "cl100k_base"
        if "gpt-4" in model:
            return "cl100k_base"
        if "gpt-3.5" in model or "code" in model:
            return "p50k_base"
        return "cl100k_base"

    def count(self, text: str) -> int:
        """Count tokens in text using tiktoken or heuristic."""
        if not text:
            return 0
        if self._tiktoken_encoder:
            try:
                return len(self._tiktoken_encoder.encode(text))
            except Exception:
                pass
        return self._heuristic_count(text)

    def count_messages(self, messages: list) -> int:
        """
        Count tokens for a messages array (OpenAI chat format).

        Args:
            messages: [{"role": "user", "content": "..."}, ...]
        """
        if not messages:
            return 0
        # Chat format overhead: ~4 tokens per message (role + opening/closing)
        overhead = 4 * len(messages)
        content_tokens = sum(self.count(str(msg.get("content", ""))) for msg in messages)
        return overhead + content_tokens

    def count_with_overhead(self, text: str) -> int:
        """Count tokens including per-call overhead (~3 tokens)."""
        return self.count(text) + 3

    def truncate_prompt(self, text: str, max_tokens: int) -> str:
        """
        Truncate text to fit within max_tokens.

        Uses binary search for accuracy and preserves beginning + end
        of important sections (marked with [QUERY], [CODE], etc.).
        """
        current = self.count(text)
        if current <= max_tokens:
            return text

        # Target: leave room for response
        target = max_tokens - RESPONSE_SAFETY_MARGIN
        if target <= 0:
            target = max_tokens // 2

        # Find section markers to preserve (head + tail)
        important_markers = ["[QUERY]", "[CODE]", "[RETRIEVED", "[UNDERSTANDING]",
                             "[REFERENCE", "[MEMORY]"]
        head_parts = []
        tail_parts = []
        remaining = text

        for marker in important_markers:
            idx = remaining.find(marker)
            if idx > 0:
                head_parts.append(remaining[:idx])
                remaining = remaining[idx:]
                break

        # Find closing markers for tail preservation
        tail_markers = ["[END]", "```", "\n\n# ", "\n## "]
        for marker in tail_markers:
            idx = remaining.rfind(marker)
            if idx > len(remaining) // 2:
                tail_parts.append(remaining[idx:])
                remaining = remaining[:idx]
                break

        head = "".join(head_parts)
        tail = "".join(tail_parts)
        middle = remaining

        # Binary search to find best truncation
        low, high = 0, len(middle)
        while low < high:
            mid = (low + high + 1) // 2
            candidate = head + middle[:mid] + tail
            if self.count(candidate) <= target:
                low = mid
            else:
                high = mid - 1

        truncated = head + middle[:low] + tail
        logger.debug("TokenCounter: Truncated %d -> %d tokens (target %d)",
                     self.count(text), self.count(truncated), target)
        return truncated

    def truncate_for_context(self, text: str, model: str = "") -> Tuple[str, int]:
        """
        Truncate text to fit the model's context window.

        Returns (truncated_text, original_count).
        """
        target_model = (model or self.model).lower()
        max_tokens = self.get_context_window(target_model) - RESPONSE_SAFETY_MARGIN
        original = self.count(text)
        if original <= max_tokens:
            return text, original
        return self.truncate_prompt(text, max_tokens), original

    def get_context_window(self, model: str = "") -> int:
        """Get the context window size for a model."""
        target = (model or self.model).lower()
        # Check exact match first
        if target in CONTEXT_WINDOWS:
            return CONTEXT_WINDOWS[target]
        # Check partial match
        for name, size in CONTEXT_WINDOWS.items():
            if name in target:
                return size
        return CONTEXT_WINDOWS["default"]

    def estimate_response_tokens(self, text: str) -> int:
        """Estimate how many tokens the model's response will be."""
        return self.count(text)

    def _heuristic_count(self, text: str) -> int:
        """
        Estimate token count using word + special character heuristic.

        More accurate than raw char/4 for code-heavy content.
        """
        if not text:
            return 0
        # Count words (whitespace-separated tokens)
        words = text.split()
        word_count = len(words)
        # Count code-like tokens (brackets, operators, etc.)
        code_tokens = len(re.findall(r"[(){}\[\];:,=<>+\-*/&|!@#$%^]", text))
        # Count string/char literals
        string_count = len(re.findall(r"['\"`].*?['\"`]", text, re.DOTALL))
        # Count line breaks (each line is ~1-2 tokens)
        newline_count = text.count("\n")
        # Estimate: words/4 + code_tokens/2 + strings/8 + newlines/4
        estimate = (
            word_count * 0.25
            + code_tokens * 0.5
            + string_count * 0.125
            + newline_count * 0.25
        )
        return max(1, int(estimate))

    def format_token_report(self, prompt: str, response: str = "") -> dict:
        """Generate a token usage report."""
        prompt_tokens = self.count(prompt)
        response_tokens = self.count(response) if response else 0
        context_window = self.get_context_window()
        utilization = (prompt_tokens / context_window) * 100 if context_window else 0
        return {
            "model": self.model,
            "prompt_tokens": prompt_tokens,
            "response_tokens": response_tokens,
            "total_tokens": prompt_tokens + response_tokens,
            "context_window": context_window,
            "utilization_pct": round(utilization, 1),
            "truncated": prompt_tokens > context_window - RESPONSE_SAFETY_MARGIN,
        }


# Singleton instance for convenience
_default_counter: Optional[TokenCounter] = None


def get_token_counter(model: str = "") -> TokenCounter:
    """Get or create the shared token counter instance."""
    global _default_counter
    if _default_counter is None or model:
        _default_counter = TokenCounter(model=model)
    return _default_counter


def count_tokens(text: str, model: str = "") -> int:
    """Quick token count for a single text."""
    return get_token_counter(model).count(text)


def truncate_for_model(text: str, model: str = "") -> str:
    """Quick truncation to fit a model's context."""
    counter = get_token_counter(model)
    return counter.truncate_for_context(text, model)[0]
