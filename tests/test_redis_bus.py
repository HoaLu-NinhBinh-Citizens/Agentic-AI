"""
Tests for Distributed Redis Event Bus

Tests RedisEventBus and EventBusProtocol implementations.
"""

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch

from src.infrastructure.distributed.redis_bus import (
    RedisEventBus,
    RedisEventBusConfig,
    EventBusProtocol,
    EventBusBackend,
    InMemoryEventBus,
    create_event_bus,
)


# =============================================================================
# RedisEventBusConfig Tests
# =============================================================================

class TestRedisEventBusConfig:
    """Test RedisEventBusConfig dataclass."""

    def test_default_config(self):
        """Test default configuration."""
        config = RedisEventBusConfig()

        assert config.host == "localhost"
        assert config.port == 6379
        assert config.db == 0
        assert config.prefix == "ai_support:events:"

    def test_custom_config(self):
        """Test custom configuration."""
        config = RedisEventBusConfig(
            host="redis.example.com",
            port=6380,
            password="secret",
            ssl=True,
            cluster_mode=True,
        )

        assert config.host == "redis.example.com"
        assert config.port == 6380
        assert config.password == "secret"
        assert config.ssl is True
        assert config.cluster_mode is True


# =============================================================================
# InMemoryEventBus Tests
# =============================================================================

class TestInMemoryEventBus:
    """Test InMemoryEventBus implementation."""

    @pytest.fixture
    def bus(self):
        """Create an in-memory event bus."""
        return InMemoryEventBus()

    @pytest.mark.asyncio
    async def test_start_stop(self, bus):
        """Test starting and stopping bus."""
        await bus.start()
        assert bus.is_connected() is True

        await bus.stop()
        assert bus.is_connected() is False

    @pytest.mark.asyncio
    async def test_publish_subscribe(self, bus):
        """Test publishing and subscribing to events."""
        await bus.start()

        received = []

        async def handler(event):
            received.append(event)

        # Subscribe
        sub_id = await bus.subscribe("task.*", handler, "test_handler")

        # Publish
        await bus.publish("task.created", {"task_id": "123"}, "test_source")

        # Wait for async handler
        await asyncio.sleep(0.1)

        assert len(received) == 1
        assert received[0]["type"] == "task.created"
        assert received[0]["data"]["task_id"] == "123"

        # Unsubscribe
        await bus.unsubscribe(sub_id)
        await bus.stop()

    @pytest.mark.asyncio
    async def test_wildcard_subscription(self, bus):
        """Test wildcard subscription."""
        await bus.start()

        received = []

        async def handler(event):
            received.append(event)

        await bus.subscribe("*", handler, "wildcard_handler")
        await bus.publish("any.event", {"data": "test"}, "source")

        await asyncio.sleep(0.1)

        assert len(received) == 1

        await bus.stop()

    @pytest.mark.asyncio
    async def test_multiple_subscriptions(self, bus):
        """Test multiple subscriptions to same event."""
        await bus.start()

        received1 = []
        received2 = []

        async def handler1(event):
            received1.append(event)

        async def handler2(event):
            received2.append(event)

        await bus.subscribe("task.*", handler1, "handler1")
        await bus.subscribe("task.created", handler2, "handler2")

        await bus.publish("task.created", {}, "source")

        await asyncio.sleep(0.1)

        assert len(received1) == 1
        assert len(received2) == 1

        await bus.stop()

    @pytest.mark.asyncio
    async def test_unsubscribe(self, bus):
        """Test unsubscribing from events."""
        await bus.start()

        received = []

        async def handler(event):
            received.append(event)

        sub_id = await bus.subscribe("task.*", handler, "test_handler")
        await bus.unsubscribe(sub_id)

        await bus.publish("task.created", {}, "source")

        await asyncio.sleep(0.1)

        assert len(received) == 0

        await bus.stop()


# =============================================================================
# EventBusProtocol Tests
# =============================================================================

class TestEventBusProtocol:
    """Test EventBusProtocol interface."""

    def test_protocol_methods_exist(self):
        """Test that EventBusProtocol has required methods."""
        required_methods = [
            'publish',
            'subscribe',
            'unsubscribe',
            'start',
            'stop',
            'is_connected',
        ]

        for method in required_methods:
            assert hasattr(EventBusProtocol, method)


# =============================================================================
# create_event_bus Tests
# =============================================================================

class TestCreateEventBus:
    """Test event bus factory function."""

    def test_create_memory_bus(self):
        """Test creating in-memory event bus."""
        bus = create_event_bus(backend=EventBusBackend.MEMORY)

        assert isinstance(bus, InMemoryEventBus)

    def test_create_redis_bus(self):
        """Test creating Redis event bus."""
        bus = create_event_bus(backend=EventBusBackend.REDIS)

        assert isinstance(bus, RedisEventBus)

    def test_create_with_config(self):
        """Test creating with custom config."""
        config = RedisEventBusConfig(host="custom.redis.com", port=6380)
        bus = create_event_bus(backend=EventBusBackend.REDIS, config=config)

        assert isinstance(bus, RedisEventBus)
        assert bus.config.host == "custom.redis.com"


# =============================================================================
# RedisEventBus Mock Tests
# =============================================================================

class TestRedisEventBusMocked:
    """Test RedisEventBus with mocked Redis."""

    @pytest.mark.asyncio
    async def test_config_stored(self):
        """Test that config is stored correctly."""
        config = RedisEventBusConfig(
            host="test.redis.com",
            port=6380,
            prefix="test:",
        )
        bus = RedisEventBus(config)

        assert bus.config.host == "test.redis.com"
        assert bus.config.port == 6380
        assert bus.config.prefix == "test:"

    @pytest.mark.asyncio
    async def test_subscription_counter(self):
        """Test subscription ID counter."""
        bus = RedisEventBus()

        assert bus._subscription_counter == 0

    def test_matches_pattern(self):
        """Test pattern matching."""
        bus = RedisEventBus()

        # Exact match
        assert bus._matches_pattern("task.created", "task.created") is True

        # Wildcard match
        assert bus._matches_pattern("task.created", "task.*") is True
        assert bus._matches_pattern("task.created", "*.created") is True
        assert bus._matches_pattern("task.created", "*") is True

        # No match
        assert bus._matches_pattern("task.created", "workflow.*") is False

    def test_matches_pattern_complex(self):
        """Test complex pattern matching."""
        bus = RedisEventBus()

        assert bus._matches_pattern("task.created.v2", "task.*.*") is True
        assert bus._matches_pattern("my.task.created", "my.task.*") is True
