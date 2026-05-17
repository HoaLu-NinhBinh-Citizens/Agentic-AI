"""Core types for Tool Cache System."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Literal, Optional

import numpy as np


class KeyState(IntEnum):
    """Cache key states with strict transition priority.

    Priority: DEGRADED > REFRESHING > STALE > FRESH > LOADING > MISS
    """

    MISS = 0
    LOADING = 1
    FRESH = 2
    STALE = 3
    REFRESHING = 4
    DEGRADED = 5
    COOLDOWN = 6

    def __ge__(self, other: KeyState) -> bool:
        return self.value >= other.value

    def __gt__(self, other: KeyState) -> bool:
        return self.value > other.value

    def __le__(self, other: KeyState) -> bool:
        return self.value <= other.value

    def __lt__(self, other: KeyState) -> bool:
        return self.value < other.value


class ValidationReason(IntEnum):
    """Reason for cache validation failure."""

    VALID = 0
    NOT_CACHEABLE = 1
    VALIDATION_FAILED = 2
    SIZE_LIMIT_EXCEEDED = 3
    SERIALIZATION_ERROR = 4


class LoadState(IntEnum):
    """System load state."""

    NORMAL = 0
    ELEVATED = 1
    DEGRADED = 2


@dataclass(frozen=True)
class CacheResponse:
    """Response from cache operations.

    This is the contract for all cache interactions.
    State meanings:
    - HIT: Safe direct use
    - STALE: Usable + may refresh
    - MISS: Must call tool
    - DEGRADED: Cache unreliable, avoid dependency
    """

    value: Any | None
    state: Literal["HIT", "MISS", "STALE", "DEGRADED"]
    reason: Optional[str] = None
    key_state: KeyState = KeyState.MISS
    expires_at: Optional[float] = None

    @classmethod
    def hit(cls, value: Any, expires_at: Optional[float] = None) -> CacheResponse:
        """Create a HIT response."""
        return cls(
            value=value,
            state="HIT",
            reason=None,
            key_state=KeyState.FRESH,
            expires_at=expires_at,
        )

    @classmethod
    def miss(cls, reason: Optional[str] = None) -> CacheResponse:
        """Create a MISS response."""
        return cls(
            value=None,
            state="MISS",
            reason=reason or "Key not found in cache",
            key_state=KeyState.MISS,
        )

    @classmethod
    def stale(
        cls,
        value: Any,
        expires_at: float,
        reason: Optional[str] = None,
    ) -> CacheResponse:
        """Create a STALE response."""
        return cls(
            value=value,
            state="STALE",
            reason=reason or "TTL expired",
            key_state=KeyState.STALE,
            expires_at=expires_at,
        )

    @classmethod
    def degraded(
        cls,
        reason: Optional[str] = None,
        value: Any | None = None,
    ) -> CacheResponse:
        """Create a DEGRADED response."""
        return cls(
            value=value,
            state="DEGRADED",
            reason=reason or "System overload",
            key_state=KeyState.DEGRADED,
        )

    def is_safe_to_use(self) -> bool:
        """Check if response value is safe to use directly."""
        return self.state in ("HIT", "STALE")

    def needs_refresh(self) -> bool:
        """Check if refresh should be triggered."""
        return self.state == "STALE"


@dataclass
class CacheEntry:
    """Internal cache entry with metadata."""

    key: str
    value: Any
    state: KeyState = KeyState.MISS
    created_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None
    last_accessed: float = field(default_factory=time.time)
    access_count: int = 0
    hit_count: int = 0
    miss_count: int = 0
    refresh_count: int = 0
    failure_count: int = 0
    size_bytes: int = 0
    is_pinned: bool = False
    version: int = 1
    vector_clock: dict[str, int] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def touch(self) -> None:
        """Update access metadata."""
        self.last_accessed = time.time()
        self.access_count += 1

    def record_hit(self) -> None:
        """Record a cache hit."""
        self.touch()
        self.hit_count += 1

    def record_miss(self) -> None:
        """Record a cache miss."""
        self.touch()
        self.miss_count += 1

    def is_expired(self) -> bool:
        """Check if entry is expired."""
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at

    def is_stale(self) -> bool:
        """Check if entry is stale (TTL expired)."""
        return self.state == KeyState.STALE or self.is_expired()

    def age(self) -> float:
        """Get entry age in seconds."""
        return time.time() - self.created_at

    def time_to_expiry(self) -> float:
        """Get time until expiry in seconds."""
        if self.expires_at is None:
            return float("inf")
        return max(0, self.expires_at - time.time())


@dataclass
class CacheKey:
    """Canonical cache key structure."""

    tool: str
    version: str
    args: tuple[tuple[str, Any], ...]

    def __hash__(self) -> int:
        return hash((self.tool, self.version, self.args))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CacheKey):
            return False
        return (
            self.tool == other.tool
            and self.version == other.version
            and self.args == other.args
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "tool": self.tool,
            "version": self.version,
            "args": dict(self.args),
        }


@dataclass
class CacheStats:
    """Cache statistics snapshot."""

    hits: int = 0
    misses: int = 0
    evictions: int = 0
    refreshes: int = 0
    failures: int = 0
    size: int = 0
    max_size: int = 0
    memory_bytes: int = 0
    max_memory_bytes: int = 0
    hit_ratio: float = 0.0
    pending_keys: int = 0
    load_state: LoadState = LoadState.NORMAL
    timestamp: float = field(default_factory=time.time)

    @property
    def total_requests(self) -> int:
        """Total cache requests."""
        return self.hits + self.misses

    def compute_hit_ratio(self) -> float:
        """Compute hit ratio from current stats."""
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0


@dataclass
class ThresholdMetrics:
    """Metrics for adaptive threshold engine."""

    memory_pressure: float = 0.0
    pending_keys: int = 0
    queue_saturation: float = 0.0
    error_rate: float = 0.0
    timestamp: float = field(default_factory=time.time)

    def is_overloaded(self, threshold: float) -> bool:
        """Check if system is overloaded."""
        return self.memory_pressure > threshold

    def is_recovery_window(self, threshold: float, windows: int = 3) -> bool:
        """Check if in recovery window (for DEGRADED exit)."""
        return (
            self.memory_pressure < threshold * 0.8
            and self.pending_keys < threshold * 0.8
            and self.error_rate < 0.05
        )


@dataclass
class RefreshToken:
    """Token for tracking refresh operations."""

    key: str
    tool: str
    started_at: float
    attempt: int = 1
    cooldown_until: Optional[float] = None

    def is_in_cooldown(self) -> bool:
        """Check if in cooldown period."""
        if self.cooldown_until is None:
            return False
        return time.time() < self.cooldown_until

    def set_cooldown(self, duration: float = 300.0) -> None:
        """Set cooldown period (default 5 minutes)."""
        self.cooldown_until = time.time() + duration


@dataclass
class ValidationResult:
    """Result of poison validation."""

    valid: bool
    reason: ValidationReason
    message: Optional[str] = None

    @classmethod
    def success(cls) -> ValidationResult:
        """Create successful validation result."""
        return cls(valid=True, reason=ValidationReason.VALID, message=None)

    @classmethod
    def failure(
        cls,
        reason: ValidationReason,
        message: Optional[str] = None,
    ) -> ValidationResult:
        """Create failed validation result."""
        return cls(valid=False, reason=reason, message=message)


class VectorClock:
    """Vector clock for reconciliation."""

    def __init__(self) -> None:
        self._clock: dict[str, int] = {}

    def increment(self, node_id: str) -> None:
        """Increment clock for node."""
        self._clock[node_id] = self._clock.get(node_id, 0) + 1

    def merge(self, other: dict[str, int]) -> None:
        """Merge another vector clock."""
        for node_id, value in other.items():
            self._clock[node_id] = max(self._clock.get(node_id, 0), value)

    def happens_before(self, other: "VectorClock") -> bool:
        """Check if self happens-before other.

        Self happens-before other if:
        - All values in other >= values in self (for common keys)
        - AND at least one value in other > corresponding value in self
        """
        self_less = False
        for node_id, value in self._clock.items():
            other_value = other._clock.get(node_id, 0)
            if value > other_value:
                return False
            if value < other_value:
                self_less = True

        if self_less:
            return True

        for node_id, other_value in other._clock.items():
            if node_id not in self._clock and other_value > 0:
                return True

        return False

    def is_concurrent(self, other: VectorClock) -> bool:
        """Check if clocks are concurrent."""
        return not self.happens_before(other) and not other.happens_before(self)

    def to_dict(self) -> dict[str, int]:
        """Convert to dictionary."""
        return dict(self._clock)

    @classmethod
    def from_dict(cls, data: dict[str, int]) -> VectorClock:
        """Create from dictionary."""
        vc = cls()
        vc._clock = dict(data)
        return vc
