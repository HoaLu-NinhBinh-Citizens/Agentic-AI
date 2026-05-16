"""Server API module."""

from typing import Any


async def handle_request(request: dict[str, Any]) -> dict[str, Any]:
    """Handle API request."""
    return {"status": "ok"}
