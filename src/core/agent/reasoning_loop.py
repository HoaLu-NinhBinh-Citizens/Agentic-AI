"""Reasoning loop stub."""

from typing import Any


class ReasoningLoop:
    """Core reasoning loop for agent."""
    
    async def reason(self, context: dict[str, Any]) -> dict[str, Any]:
        """Perform reasoning step."""
        return {"reasoning": "stub", "context": context}
