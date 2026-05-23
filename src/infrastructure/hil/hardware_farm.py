"""Hardware farm manager (Phase 7.4).

Manages fleet of hardware boards for testing:
- Board registry and state tracking
- Board health monitoring
- Board scheduling and allocation
- Capacity planning
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class BoardState(Enum):
    """Board availability state."""
    AVAILABLE = "available"
    IN_USE = "in_use"
    TESTING = "testing"
    MAINTENANCE = "maintenance"
    OFFLINE = "offline"
    ERROR = "error"
    RESERVED = "reserved"


class BoardHealth(Enum):
    """Board health status."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class BoardSpec:
    """Hardware board specification."""
    board_id: str
    board_type: str  # e.g., "STM32F407VG", "ESP32-DevKit"
    probe_type: str  # "J-Link", "ST-Link", "CMSIS-DAP"
    firmware_version: str = ""
    capabilities: list[str] = field(default_factory=list)  # e.g., ["jtag", "swd", "rtt"]
    max_test_duration_minutes: int = 30


@dataclass
class BoardStatus:
    """Current board status."""
    board_id: str
    state: BoardState = BoardState.OFFLINE
    health: BoardHealth = BoardHealth.UNKNOWN
    
    # Usage
    current_test: str = ""
    current_user: str = ""
    test_start_time: datetime | None = None
    
    # Metrics
    total_tests: int = 0
    successful_tests: int = 0
    failed_tests: int = 0
    flaky_tests: int = 0
    
    # Health
    last_health_check: datetime = field(default_factory=datetime.now)
    error_count_24h: int = 0
    uptime_hours: float = 0.0
    
    # Maintenance
    last_maintenance: datetime | None = None
    next_maintenance: datetime | None = None
    maintenance_required: bool = False
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        total = self.successful_tests + self.failed_tests
        if total == 0:
            return 0.0
        return self.successful_tests / total
    
    @property
    def is_available(self) -> bool:
        """Check if board is available for use."""
        return self.state in [BoardState.AVAILABLE, BoardState.OFFLINE] and self.health != BoardHealth.UNHEALTHY


@dataclass
class BoardLease:
    """Lease for a board."""
    lease_id: str
    board_id: str
    user: str
    purpose: str
    start_time: datetime
    end_time: datetime | None = None
    max_duration_minutes: int = 30
    force_release: bool = False
    
    @property
    def is_active(self) -> bool:
        """Check if lease is still active."""
        if self.end_time:
            return datetime.now() < self.end_time
        return True


class HardwareFarmManager:
    """Manages hardware board farm for HIL testing.
    
    Phase 7.4: Hardware farm manager
    """
    
    def __init__(self) -> None:
        self._boards: dict[str, BoardSpec] = {}
        self._status: dict[str, BoardStatus] = {}
        self._leases: dict[str, BoardLease] = {}
        self._reservations: dict[str, list[str]] = {}  # user -> [board_ids]
    
    def register_board(self, spec: BoardSpec) -> None:
        """Register a new board in the farm."""
        self._boards[spec.board_id] = spec
        self._status[spec.board_id] = BoardStatus(
            board_id=spec.board_id,
            state=BoardState.OFFLINE,
            health=BoardHealth.UNKNOWN,
        )
        logger.info("Registered board", board_id=spec.board_id, type=spec.board_type)
    
    def unregister_board(self, board_id: str) -> bool:
        """Unregister a board from the farm."""
        if board_id in self._boards:
            del self._boards[board_id]
            del self._status[board_id]
            logger.info("Unregistered board", board_id=board_id)
            return True
        return False
    
    def get_board(self, board_id: str) -> BoardSpec | None:
        """Get board specification."""
        return self._boards.get(board_id)
    
    def get_status(self, board_id: str) -> BoardStatus | None:
        """Get board status."""
        return self._status.get(board_id)
    
    def list_boards(
        self,
        state: BoardState | None = None,
        health: BoardHealth | None = None,
        board_type: str | None = None,
    ) -> list[BoardSpec]:
        """List boards with optional filters."""
        boards = list(self._boards.values())
        
        if state:
            boards = [b for b in boards if self._status.get(b.board_id, BoardStatus(b.board_id)).state == state]
        
        if health:
            boards = [b for b in boards if self._status.get(b.board_id, BoardStatus(b.board_id)).health == health]
        
        if board_type:
            boards = [b for b in boards if b.board_type == board_type]
        
        return boards
    
    def get_available_boards(self, board_type: str | None = None) -> list[BoardSpec]:
        """Get available boards for testing."""
        available = []
        for board in self._boards.values():
            status = self._status.get(board.board_id)
            if status and status.is_available:
                if board_type is None or board.board_type == board_type:
                    available.append(board)
        return available
    
    def acquire_board(
        self,
        user: str,
        purpose: str,
        board_type: str | None = None,
        max_duration_minutes: int = 30,
    ) -> BoardSpec | None:
        """Acquire an available board for testing."""
        available = self.get_available_boards(board_type)
        if not available:
            logger.warning("No boards available", user=user, board_type=board_type)
            return None
        
        # Pick first available
        board = available[0]
        status = self._status[board.board_id]
        
        # Update status
        status.state = BoardState.IN_USE
        status.current_user = user
        status.current_test = purpose
        status.test_start_time = datetime.now()
        
        # Create lease
        lease = BoardLease(
            lease_id=f"lease_{board.board_id}_{int(datetime.now().timestamp())}",
            board_id=board.board_id,
            user=user,
            purpose=purpose,
            start_time=datetime.now(),
            max_duration_minutes=max_duration_minutes,
        )
        self._leases[lease.lease_id] = lease
        
        logger.info("Board acquired", board_id=board.board_id, user=user, purpose=purpose)
        return board
    
    def release_board(self, board_id: str) -> bool:
        """Release a board back to the pool."""
        if board_id not in self._status:
            return False
        
        status = self._status[board_id]
        
        # Update status
        status.state = BoardState.AVAILABLE
        status.current_user = ""
        status.current_test = ""
        status.test_start_time = None
        
        # Expire related leases
        for lease_id, lease in list(self._leases.items()):
            if lease.board_id == board_id and lease.is_active:
                lease.end_time = datetime.now()
        
        logger.info("Board released", board_id=board_id)
        return True
    
    def update_health(
        self,
        board_id: str,
        health: BoardHealth,
        error_count: int | None = None,
    ) -> None:
        """Update board health status."""
        if board_id not in self._status:
            return
        
        status = self._status[board_id]
        status.health = health
        status.last_health_check = datetime.now()
        
        if error_count is not None:
            status.error_count_24h = error_count
        
        # Mark as unhealthy if too many errors
        if error_count and error_count > 10:
            status.state = BoardState.ERROR
            logger.warning("Board marked as error", board_id=board_id, errors=error_count)
        
        # Suggest maintenance if degraded
        if health == BoardHealth.DEGRADED:
            status.maintenance_required = True
    
    def record_test_result(
        self,
        board_id: str,
        success: bool,
        duration_minutes: float,
        is_flaky: bool = False,
    ) -> None:
        """Record test result for a board."""
        if board_id not in self._status:
            return
        
        status = self._status[board_id]
        status.total_tests += 1
        
        if success:
            status.successful_tests += 1
        else:
            status.failed_tests += 1
            status.error_count_24h += 1
        
        if is_flaky:
            status.flaky_tests += 1
    
    def set_maintenance(self, board_id: str, duration_hours: int = 24) -> None:
        """Schedule board for maintenance."""
        if board_id not in self._status:
            return
        
        status = self._status[board_id]
        status.state = BoardState.MAINTENANCE
        status.maintenance_required = False
        status.last_maintenance = datetime.now()
        status.next_maintenance = datetime.now() + timedelta(hours=duration_hours)
        
        logger.info("Board scheduled for maintenance", board_id=board_id, hours=duration_hours)
    
    def get_statistics(self) -> dict[str, Any]:
        """Get farm statistics."""
        total = len(self._boards)
        available = len([s for s in self._status.values() if s.state == BoardState.AVAILABLE])
        in_use = len([s for s in self._status.values() if s.state == BoardState.IN_USE])
        maintenance = len([s for s in self._status.values() if s.state == BoardState.MAINTENANCE])
        error = len([s for s in self._status.values() if s.state == BoardState.ERROR])
        
        total_tests = sum(s.total_tests for s in self._status.values())
        total_success = sum(s.successful_tests for s in self._status.values())
        
        return {
            "total_boards": total,
            "available": available,
            "in_use": in_use,
            "maintenance": maintenance,
            "error": error,
            "utilization": (in_use / total * 100) if total > 0 else 0,
            "total_tests": total_tests,
            "overall_success_rate": (total_success / total_tests * 100) if total_tests > 0 else 0,
            "active_leases": len([l for l in self._leases.values() if l.is_active]),
            "boards_by_type": self._count_by_type(),
        }
    
    def _count_by_type(self) -> dict[str, int]:
        """Count boards by type."""
        counts: dict[str, int] = {}
        for board in self._boards.values():
            counts[board.board_type] = counts.get(board.board_type, 0) + 1
        return counts


# Global singleton
_farm_manager: HardwareFarmManager | None = None


def get_hardware_farm_manager() -> HardwareFarmManager:
    """Get global hardware farm manager."""
    global _farm_manager
    if _farm_manager is None:
        _farm_manager = HardwareFarmManager()
    return _farm_manager


if __name__ == "__main__":
    farm = get_hardware_farm_manager()
    
    # Register boards
    farm.register_board(BoardSpec(
        board_id="board_001",
        board_type="STM32F407VG",
        probe_type="J-Link",
        capabilities=["jtag", "swd", "rtt"],
    ))
    farm.register_board(BoardSpec(
        board_id="board_002",
        board_type="STM32F407VG",
        probe_type="ST-Link",
        capabilities=["swd"],
    ))
    
    # Acquire board
    board = farm.acquire_board("engineer1", "Run UART tests")
    if board:
        print(f"Acquired: {board.board_id}")
        
        # Record results
        farm.record_test_result(board.board_id, success=True, duration_minutes=5)
        farm.record_test_result(board.board_id, success=True, duration_minutes=4)
        farm.record_test_result(board.board_id, success=False, duration_minutes=3, is_flaky=True)
        
        # Release
        farm.release_board(board.board_id)
    
    # Statistics
    stats = farm.get_statistics()
    print(f"\nFarm Statistics:")
    for key, value in stats.items():
        print(f"  {key}: {value}")
