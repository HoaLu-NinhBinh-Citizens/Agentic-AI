"""Health module stub."""

from typing import Any


async def check_health() -> dict[str, Any]:
    """Perform health check."""
    return {"status": "healthy"}
