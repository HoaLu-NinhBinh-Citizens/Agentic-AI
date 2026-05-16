"""Metrics module."""

from typing import Any


def get_metrics() -> dict[str, Any]:
    """Get current metrics."""
    return {"requests": 0, "errors": 0}
