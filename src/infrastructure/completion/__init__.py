"""Completion Engine — inline ghost text via local Ollama completion models."""

from src.infrastructure.completion.completion_engine import (
    CompletionCache,
    CompletionConfig,
    CompletionEngine,
    CompletionToken,
    OllamaCompletionAdapter,
)

__all__ = [
    "CompletionEngine",
    "CompletionConfig",
    "CompletionCache",
    "CompletionToken",
    "OllamaCompletionAdapter",
]
