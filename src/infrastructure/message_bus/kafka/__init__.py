"""Kafka message bus module."""

from typing import Any


class KafkaMessageBus:
    """Kafka-backed message bus."""
    
    async def publish(self, topic: str, message: Any) -> None:
        """Publish message."""
        pass
    
    async def subscribe(self, topic: str) -> Any:
        """Subscribe to topic."""
        return None
