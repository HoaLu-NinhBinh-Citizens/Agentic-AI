"""Unit tests for cache types."""

import time
import pytest

from src.infrastructure.cache.tool.types import (
    CacheEntry,
    CacheResponse,
    CacheStats,
    KeyState,
    ValidationReason,
    ValidationResult,
    VectorClock,
)


class TestKeyState:
    """Tests for KeyState enum."""

    def test_state_ordering(self):
        """Test that states have correct ordering."""
        assert KeyState.MISS < KeyState.LOADING
        assert KeyState.LOADING < KeyState.FRESH
        assert KeyState.FRESH < KeyState.STALE
        assert KeyState.STALE < KeyState.REFRESHING
        assert KeyState.REFRESHING < KeyState.DEGRADED
        assert KeyState.DEGRADED < KeyState.COOLDOWN

    def test_state_comparison(self):
        """Test state comparisons."""
        assert KeyState.FRESH >= KeyState.LOADING
        assert KeyState.DEGRADED > KeyState.FRESH
        assert KeyState.MISS <= KeyState.MISS


class TestCacheResponse:
    """Tests for CacheResponse."""

    def test_hit_response(self):
        """Test creating a HIT response."""
        response = CacheResponse.hit("value", expires_at=1000.0)

        assert response.value == "value"
        assert response.state == "HIT"
        assert response.reason is None
        assert response.key_state == KeyState.FRESH
        assert response.expires_at == 1000.0

    def test_miss_response(self):
        """Test creating a MISS response."""
        response = CacheResponse.miss()

        assert response.value is None
        assert response.state == "MISS"
        assert response.reason == "Key not found in cache"
        assert response.key_state == KeyState.MISS

    def test_stale_response(self):
        """Test creating a STALE response."""
        response = CacheResponse.stale("value", expires_at=1000.0)

        assert response.value == "value"
        assert response.state == "STALE"
        assert response.reason == "TTL expired"
        assert response.key_state == KeyState.STALE

    def test_degraded_response(self):
        """Test creating a DEGRADED response."""
        response = CacheResponse.degraded(reason="System overload")

        assert response.value is None
        assert response.state == "DEGRADED"
        assert response.reason == "System overload"
        assert response.key_state == KeyState.DEGRADED

    def test_is_safe_to_use(self):
        """Test is_safe_to_use method."""
        assert CacheResponse.hit("value").is_safe_to_use()
        assert CacheResponse.stale("value", expires_at=0).is_safe_to_use()
        assert not CacheResponse.miss().is_safe_to_use()
        assert not CacheResponse.degraded().is_safe_to_use()

    def test_needs_refresh(self):
        """Test needs_refresh method."""
        assert CacheResponse.stale("value", expires_at=0).needs_refresh()
        assert not CacheResponse.hit("value").needs_refresh()
        assert not CacheResponse.miss().needs_refresh()


class TestCacheEntry:
    """Tests for CacheEntry."""

    def test_create_entry(self):
        """Test creating a cache entry."""
        entry = CacheEntry(
            key="test_key",
            value={"data": "value"},
        )

        assert entry.key == "test_key"
        assert entry.value == {"data": "value"}
        assert entry.state == KeyState.MISS
        assert entry.access_count == 0
        assert entry.hit_count == 0
        assert entry.miss_count == 0

    def test_touch(self):
        """Test touch updates access metadata."""
        entry = CacheEntry(key="test", value="value")

        initial_access = entry.access_count
        entry.touch()

        assert entry.access_count == initial_access + 1
        assert entry.last_accessed >= entry.created_at

    def test_record_hit(self):
        """Test record_hit increments counters."""
        entry = CacheEntry(key="test", value="value")

        entry.record_hit()
        entry.record_hit()

        assert entry.hit_count == 2
        assert entry.access_count == 2

    def test_record_miss(self):
        """Test record_miss increments counters."""
        entry = CacheEntry(key="test", value="value")

        entry.record_miss()

        assert entry.miss_count == 1
        assert entry.access_count == 1

    def test_is_expired(self):
        """Test is_expired checks TTL."""
        entry = CacheEntry(
            key="test",
            value="value",
            expires_at=time.time() - 1,
        )

        assert entry.is_expired()

        entry2 = CacheEntry(
            key="test",
            value="value",
            expires_at=time.time() + 100,
        )

        assert not entry2.is_expired()

    def test_time_to_expiry(self):
        """Test time_to_expiry calculation."""
        entry = CacheEntry(
            key="test",
            value="value",
            expires_at=time.time() + 60,
        )

        ttl = entry.time_to_expiry()
        assert 59 <= ttl <= 61

    def test_is_stale(self):
        """Test is_stale checks state and TTL."""
        entry = CacheEntry(
            key="test",
            value="value",
            state=KeyState.STALE,
        )

        assert entry.is_stale()


class TestVectorClock:
    """Tests for VectorClock."""

    def test_increment(self):
        """Test incrementing clock."""
        vc = VectorClock()
        vc.increment("node1")

        assert vc.to_dict()["node1"] == 1

        vc.increment("node1")
        assert vc.to_dict()["node1"] == 2

    def test_merge(self):
        """Test merging clocks."""
        vc1 = VectorClock()
        vc1.increment("node1")
        vc1.increment("node1")

        vc2 = VectorClock()
        vc2.increment("node1")
        vc2.increment("node2")

        vc1.merge(vc2.to_dict())

        assert vc1.to_dict()["node1"] == 2
        assert vc1.to_dict()["node2"] == 1

    def test_happens_before(self):
        """Test happens_before comparison."""
        vc1 = VectorClock()
        vc1.increment("node1")

        vc2 = VectorClock()
        vc2.increment("node1")
        vc2.increment("node2")

        assert vc1.happens_before(vc2)
        assert not vc2.happens_before(vc1)

    def test_is_concurrent(self):
        """Test concurrent detection."""
        vc1 = VectorClock()
        vc1.increment("node1")

        vc2 = VectorClock()
        vc2.increment("node2")

        assert vc1.is_concurrent(vc2)

    def test_from_dict(self):
        """Test creating from dictionary."""
        data = {"node1": 1, "node2": 2}
        vc = VectorClock.from_dict(data)

        assert vc.to_dict() == data


class TestValidationResult:
    """Tests for ValidationResult."""

    def test_success(self):
        """Test success validation result."""
        result = ValidationResult.success()

        assert result.valid is True
        assert result.reason == ValidationReason.VALID
        assert result.message is None

    def test_failure(self):
        """Test failed validation result."""
        result = ValidationResult.failure(
            ValidationReason.VALIDATION_FAILED,
            "Invalid data",
        )

        assert result.valid is False
        assert result.reason == ValidationReason.VALIDATION_FAILED
        assert result.message == "Invalid data"
