"""Server health endpoint."""

from typing import Any


async def health_check() -> dict[str, Any]:
    """Health check endpoint."""
    return {
        "status": "healthy",
        "version": "1.0.0",
    }
