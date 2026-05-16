"""Server auth module."""

from typing import Any


class Auth:
    """Authentication handler."""
    
    async def authenticate(self, token: str) -> dict[str, Any]:
        """Authenticate token."""
        return {"user_id": "stub", "valid": True}
