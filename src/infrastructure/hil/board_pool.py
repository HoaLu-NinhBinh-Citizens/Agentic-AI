"""Board pool with automatic replacement (Phase 7.6a).

Provides automatic board pool management:
- Auto-detection of failed boards
- Hot-swap board replacement
- Pool health monitoring
- Reserve board management
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class PoolState(Enum):
    """Board pool state."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    RECOVERING = "recovering"


@dataclass
class BoardPoolConfig:
    """Board pool configuration."""
    min_boards: int = 2
    max_boards: int = 10
    reserve_ratio: float = 0.2  # Keep 20% in reserve
    health_check_interval_seconds: int = 60
    replacement_timeout_minutes: int = 30
    auto_replacement_enabled: bool = True
    alert_threshold: float = 0.5  # Alert when available < 50%


@dataclass
class PoolStatistics:
    """Pool statistics."""
    total_boards: int
    available: int
    in_use: int
    maintenance: int
    failed: int
    reserve: int
    
    availability_rate: float
    utilization_rate: float
    avg_wait_time_seconds: float


@dataclass
class ReplacementEvent:
    """Board replacement event."""
    event_id: str
    failed_board_id: str
    replacement_board_id: str | None
    status: str  # pending, completed, failed
    triggered_at: datetime
    completed_at: datetime | None = None
    reason: str = ""


class BoardPool:
    """Board pool with auto-replacement.
    
    Phase 7.6a: Board pool - Auto-replacement
    """
    
    def __init__(self, config: BoardPoolConfig | None = None) -> None:
        self._config = config or BoardPoolConfig()
        
        # Boards
        self._available: list[str] = []  # Board IDs
        self._in_use: dict[str, str] = {}  # board_id -> user
        self._maintenance: list[str] = []
        self._failed: list[str] = []
        self._reserve: list[str] = []  # Reserve boards
        self._pending_replacement: dict[str, ReplacementEvent] = {}
        
        # State
        self._state = PoolState.HEALTHY
        self._last_health_check: datetime | None = None
    
    def add_board(self, board_id: str, to_reserve: bool = False) -> bool:
        """Add board to pool."""
        if to_reserve:
            if len(self._reserve) >= int(self._config.max_boards * self._config.reserve_ratio):
                logger.warning("Reserve pool full", board_id=board_id)
                return False
            self._reserve.append(board_id)
        else:
            self._available.append(board_id)
        
        self._update_state()
        logger.info("Board added to pool", board_id=board_id, reserve=to_reserve)
        return True
    
    def remove_board(self, board_id: str) -> bool:
        """Remove board from pool."""
        for pool_name, pool in [
            ("available", self._available),
            ("maintenance", self._maintenance),
            ("failed", self._failed),
            ("reserve", self._reserve),
        ]:
            if board_id in pool:
                pool.remove(board_id)
                self._in_use.pop(board_id, None)
                self._update_state()
                logger.info("Board removed from pool", board_id=board_id)
                return True
        
        return False
    
    def acquire_board(self, user: str, purpose: str = "") -> str | None:
        """Acquire board from pool."""
        if not self._available:
            logger.warning(f"No boards available for user {user}")
            return None
        
        board_id = self._available.pop(0)
        self._in_use[board_id] = user
        
        logger.info("Board acquired", board_id=board_id, user=user)
        self._update_state()
        
        return board_id
    
    def release_board(self, board_id: str, healthy: bool = True) -> bool:
        """Release board back to pool."""
        if board_id not in self._in_use:
            return False
        
        del self._in_use[board_id]
        
        if healthy:
            self._available.append(board_id)
        else:
            self._failed.append(board_id)
            if self._config.auto_replacement_enabled:
                self._trigger_replacement(board_id)
        
        self._update_state()
        logger.info("Board released", board_id=board_id, healthy=healthy)
        return True
    
    def mark_failed(self, board_id: str, reason: str = "") -> None:
        """Mark board as failed."""
        # Remove from any pool
        for pool in [self._available, self._in_use, self._maintenance, self._reserve]:
            if board_id in pool:
                pool.remove(board_id)
        
        self._failed.append(board_id)
        
        # Trigger replacement
        if self._config.auto_replacement_enabled:
            self._trigger_replacement(board_id, reason)
        
        self._update_state()
        logger.warning(f"Board {board_id} marked failed: {reason}")
    
    def mark_maintenance(self, board_id: str) -> bool:
        """Mark board for maintenance."""
        for pool in [self._available, self._in_use]:
            if board_id in pool:
                pool.remove(board_id)
                if board_id in self._in_use:
                    del self._in_use[board_id]
                break
        
        if board_id not in self._maintenance:
            self._maintenance.append(board_id)
        
        self._update_state()
        return True
    
    def complete_maintenance(self, board_id: str) -> bool:
        """Complete maintenance and return board to pool."""
        if board_id in self._maintenance:
            self._maintenance.remove(board_id)
            self._available.append(board_id)
            self._update_state()
            return True
        return False
    
    def _trigger_replacement(self, failed_board_id: str, reason: str = "") -> ReplacementEvent:
        """Trigger automatic board replacement."""
        event = ReplacementEvent(
            event_id=f"repl_{failed_board_id}_{datetime.now().timestamp()}",
            failed_board_id=failed_board_id,
            replacement_board_id=None,
            status="pending",
            triggered_at=datetime.now(),
            reason=reason,
        )
        
        self._pending_replacement[event.event_id] = event
        
        # Try to get replacement from reserve
        if self._reserve:
            replacement = self._reserve.pop(0)
            event.replacement_board_id = replacement
            event.status = "completed"
            event.completed_at = datetime.now()
            
            # Add replacement to available
            self._available.append(replacement)
            
            logger.info(
                "Board replaced",
                failed=failed_board_id,
                replacement=replacement,
            )
        else:
            logger.warning("No replacement available", failed=failed_board_id)
        
        return event
    
    def _update_state(self) -> None:
        """Update pool state."""
        total = len(self._available) + len(self._in_use) + len(self._maintenance) + len(self._failed)
        available_count = len(self._available) + len(self._reserve)
        
        if total == 0:
            self._state = PoolState.CRITICAL
        elif len(self._failed) > 0 or available_count < self._config.min_boards:
            self._state = PoolState.CRITICAL
        elif available_count < total * self._config.alert_threshold:
            self._state = PoolState.DEGRADED
        else:
            self._state = PoolState.HEALTHY
        
        self._last_health_check = datetime.now()
    
    def get_statistics(self) -> PoolStatistics:
        """Get pool statistics."""
        total = len(self._available) + len(self._in_use) + len(self._maintenance) + len(self._failed)
        available_count = len(self._available) + len(self._reserve)
        
        return PoolStatistics(
            total_boards=total,
            available=len(self._available),
            in_use=len(self._in_use),
            maintenance=len(self._maintenance),
            failed=len(self._failed),
            reserve=len(self._reserve),
            availability_rate=available_count / total if total > 0 else 0,
            utilization_rate=len(self._in_use) / total if total > 0 else 0,
            avg_wait_time_seconds=0.0,  # Would track actual wait times
        )
    
    @property
    def state(self) -> PoolState:
        """Get pool state."""
        return self._state
    
    @property
    def available_count(self) -> int:
        """Get available board count."""
        return len(self._available)
    
    @property
    def pending_replacements(self) -> list[ReplacementEvent]:
        """Get pending replacement events."""
        return [e for e in self._pending_replacement.values() if e.status == "pending"]


# Global singleton
_pool: BoardPool | None = None


def get_board_pool(config: BoardPoolConfig | None = None) -> BoardPool:
    """Get global board pool."""
    global _pool
    if _pool is None:
        _pool = BoardPool(config)
    return _pool


if __name__ == "__main__":
    pool = get_board_pool(BoardPoolConfig(
        min_boards=2,
        max_boards=10,
        auto_replacement_enabled=True,
    ))
    
    print("Board Pool Test")
    print("=" * 40)
    
    # Add boards
    for i in range(5):
        pool.add_board(f"board_{i:02d}")
    
    # Add reserve
    pool.add_board("reserve_01", to_reserve=True)
    pool.add_board("reserve_02", to_reserve=True)
    
    # Stats
    stats = pool.get_statistics()
    print(f"Initial: {stats.available} available, {stats.reserve} reserve")
    print(f"State: {pool.state.value}")
    
    # Acquire boards
    board1 = pool.acquire_board("user1")
    board2 = pool.acquire_board("user2")
    print(f"\nAcquired: {board1}, {board2}")
    
    # Simulate failure
    if board1:
        pool.mark_failed(board1, "Hardware malfunction")
    
    stats = pool.get_statistics()
    print(f"\nAfter failure: {stats.failed} failed, {stats.available} available")
    print(f"State: {pool.state.value}")
    print(f"Pending replacements: {len(pool.pending_replacements)}")
    
    # Release
    if board2:
        pool.release_board(board2)
    
    stats = pool.get_statistics()
    print(f"\nAfter release: {stats.available} available")
