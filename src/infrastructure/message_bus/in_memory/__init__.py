"""In-memory message bus."""

from typing import Any


class InMemoryMessageBus:
    """In-memory message bus."""
    
    def __init__(self):
        self._handlers: dict[str, list] = {}
    
    def subscribe(self, topic: str, handler: Any) -> None:
        """Subscribe to a topic."""
        if topic not in self._handlers:
            self._handlers[topic] = []
        self._handlers[topic].append(handler)
    
    async def publish(self, topic: str, message: Any) -> None:
        """Publish to a topic."""
        for handler in self._handlers.get(topic, []):
            await handler(message)
