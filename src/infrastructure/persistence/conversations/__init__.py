"""Persistence conversations module."""

from typing import Any


class ConversationStore:
    """Stores conversation history."""
    
    def __init__(self):
        self._conversations: dict[str, list[dict[str, Any]]] = {}
    
    def save(self, id: str, messages: list[dict[str, Any]]) -> None:
        """Save conversation."""
        self._conversations[id] = messages
    
    def load(self, id: str) -> list[dict[str, Any]]:
        """Load conversation."""
        return self._conversations.get(id, [])
