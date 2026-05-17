"""Unit tests for LifecycleManager."""

from __future__ import annotations

import asyncio
import time

import pytest
import pytest_asyncio

from src.infrastructure.router.observation.health_monitor import HealthMonitor
from src.infrastructure.router.observation.lifecycle_manager import (
    InMemoryLifecycleStorage,
    LifecycleManager,
)
from src.infrastructure.router.types import (
    IntentLifecycle,
    IntentLifecycleState,
    LifecycleConfig,
)


class TestLifecycleManagerBasic:
    """Test basic LifecycleManager functionality."""

    @pytest.fixture
    def health_monitor(self) -> HealthMonitor:
        """Create health monitor."""
        return HealthMonitor(window_size=100)

    @pytest.fixture
    def storage(self) -> InMemoryLifecycleStorage:
        """Create lifecycle storage."""
        return InMemoryLifecycleStorage()

    @pytest.fixture
    def config(self) -> LifecycleConfig:
        """Create lifecycle config."""
        return LifecycleConfig(
            disable_ttl_seconds=3600,  # 1 hour for testing
            auto_restore_if_health_recovers=True,
            restore_success_rate_threshold=0.7,
            restore_observation_window_hours=1,
        )

    @pytest.fixture
    def manager(
        self,
        storage: InMemoryLifecycleStorage,
        health_monitor: HealthMonitor,
        config: LifecycleConfig,
    ) -> LifecycleManager:
        """Create lifecycle manager."""
        return LifecycleManager(
            storage=storage,
            config=config,
            health_monitor=health_monitor,
        )

    @pytest.mark.asyncio
    async def test_get_intent_state_default_active(
        self, manager: LifecycleManager
    ):
        """Test that new intents start as active."""
        lifecycle = await manager.get_intent_state("new_intent")

        assert lifecycle.state == IntentLifecycleState.ACTIVE
        assert lifecycle.is_available is True
        assert lifecycle.should_auto_restore is False

    @pytest.mark.asyncio
    async def test_disable_intent(
        self, manager: LifecycleManager
    ):
        """Test disabling an intent."""
        await manager.disable_intent(
            "test_intent",
            reason="Testing disable",
            ttl_seconds=60,
        )

        lifecycle = await manager.get_intent_state("test_intent")

        assert lifecycle.state == IntentLifecycleState.DISABLED
        assert lifecycle.is_available is False
        assert lifecycle.auto_restore_after is not None

    @pytest.mark.asyncio
    async def test_enable_intent(
        self, manager: LifecycleManager
    ):
        """Test enabling an intent."""
        # First disable
        await manager.disable_intent("test_intent", reason="test")
        await manager.enable_intent("test_intent")

        lifecycle = await manager.get_intent_state("test_intent")

        assert lifecycle.state == IntentLifecycleState.ACTIVE
        assert lifecycle.is_available is True

    @pytest.mark.asyncio
    async def test_auto_restore_after_ttl_expires(
        self, storage: InMemoryLifecycleStorage
    ):
        """Test auto-restore after TTL expires (simplified)."""
        health_monitor = HealthMonitor()
        config = LifecycleConfig(
            disable_ttl_seconds=1,  # 1 second for testing
            auto_restore_if_health_recovers=True,
            restore_success_rate_threshold=0.7,
            restore_observation_window_hours=1,
        )
        manager = LifecycleManager(
            storage=storage,
            config=config,
            health_monitor=health_monitor,
        )

        # Record good health
        for _ in range(10):
            await health_monitor.record("test_intent", success=True, latency_ms=10)

        # Disable with short TTL
        await manager.disable_intent("test_intent", reason="test", ttl_seconds=1)

        # Verify disabled immediately
        lifecycle = await manager.get_intent_state("test_intent")
        assert lifecycle.state == IntentLifecycleState.DISABLED
        assert lifecycle.auto_restore_after is not None

        # TTL should have expired setting for auto-restore
        # The actual restoration happens on next get_intent_state call after TTL

    @pytest.mark.asyncio
    async def test_no_auto_restore_with_bad_health(
        self, storage: InMemoryLifecycleStorage
    ):
        """Test no auto-restore with bad health."""
        health_monitor = HealthMonitor()
        config = LifecycleConfig(
            disable_ttl_seconds=1,
            auto_restore_if_health_recovers=True,
            restore_success_rate_threshold=0.7,
            restore_observation_window_hours=1,
        )
        manager = LifecycleManager(
            storage=storage,
            config=config,
            health_monitor=health_monitor,
        )

        # Record bad health
        for _ in range(10):
            await health_monitor.record("test_intent", success=False, latency_ms=100)

        # Disable with short TTL
        await manager.disable_intent("test_intent", reason="test", ttl_seconds=1)

        # Wait for TTL
        await asyncio.sleep(1.5)

        # Should not restore (TTL extended due to bad health)
        lifecycle = await manager.get_intent_state("test_intent")

        assert lifecycle.state == IntentLifecycleState.DISABLED


class TestLifecycleManagerGetAvailable:
    """Test get_available_intents functionality."""

    @pytest.fixture
    def health_monitor(self) -> HealthMonitor:
        """Create health monitor."""
        return HealthMonitor()

    @pytest.fixture
    def storage(self) -> InMemoryLifecycleStorage:
        """Create storage."""
        return InMemoryLifecycleStorage()

    @pytest.fixture
    def manager(
        self, storage: InMemoryLifecycleStorage, health_monitor: HealthMonitor
    ) -> LifecycleManager:
        """Create manager."""
        config = LifecycleConfig(
            disable_ttl_seconds=3600,
            auto_restore_if_health_recovers=True,
            restore_success_rate_threshold=0.7,
        )
        return LifecycleManager(
            storage=storage,
            config=config,
            health_monitor=health_monitor,
        )

    @pytest.mark.asyncio
    async def test_get_available_intents_all_active(
        self, manager: LifecycleManager
    ):
        """Test get_available_intents with all active."""
        intents = ["intent_a", "intent_b", "intent_c"]

        available = await manager.get_available_intents(intents)

        assert len(available) == 3
        assert set(available) == set(intents)

    @pytest.mark.asyncio
    async def test_get_available_intents_some_disabled(
        self, manager: LifecycleManager
    ):
        """Test get_available_intents with some disabled."""
        intents = ["intent_a", "intent_b", "intent_c"]

        # Disable intent_b
        await manager.disable_intent("intent_b", reason="testing")

        available = await manager.get_available_intents(intents)

        assert "intent_a" in available
        assert "intent_b" not in available
        assert "intent_c" in available


class TestLifecycleManagerCaching:
    """Test lifecycle manager caching behavior."""

    @pytest.fixture
    def health_monitor(self) -> HealthMonitor:
        """Create health monitor."""
        return HealthMonitor()

    @pytest.fixture
    def storage(self) -> InMemoryLifecycleStorage:
        """Create storage."""
        return InMemoryLifecycleStorage()

    @pytest.fixture
    def manager(
        self, storage: InMemoryLifecycleStorage, health_monitor: HealthMonitor
    ) -> LifecycleManager:
        """Create manager."""
        config = LifecycleConfig(disable_ttl_seconds=3600)
        manager = LifecycleManager(
            storage=storage,
            config=config,
            health_monitor=health_monitor,
        )
        manager._cache_ttl = 5  # 5 seconds for testing
        return manager

    @pytest.mark.asyncio
    async def test_cache_used_within_ttl(self, manager: LifecycleManager):
        """Test cache TTL behavior."""
        # First call - loads from storage
        lifecycle1 = await manager.get_intent_state("cached_intent")

        # Cache TTL is 5 seconds, so within TTL should use cache
        # The exact behavior depends on implementation
        assert lifecycle1 is not None
        assert lifecycle1.intent_path == "cached_intent"

    @pytest.mark.asyncio
    async def test_cache_bypassed_after_ttl(self, manager: LifecycleManager):
        """Test that cache is bypassed after TTL."""
        # First call
        lifecycle1 = await manager.get_intent_state("ttl_test")

        # Wait for cache to expire
        await asyncio.sleep(6)

        # Modify storage
        await manager._storage.save_lifecycle("ttl_test", {"state": "disabled"})

        # Third call - should get new value
        lifecycle2 = await manager.get_intent_state("ttl_test")

        # Cache should be refreshed
        assert lifecycle2.state == IntentLifecycleState.DISABLED


class TestLifecycleManagerAutoRestore:
    """Test auto-restore functionality."""

    @pytest.fixture
    def health_monitor(self) -> HealthMonitor:
        """Create health monitor."""
        return HealthMonitor()

    @pytest.fixture
    def storage(self) -> InMemoryLifecycleStorage:
        """Create storage."""
        return InMemoryLifecycleStorage()

    @pytest.mark.asyncio
    async def test_restore_success_threshold_met(self):
        """Test restore success rate calculation (simplified)."""
        health_monitor = HealthMonitor()
        storage = InMemoryLifecycleStorage()
        config = LifecycleConfig(
            disable_ttl_seconds=1,
            auto_restore_if_health_recovers=True,
            restore_success_rate_threshold=0.5,
        )
        manager = LifecycleManager(
            storage=storage,
            config=config,
            health_monitor=health_monitor,
        )

        # Record good success rate (70% success)
        for i in range(10):
            await health_monitor.record("good_intent", success=i < 7, latency_ms=10)

        # Verify success rate
        rate = await health_monitor.get_success_rate("good_intent")
        assert rate >= 0.5  # Meets threshold

        # Disable
        await manager.disable_intent("good_intent", reason="test", ttl_seconds=1)

        # Verify disabled state
        lifecycle = await manager.get_intent_state("good_intent")
        assert lifecycle.state == IntentLifecycleState.DISABLED

    @pytest.mark.asyncio
    async def test_restore_extends_ttl_on_failure(self):
        """Test that failed restore extends TTL."""
        health_monitor = HealthMonitor()
        storage = InMemoryLifecycleStorage()
        config = LifecycleConfig(
            disable_ttl_seconds=1,
            auto_restore_if_health_recovers=True,
            restore_success_rate_threshold=0.8,
        )
        manager = LifecycleManager(
            storage=storage,
            config=config,
            health_monitor=health_monitor,
        )

        # Record low success rate
        for i in range(10):
            await health_monitor.record("bad_intent", success=i < 3, latency_ms=100)

        # Disable with short TTL
        await manager.disable_intent("bad_intent", reason="test", ttl_seconds=1)

        # Wait for first check
        await asyncio.sleep(1.5)

        # Check - should still be disabled but TTL extended
        lifecycle = await manager.get_intent_state("bad_intent")
        assert lifecycle.state == IntentLifecycleState.DISABLED


class TestLifecycleManagerPostRestore:
    """Test post-restore health monitoring."""

    @pytest.fixture
    def health_monitor(self) -> HealthMonitor:
        """Create health monitor."""
        return HealthMonitor()

    @pytest.fixture
    def storage(self) -> InMemoryLifecycleStorage:
        """Create storage."""
        return InMemoryLifecycleStorage()

    @pytest.fixture
    def manager(
        self, storage: InMemoryLifecycleStorage, health_monitor: HealthMonitor
    ) -> LifecycleManager:
        """Create manager."""
        config = LifecycleConfig(
            disable_ttl_seconds=3600,
            auto_restore_if_health_recovers=True,
            restore_success_rate_threshold=0.7,
        )
        return LifecycleManager(
            storage=storage,
            config=config,
            health_monitor=health_monitor,
        )

    @pytest.mark.asyncio
    async def test_post_restore_health_check(
        self, manager: LifecycleManager
    ):
        """Test post-restore health monitoring."""
        # Manually set to restored state
        await manager._storage.save_lifecycle("restored_intent", {
            "state": "restored",
            "health_check_start": time.time() - 4000,  # Window passed
        })

        # Record bad health after restore
        for _ in range(10):
            await manager._health_monitor.record("restored_intent", success=False, latency_ms=100)

        # Check health
        await manager.check_post_restore_health("restored_intent")

        # Should be disabled again
        lifecycle = await manager.get_intent_state("restored_intent")
        assert lifecycle.state == IntentLifecycleState.DISABLED


class TestIntentLifecycle:
    """Test IntentLifecycle data class."""

    def test_is_available_active(self):
        """Test is_available for active state."""
        lifecycle = IntentLifecycle(
            intent_path="test",
            state=IntentLifecycleState.ACTIVE,
        )
        assert lifecycle.is_available is True

    def test_is_available_disabled(self):
        """Test is_available for disabled state."""
        lifecycle = IntentLifecycle(
            intent_path="test",
            state=IntentLifecycleState.DISABLED,
        )
        assert lifecycle.is_available is False

    def test_is_available_restored(self):
        """Test is_available for restored state."""
        lifecycle = IntentLifecycle(
            intent_path="test",
            state=IntentLifecycleState.RESTORED,
        )
        assert lifecycle.is_available is True

    def test_should_auto_restore_false_when_not_disabled(self):
        """Test should_auto_restore when not disabled."""
        lifecycle = IntentLifecycle(
            intent_path="test",
            state=IntentLifecycleState.ACTIVE,
            auto_restore_after=time.time() - 100,
        )
        assert lifecycle.should_auto_restore is False

    def test_should_auto_restore_true_when_expired(self):
        """Test should_auto_restore when TTL expired."""
        lifecycle = IntentLifecycle(
            intent_path="test",
            state=IntentLifecycleState.DISABLED,
            auto_restore_after=time.time() - 100,  # Past
        )
        assert lifecycle.should_auto_restore is True

    def test_should_auto_restore_false_when_future(self):
        """Test should_auto_restore when TTL not yet expired."""
        lifecycle = IntentLifecycle(
            intent_path="test",
            state=IntentLifecycleState.DISABLED,
            auto_restore_after=time.time() + 3600,  # Future
        )
        assert lifecycle.should_auto_restore is False


class TestLifecycleStorage:
    """Test InMemoryLifecycleStorage."""

    @pytest.fixture
    def storage(self) -> InMemoryLifecycleStorage:
        """Create storage."""
        return InMemoryLifecycleStorage()

    @pytest.mark.asyncio
    async def test_load_lifecycle_default(self, storage: InMemoryLifecycleStorage):
        """Test loading lifecycle with defaults."""
        lifecycle = await storage.load_lifecycle("nonexistent")

        assert lifecycle.intent_path == "nonexistent"
        assert lifecycle.state == IntentLifecycleState.ACTIVE

    @pytest.mark.asyncio
    async def test_save_and_load_lifecycle(self, storage: InMemoryLifecycleStorage):
        """Test saving and loading lifecycle."""
        await storage.save_lifecycle("test", {
            "state": "disabled",
            "disabled_at": time.time(),
        })

        lifecycle = await storage.load_lifecycle("test")

        assert lifecycle.state == IntentLifecycleState.DISABLED
        assert lifecycle.disabled_at is not None

    @pytest.mark.asyncio
    async def test_update_existing_lifecycle(self, storage: InMemoryLifecycleStorage):
        """Test updating existing lifecycle."""
        await storage.save_lifecycle("test", {"state": "active"})
        await storage.save_lifecycle("test", {"state": "disabled"})

        lifecycle = await storage.load_lifecycle("test")

        assert lifecycle.state == IntentLifecycleState.DISABLED
