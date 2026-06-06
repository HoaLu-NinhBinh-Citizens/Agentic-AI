"""CLI command modules."""

from . import (
    flash,
    health,
    review,
    slash,
    trace,
    unified_review,
    watch,
    test_gen,
    search,
    undo,
    refactor,
    local_llm,
    lsp,
    metrics,
    complete,
    settings,
    git_ai,
    command_parser,
    virtual_commands,
)

# debug is intentionally excluded from top-level import to avoid
# pulling in src.domain.hardware (and its hardware chip definitions)
# which would break test collection for unrelated CLI tests.
# Import it lazily where needed: import src.interfaces.cli.commands.debug


def get_all_commands():
    """Get all available commands."""
    # Import debug lazily to avoid hardware side-effect
    import src.interfaces.cli.commands.debug as debug  # noqa: F401

    return {
        "review": review.register,
        "unified-review": unified_review.register,
        "ur": unified_review.register,
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
        "complete": complete.register,
        "settings": settings.register,
        "git-ai": git_ai.register,
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
    "complete",
    "settings",
    "git_ai",
    "command_parser",
    "virtual_commands",
    "get_all_commands",
]
