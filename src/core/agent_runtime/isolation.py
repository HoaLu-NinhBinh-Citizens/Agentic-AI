"""Failure Isolation - agent crash handling, retry boundaries.

Provides failure isolation for agent execution:
- Crash detection and handling
- Retry boundary management
- Error classification
- Graceful degradation
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ErrorSeverity(str, Enum):
    """Error severity levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorCategory(str, Enum):
    """Error categories for classification."""

    TRANSIENT = "transient"
    RESOURCE = "resource"
    TIMEOUT = "timeout"
    VALIDATION = "validation"
    PERMISSION = "permission"
    SYSTEM = "system"
    UNKNOWN = "unknown"


@dataclass
class ErrorInfo:
    """Information about an error."""

    message: str
    category: ErrorCategory
    severity: ErrorSeverity
    timestamp: int
    is_retryable: bool
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class IsolationBoundary:
    """Boundary for failure isolation."""

    boundary_id: str
    agent_id: str
    created_at: int
    errors: list[ErrorInfo] = field(default_factory=list)
    is_isolated: bool = False
    retries: int = 0

    def add_error(self, error: ErrorInfo) -> None:
        """Add an error to the boundary."""
        self.errors.append(error)
        if error.severity == ErrorSeverity.CRITICAL:
            self.is_isolated = True


@dataclass
class RetryBoundary:
    """Boundary for retry management."""

    boundary_id: str
    max_retries: int
    retry_count: int = 0
    backoff_seconds: float = 1.0
    max_backoff: float = 60.0

    def can_retry(self) -> bool:
        """Check if retry is allowed."""
        return self.retry_count < self.max_retries

    def record_retry(self) -> bool:
        """Record a retry attempt.

        Returns:
            True if retry was recorded, False if max reached.
        """
        if not self.can_retry():
            return False
        self.retry_count += 1
        self.backoff_seconds = min(self.backoff_seconds * 2, self.max_backoff)
        return True

    def get_backoff(self) -> float:
        """Get current backoff delay."""
        return self.backoff_seconds


class FailureIsolation:
    """Manages failure isolation for agent execution.

    Features:
    - Error classification
    - Retry boundary management
    - Crash detection
    - Graceful degradation
    """

    def __init__(
        self,
        max_retries: int = 3,
        isolation_threshold: int = 5,
    ) -> None:
        """Initialize failure isolation.

        Args:
            max_retries: Maximum retry attempts per boundary.
            isolation_threshold: Number of errors before isolation.
        """
        self._max_retries = max_retries
        self._isolation_threshold = isolation_threshold
        self._boundaries: dict[str, IsolationBoundary] = {}
        self._retry_boundaries: dict[str, RetryBoundary] = {}
        self._lock = asyncio.Lock()

    def classify_error(self, error: Exception) -> ErrorInfo:
        """Classify an error.

        Args:
            error: Exception to classify.

        Returns:
            ErrorInfo with classification.
        """
        error_type = type(error).__name__
        message = str(error)

        if "timeout" in message.lower() or "Timeout" in error_type:
            category = ErrorCategory.TIMEOUT
            severity = ErrorSeverity.MEDIUM
            is_retryable = True
        elif "memory" in message.lower() or "MemoryError" in error_type:
            category = ErrorCategory.RESOURCE
            severity = ErrorSeverity.HIGH
            is_retryable = False
        elif "permission" in message.lower() or "Permission" in error_type:
            category = ErrorCategory.PERMISSION
            severity = ErrorSeverity.HIGH
            is_retryable = False
        elif "validate" in message.lower() or "Validation" in error_type:
            category = ErrorCategory.VALIDATION
            severity = ErrorSeverity.MEDIUM
            is_retryable = False
        elif "network" in message.lower() or "Connection" in error_type:
            category = ErrorCategory.TRANSIENT
            severity = ErrorSeverity.MEDIUM
            is_retryable = True
        else:
            category = ErrorCategory.UNKNOWN
            severity = ErrorSeverity.MEDIUM
            is_retryable = True

        return ErrorInfo(
            message=message,
            category=category,
            severity=severity,
            timestamp=int(time.time()),
            is_retryable=is_retryable,
            details={"error_type": error_type},
        )

    async def create_boundary(self, agent_id: str) -> IsolationBoundary:
        """Create an isolation boundary for an agent.

        Args:
            agent_id: Agent identifier.

        Returns:
            Created isolation boundary.
        """
        async with self._lock:
            boundary = IsolationBoundary(
                boundary_id=f"{agent_id}_{int(time.time())}",
                agent_id=agent_id,
                created_at=int(time.time()),
            )
            self._boundaries[agent_id] = boundary

            retry_boundary = RetryBoundary(
                boundary_id=boundary.boundary_id,
                max_retries=self._max_retries,
            )
            self._retry_boundaries[agent_id] = retry_boundary

            logger.info("Created isolation boundary: agent=%s id=%s", agent_id, boundary.boundary_id)
            return boundary

    async def record_error(self, agent_id: str, error: Exception) -> ErrorInfo:
        """Record an error for an agent.

        Args:
            agent_id: Agent identifier.
            error: Exception that occurred.

        Returns:
            ErrorInfo with classification.
        """
        async with self._lock:
            error_info = self.classify_error(error)

            boundary = self._boundaries.get(agent_id)
            if boundary:
                boundary.add_error(error_info)

                if len(boundary.errors) >= self._isolation_threshold:
                    boundary.is_isolated = True
                    logger.warning(
                        "Agent isolated: agent=%s errors=%d",
                        agent_id,
                        len(boundary.errors),
                    )

            logger.debug(
                "Error recorded: agent=%s category=%s severity=%s retryable=%s",
                agent_id,
                error_info.category.value,
                error_info.severity.value,
                error_info.is_retryable,
            )

            return error_info

    async def should_isolate(self, agent_id: str) -> bool:
        """Check if agent should be isolated.

        Args:
            agent_id: Agent identifier.

        Returns:
            True if agent should be isolated.
        """
        boundary = self._boundaries.get(agent_id)
        if not boundary:
            return False
        return boundary.is_isolated

    async def can_retry(self, agent_id: str) -> tuple[bool, float]:
        """Check if agent can retry and get backoff.

        Args:
            agent_id: Agent identifier.

        Returns:
            Tuple of (can_retry, backoff_seconds).
        """
        retry_boundary = self._retry_boundaries.get(agent_id)
        if not retry_boundary:
            return True, 0.0

        can_retry = retry_boundary.can_retry()
        backoff = retry_boundary.get_backoff() if can_retry else 0.0
        return can_retry, backoff

    async def record_retry(self, agent_id: str) -> bool:
        """Record a retry attempt.

        Args:
            agent_id: Agent identifier.

        Returns:
            True if retry was recorded, False if max reached.
        """
        async with self._lock:
            retry_boundary = self._retry_boundaries.get(agent_id)
            if not retry_boundary:
                retry_boundary = RetryBoundary(
                    boundary_id=f"{agent_id}_{int(time.time())}",
                    max_retries=self._max_retries,
                )
                self._retry_boundaries[agent_id] = retry_boundary

            recorded = retry_boundary.record_retry()
            if recorded:
                logger.info(
                    "Retry recorded: agent=%s count=%d/%d backoff=%.1fs",
                    agent_id,
                    retry_boundary.retry_count,
                    retry_boundary.max_retries,
                    retry_boundary.backoff_seconds,
                )
            else:
                logger.warning(
                    "Max retries reached: agent=%s",
                    agent_id,
                )

            return recorded

    async def reset(self, agent_id: str) -> bool:
        """Reset isolation for an agent.

        Args:
            agent_id: Agent identifier.

        Returns:
            True if reset successfully.
        """
        async with self._lock:
            if agent_id in self._boundaries:
                self._boundaries[agent_id].errors.clear()
                self._boundaries[agent_id].is_isolated = False
                self._boundaries[agent_id].retries = 0

            if agent_id in self._retry_boundaries:
                self._retry_boundaries[agent_id].retry_count = 0
                self._retry_boundaries[agent_id].backoff_seconds = 1.0

            logger.info("Reset isolation: agent=%s", agent_id)
            return True

    async def get_boundary(self, agent_id: str) -> IsolationBoundary | None:
        """Get isolation boundary for an agent.

        Args:
            agent_id: Agent identifier.

        Returns:
            IsolationBoundary or None if not found.
        """
        return self._boundaries.get(agent_id)

    async def get_stats(self) -> dict[str, Any]:
        """Get failure isolation statistics.

        Returns:
            Statistics dictionary.
        """
        isolated_count = sum(1 for b in self._boundaries.values() if b.is_isolated)
        total_errors = sum(len(b.errors) for b in self._boundaries.values())
        total_retries = sum(b.retry_count for b in self._retry_boundaries.values())

        error_categories: dict[str, int] = {}
        error_severities: dict[str, int] = {}

        for boundary in self._boundaries.values():
            for error in boundary.errors:
                cat = error.category.value
                sev = error.severity.value
                error_categories[cat] = error_categories.get(cat, 0) + 1
                error_severities[sev] = error_severities.get(sev, 0) + 1

        return {
            "total_boundaries": len(self._boundaries),
            "isolated_agents": isolated_count,
            "total_errors": total_errors,
            "total_retries": total_retries,
            "error_categories": error_categories,
            "error_severities": error_severities,
            "isolation_threshold": self._isolation_threshold,
            "max_retries": self._max_retries,
        }
