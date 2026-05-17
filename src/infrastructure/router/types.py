"""Core types for Semantic Router."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

import numpy as np


class IntentLifecycleState(Enum):
    """Intent lifecycle states."""

    ACTIVE = "active"
    DISABLED = "disabled"
    PENDING_RESTORE = "pending"
    RESTORED = "restored"


class RoutingType(Enum):
    """Type of routing decision."""

    RULE = "rule"
    SEMANTIC = "semantic"
    FALLBACK = "fallback"


def _get_time() -> float:
    """Get current time (injectable for testing)."""
    import time

    return time.time()


@dataclass(frozen=True)
class Snapshot:
    """Frozen snapshot for immutable request context."""

    snapshot_id: str
    config: RouterConfig
    index: Any  # ANN index (read-only)
    frequency_version: int
    freq_snapshot_time: float
    created_at: float

    @property
    def intent_table(self) -> dict[str, IntentConfig]:
        """Get intent table from config."""
        return self.config.intents


@dataclass
class RequestContext:
    """
    Immutable request context containing frozen snapshot.
    
    Created once at route() start, passed through entire pipeline.
    No global state access allowed after creation.
    """

    context_id: str
    snapshot_id: str
    frozen_snapshot: Snapshot
    start_time: float
    request: Request
    metadata: dict[str, Any] = field(default_factory=dict)

    def with_metadata(self, key: str, value: Any) -> RequestContext:
        """Return new context with additional metadata (immutable pattern)."""
        return RequestContext(
            context_id=self.context_id,
            snapshot_id=self.snapshot_id,
            frozen_snapshot=self.frozen_snapshot,
            start_time=self.start_time,
            request=self.request,
            metadata={**self.metadata, key: value},
        )

    @classmethod
    def create(
        cls,
        snapshot: Snapshot,
        request: Request,
    ) -> RequestContext:
        """Factory method to create new context."""
        return cls(
            context_id=str(uuid.uuid4()),
            snapshot_id=snapshot.snapshot_id,
            frozen_snapshot=snapshot,
            start_time=_get_time(),
            request=request,
            metadata={},
        )


@dataclass
class Request:
    """Incoming routing request."""

    query: str
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class IntentConfig:
    """Configuration for an intent."""

    name: str
    base_score: float = 0.5
    priority: int = 5
    handler: Optional[str] = None
    rules: list[RoutingRule] = field(default_factory=list)
    frequency: int = 0


@dataclass
class RoutingRule:
    """Rule for intent matching."""

    pattern: str
    intent: str
    confidence: float = 1.0
    needs_semantic: bool = False
    priority: int = 0

    def matches(self, request: "Request") -> bool:
        """Check if request matches this rule's pattern."""
        import re

        query = request.query.lower()
        pattern = self.pattern.lower()

        if re.search(pattern, query, re.IGNORECASE):
            return True
        return False


@dataclass
class ConsistencyConfig:
    """Configuration for read-after-write consistency."""

    read_after_write_guard_ms: int = 5000
    force_new_snapshot_on_feedback: bool = False
    warn_on_stale_snapshot: bool = True


@dataclass
class BoostFairnessConfig:
    """Configuration for boost budget fairness."""

    enabled: bool = True
    per_intent_weight_cap: float = 0.30
    min_share_per_intent: float = 0.01
    global_boost_per_second: int = 1000


@dataclass
class LifecycleConfig:
    """Configuration for intent lifecycle."""

    disable_ttl_seconds: int = 86400
    auto_restore_if_health_recovers: bool = True
    restore_success_rate_threshold: float = 0.7
    restore_observation_window_hours: int = 1


@dataclass
class RouterConfig:
    """Main router configuration."""

    default_intent: str = "unknown"
    fallback_enabled: bool = True
    intents: dict[str, IntentConfig] = field(default_factory=dict)
    consistency: ConsistencyConfig = field(default_factory=ConsistencyConfig)
    boost_fairness: BoostFairnessConfig = field(default_factory=BoostFairnessConfig)
    lifecycle: LifecycleConfig = field(default_factory=LifecycleConfig)


@dataclass
class IntentLifecycle:
    """Lifecycle state for an intent."""

    intent_path: str
    state: IntentLifecycleState = IntentLifecycleState.ACTIVE
    disabled_at: Optional[float] = None
    disable_ttl_seconds: int = 86400
    auto_restore_after: Optional[float] = None
    health_check_start: Optional[float] = None
    health_check_window_hours: int = 1
    recent_success_rates: list[float] = field(default_factory=list)

    @property
    def is_available(self) -> bool:
        """Check if intent is available for routing."""
        return self.state in (
            IntentLifecycleState.ACTIVE,
            IntentLifecycleState.RESTORED,
        )

    @property
    def should_auto_restore(self) -> bool:
        """Check if intent should auto-restore."""
        if self.state != IntentLifecycleState.DISABLED:
            return False
        if self.auto_restore_after is None:
            return False
        return _get_time() >= self.auto_restore_after


@dataclass
class PolicyResult:
    """Result from policy engine evaluation."""

    intent: Optional[str] = None
    confidence: float = 0.0
    needs_semantic: bool = True
    routing_type: RoutingType = RoutingType.SEMANTIC
    handler: Optional[str] = None
    scores: Optional[dict[str, float]] = None


@dataclass
class RouteResult:
    """Final routing result."""

    intent: str
    confidence: float
    handler: Optional[str] = None
    all_scores: Optional[dict[str, float]] = None
    routing_type: RoutingType = RoutingType.SEMANTIC


@dataclass
class ExecutionResult:
    """Result from execution."""

    success: bool
    intent: Optional[str] = None
    result: Any = None
    error: Optional[str] = None
    latency_ms: float = 0.0


@dataclass
class Feedback:
    """Feedback for learning."""

    query: str
    intent_path: str
    example_text: str
    success: bool
    timestamp: float = field(default_factory=_get_time)


@dataclass
class FeedbackResult:
    """Result from feedback processing."""

    success: bool
    was_idempotent: bool = False
    new_snapshot_id: Optional[str] = None


def _get_time() -> float:
    """Get current time (injectable for testing)."""
    import time

    return time.time()
