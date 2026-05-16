"""Runtime health module."""

from typing import Any


async def check_runtime_health() -> dict[str, Any]:
    """Check runtime health."""
    return {"status": "healthy", "uptime": 0}
