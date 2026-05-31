"""CLI command modules."""

from . import debug, flash, health, review, slash, trace, unified_review, watch, test_gen
from .unified_review import register

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
    "get_all_commands",
]
