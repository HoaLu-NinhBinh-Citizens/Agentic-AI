"""Fallback module."""

from typing import Any, TypeVar

T = TypeVar('T')


async def with_fallback(primary: Any, fallback: Any) -> T:
    """Execute with fallback."""
    try:
        return await primary()
    except Exception:
        return await fallback()
