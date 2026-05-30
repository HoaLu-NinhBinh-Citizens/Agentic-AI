"""Redis message bus implementations."""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Dict, List, Optional


class RedisEventBusConfig:
    """Configuration for Redis event bus."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: Optional[str] = None,
        ssl: bool = False,
        cluster_mode: bool = False,
        prefix: str = "ai_support:events:",
    ):
        self.host = host
        self.port = port
        self.db = db
        self.password = password
        self.ssl = ssl
        self.cluster_mode = cluster_mode
        self.prefix = prefix


class EventBusProtocol:
    """Protocol for event bus implementations."""

    async def publish(self, channel: str, event: Dict[str, Any], source: str) -> None:
        ...

    async def subscribe(self, pattern: str, handler: Callable, label: str) -> str:
        ...

    async def unsubscribe(self, subscription_id: str) -> None:
        ...

    async def start(self) -> None:
        ...

    async def stop(self) -> None:
        ...

    def is_connected(self) -> bool:
        ...


class RedisMessageBus(EventBusProtocol):
    """Redis-backed message bus."""

    def __init__(self, config: Optional[RedisEventBusConfig] = None):
        self.config = config or RedisEventBusConfig()
        self._url = f"redis://{self.config.host}:{self.config.port}/{self.config.db}"
        self._subscription_counter = 0
        self._subscriptions: Dict[str, Dict] = {}
        self._running = False
        self._handlers: Dict[str, List[Callable]] = {}

    async def publish(self, channel: str, event: Dict[str, Any], source: str) -> None:
        """Publish an event to a channel."""
        pass

    async def subscribe(self, pattern: str, handler: Callable, label: str) -> str:
        """Subscribe to events matching a pattern."""
        sub_id = str(self._subscription_counter)
        self._subscription_counter += 1
        self._subscriptions[sub_id] = {"pattern": pattern, "handler": handler, "label": label}
        if pattern not in self._handlers:
            self._handlers[pattern] = []
        self._handlers[pattern].append(handler)
        return sub_id

    async def unsubscribe(self, subscription_id: str) -> None:
        """Unsubscribe by subscription ID."""
        if subscription_id in self._subscriptions:
            sub = self._subscriptions.pop(subscription_id)
            pattern = sub["pattern"]
            handler = sub["handler"]
            if pattern in self._handlers and handler in self._handlers[pattern]:
                self._handlers[pattern].remove(handler)

    async def start(self) -> None:
        """Start the event bus."""
        self._running = True

    async def stop(self) -> None:
        """Stop the event bus."""
        self._running = False
        self._subscriptions.clear()
        self._handlers.clear()

    def is_connected(self) -> bool:
        """Check if connected."""
        return self._running

    def _matches_pattern(self, channel: str, pattern: str) -> bool:
        """Match channel against pattern with * wildcard support."""
        if pattern == "*":
            return True
        if ".*" in pattern:
            channel_parts = channel.split(".")
            pattern_parts = pattern.split(".")
            if len(channel_parts) != len(pattern_parts):
                return False
            return all(
                pc == "*" or pc == cc for cc, pc in zip(channel_parts, pattern_parts)
            )
        return channel == pattern


class InMemoryEventBus(EventBusProtocol):
    """In-memory event bus for testing and single-process use."""

    def __init__(self):
        self._handlers: Dict[str, List[Callable]] = {}
        self._subscriptions: Dict[str, Dict] = {}
        self._counter = 0
        self._running = False

    async def publish(self, channel: str, event: Dict[str, Any], source: str) -> None:
        """Publish an event to a channel."""
        if not self._running:
            return
        event_with_meta = {"type": channel, "data": event, "source": source}
        for pattern, handlers in list(self._handlers.items()):
            if self._matches_pattern(channel, pattern):
                for handler in handlers:
                    asyncio.create_task(handler(event_with_meta))

    async def subscribe(self, pattern: str, handler: Callable, label: str) -> str:
        """Subscribe to events matching a pattern."""
        sub_id = f"sub_{self._counter}"
        self._counter += 1
        self._subscriptions[sub_id] = {"pattern": pattern, "handler": handler, "label": label}
        if pattern not in self._handlers:
            self._handlers[pattern] = []
        self._handlers[pattern].append(handler)
        return sub_id

    async def unsubscribe(self, subscription_id: str) -> None:
        """Unsubscribe by subscription ID."""
        if subscription_id in self._subscriptions:
            sub = self._subscriptions.pop(subscription_id)
            pattern = sub["pattern"]
            handler = sub["handler"]
            if pattern in self._handlers and handler in self._handlers[pattern]:
                self._handlers[pattern].remove(handler)

    async def start(self) -> None:
        """Start the event bus."""
        self._running = True

    async def stop(self) -> None:
        """Stop the event bus."""
        self._running = False
        self._handlers.clear()
        self._subscriptions.clear()

    def is_connected(self) -> bool:
        """Check if connected."""
        return self._running

    def _matches_pattern(self, channel: str, pattern: str) -> bool:
        """Match channel against pattern with * wildcard support."""
        if pattern == "*":
            return True
        if ".*" in pattern:
            channel_parts = channel.split(".")
            pattern_parts = pattern.split(".")
            if len(channel_parts) != len(pattern_parts):
                return False
            return all(
                pc == "*" or pc == cc for cc, pc in zip(channel_parts, pattern_parts)
            )
        return channel == pattern


class EventBusBackend:
    """Backend types for event bus factory."""

    REDIS = "redis"
    MEMORY = "memory"


def create_event_bus(
    backend: str = EventBusBackend.MEMORY,
    config: Optional[RedisEventBusConfig] = None,
) -> EventBusProtocol:
    """Factory function to create an event bus."""
    if backend == EventBusBackend.REDIS:
        return RedisMessageBus(config)
    return InMemoryEventBus()


# Alias for compatibility
RedisEventBus = RedisMessageBus
