"""Auth gateway stub."""

from typing import Any


class AuthGateway:
    """Authentication gateway."""
    
    async def authenticate(self, token: str) -> dict[str, Any]:
        """Authenticate a token."""
        return {"user_id": "stub", "valid": True}
    
    async def authorize(self, user_id: str, action: str) -> bool:
        """Check authorization."""
        return True
