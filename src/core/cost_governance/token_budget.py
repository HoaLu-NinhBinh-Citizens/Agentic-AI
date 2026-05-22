"""Token Budget - per-session, per-user limits.

Manages token usage quotas for cost control.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class BudgetScope(str, Enum):
    """Budget scope types."""

    SESSION = "session"
    USER = "user"
    GLOBAL = "global"


@dataclass
class BudgetConfig:
    """Configuration for token budget."""

    max_tokens: int = 100000
    scope: BudgetScope = BudgetScope.SESSION
    warning_threshold: float = 0.8
    reset_interval_seconds: int = 3600


@dataclass
class BudgetResult:
    """Result of a budget check operation."""

    allowed: bool
    reason: str
    remaining_tokens: int
    usage_percent: float

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "remaining_tokens": self.remaining_tokens,
            "usage_percent": self.usage_percent,
        }


class TokenBudget:
    """Manages token usage budgets for sessions and users.

    Features:
    - Per-session budget tracking
    - Per-user budget aggregation
    - Global budget limits
    - Warning thresholds
    - Automatic reset
    """

    def __init__(
        self,
        config: BudgetConfig | None = None,
    ) -> None:
        """Initialize token budget manager.

        Args:
            config: Budget configuration.
        """
        self._config = config or BudgetConfig()
        self._session_budgets: dict[str, int] = {}
        self._user_budgets: dict[str, int] = {}
        self._global_usage = 0
        self._session_reset_times: dict[str, int] = {}
        self._lock = asyncio.Lock()

    @property
    def config(self) -> BudgetConfig:
        """Get budget configuration."""
        return self._config

    async def check_and_consume(
        self,
        session_id: str,
        tokens: int,
        user_id: str | None = None,
    ) -> BudgetResult:
        """Check budget and consume tokens if allowed.

        Args:
            session_id: Session identifier.
            tokens: Number of tokens to consume.
            user_id: Optional user identifier.

        Returns:
            BudgetResult with consumption status.
        """
        async with self._lock:
            self._maybe_reset_session(session_id)

            current_usage = self._session_budgets.get(session_id, 0)
            new_usage = current_usage + tokens

            usage_percent = new_usage / self._config.max_tokens

            if new_usage > self._config.max_tokens:
                logger.warning(
                    "Budget exceeded: session=%s usage=%d limit=%d",
                    session_id,
                    new_usage,
                    self._config.max_tokens,
                )
                return BudgetResult(
                    allowed=False,
                    reason=f"Budget exceeded: {new_usage}/{self._config.max_tokens} tokens",
                    remaining_tokens=max(0, self._config.max_tokens - current_usage),
                    usage_percent=current_usage / self._config.max_tokens,
                )

            if usage_percent >= self._config.warning_threshold:
                logger.warning(
                    "Budget warning: session=%s usage=%.1f%%",
                    session_id,
                    usage_percent * 100,
                )

            self._session_budgets[session_id] = new_usage
            self._global_usage += tokens

            if user_id:
                self._user_budgets[user_id] = self._user_budgets.get(user_id, 0) + tokens

            logger.debug(
                "Tokens consumed: session=%s tokens=%d total=%d/%d",
                session_id,
                tokens,
                new_usage,
                self._config.max_tokens,
            )

            return BudgetResult(
                allowed=True,
                reason="Tokens consumed successfully",
                remaining_tokens=self._config.max_tokens - new_usage,
                usage_percent=usage_percent,
            )

    async def check(
        self,
        session_id: str,
        tokens: int,
    ) -> BudgetResult:
        """Check if budget allows consumption without consuming.

        Args:
            session_id: Session identifier.
            tokens: Number of tokens to check.

        Returns:
            BudgetResult with check status.
        """
        async with self._lock:
            self._maybe_reset_session(session_id)

            current_usage = self._session_budgets.get(session_id, 0)
            new_usage = current_usage + tokens
            usage_percent = new_usage / self._config.max_tokens

            if new_usage > self._config.max_tokens:
                return BudgetResult(
                    allowed=False,
                    reason=f"Would exceed budget: {new_usage}/{self._config.max_tokens}",
                    remaining_tokens=max(0, self._config.max_tokens - current_usage),
                    usage_percent=current_usage / self._config.max_tokens,
                )

            return BudgetResult(
                allowed=True,
                reason="Budget allows consumption",
                remaining_tokens=self._config.max_tokens - new_usage,
                usage_percent=usage_percent,
            )

    async def get_session_usage(self, session_id: str) -> tuple[int, int]:
        """Get session token usage.

        Args:
            session_id: Session identifier.

        Returns:
            Tuple of (used_tokens, limit).
        """
        async with self._lock:
            self._maybe_reset_session(session_id)
            used = self._session_budgets.get(session_id, 0)
            return used, self._config.max_tokens

    async def get_user_usage(self, user_id: str) -> int:
        """Get aggregated user token usage.

        Args:
            user_id: User identifier.

        Returns:
            Total tokens used by user.
        """
        async with self._lock:
            return self._user_budgets.get(user_id, 0)

    def _maybe_reset_session(self, session_id: str) -> None:
        """Reset session budget if interval has passed."""
        current_time = int(time.time())
        reset_time = self._session_reset_times.get(session_id, 0)

        if current_time >= reset_time + self._config.reset_interval_seconds:
            self._session_budgets[session_id] = 0
            self._session_reset_times[session_id] = current_time

    async def reset_session(self, session_id: str) -> None:
        """Manually reset session budget.

        Args:
            session_id: Session identifier.
        """
        async with self._lock:
            self._session_budgets[session_id] = 0
            self._session_reset_times[session_id] = int(time.time())
            logger.info("Session budget reset: session=%s", session_id)

    async def reset_all(self) -> None:
        """Reset all budgets."""
        async with self._lock:
            self._session_budgets.clear()
            self._user_budgets.clear()
            self._global_usage = 0
            self._session_reset_times.clear()
            logger.info("All budgets reset")

    async def get_stats(self) -> dict[str, Any]:
        """Get budget statistics.

        Returns:
            Statistics dictionary.
        """
        async with self._lock:
            session_count = len(self._session_budgets)
            total_session_usage = sum(self._session_budgets.values())

            return {
                "config": {
                    "max_tokens": self._config.max_tokens,
                    "scope": self._config.scope.value,
                    "warning_threshold": self._config.warning_threshold,
                    "reset_interval_seconds": self._config.reset_interval_seconds,
                },
                "sessions": session_count,
                "users": len(self._user_budgets),
                "total_session_usage": total_session_usage,
                "global_usage": self._global_usage,
                "avg_usage_percent": (
                    (total_session_usage / session_count / self._config.max_tokens * 100)
                    if session_count > 0
                    else 0
                ),
            }
