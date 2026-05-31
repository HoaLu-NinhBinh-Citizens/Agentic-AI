"""CLI command modules."""

from . import debug, flash, health, review, slash, trace, unified_review, watch, test_gen
from .unified_review import register
from . import search, undo, refactor, local_llm, lsp, metrics

def get_all_commands():
    """Get all available commands."""
    return {
        "review": review.register,
        "unified-review": register,
        "ur": register,  # Short alias
        "health": health.register,
        "debug": debug.register,
        "flash": flash.register,
        "trace": trace.register,
        "watch": watch.register,
        "test": test_gen.register,
        "search": search.register,
        "undo": undo.register,
        "refactor": refactor.register,
        "local-llm": local_llm.register,
        "lsp": lsp.register,
        "metrics": metrics.register,
    }

__all__ = [
    "debug",
    "flash",
    "health",
    "review",
    "slash",
    "trace",
    "unified_review",
    "watch",
    "test_gen",
    "search",
    "undo",
    "refactor",
    "local_llm",
    "lsp",
    "metrics",
    "get_all_commands",
]
