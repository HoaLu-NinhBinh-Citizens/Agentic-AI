"""Erase Policy & Wear Leveling for flash operations.

Phase 6.2: Implements erase policy management and flash wear monitoring:
- MINIMAL, BALANCED, FULL erase modes
- Sector erase tracking
- Wear leveling warnings
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class EraseMode(Enum):
    """Flash erase modes."""
    
    MINIMAL = "minimal"     # Only erase sectors needed for firmware
    BALANCED = "balanced"   # Erase with guard sectors
    FULL = "full"          # Erase entire region before flash


@dataclass
class ErasePolicy:
    """Policy for flash erase operations.
    
    Balances flash wear against time/resources.
    """
    
    mode: EraseMode = EraseMode.BALANCED
    
    # Guard sectors (for BALANCED mode)
    guard_sectors_before: int = 1
    guard_sectors_after: int = 1
    
    # Skip unchanged sectors (optimization)
    skip_unchanged_sectors: bool = True
    
    # Force full erase (security)
    force_full_erase: bool = False
    
    def get_sectors_to_erase(
        self,
        firmware_address: int,
        firmware_size: int,
        sector_size: int,
        total_sectors: int,
    ) -> list[int]:
        """Calculate which sectors to erase.
        
        Args:
            firmware_address: Start address of firmware
            firmware_size: Size of firmware in bytes
            sector_size: Size of each sector
            total_sectors: Total sectors in region
        
        Returns:
            List of sector indices to erase
        """
        start_sector = firmware_address // sector_size
        end_sector = (firmware_address + firmware_size - 1) // sector_size
        
        sectors = []
        
        if self.mode == EraseMode.MINIMAL:
            sectors = list(range(start_sector, end_sector + 1))
        
        elif self.mode == EraseMode.BALANCED:
            start = max(0, start_sector - self.guard_sectors_before)
            end = min(total_sectors - 1, end_sector + self.guard_sectors_after)
            sectors = list(range(start, end + 1))
        
        elif self.mode == EraseMode.FULL:
            sectors = list(range(total_sectors))
        
        return sectors
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "mode": self.mode.value,
            "guard_sectors_before": self.guard_sectors_before,
            "guard_sectors_after": self.guard_sectors_after,
            "skip_unchanged_sectors": self.skip_unchanged_sectors,
            "force_full_erase": self.force_full_erase,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ErasePolicy:
        """Create from dictionary."""
        return cls(
            mode=EraseMode(data.get("mode", "balanced")),
            guard_sectors_before=data.get("guard_sectors_before", 1),
            guard_sectors_after=data.get("guard_sectors_after", 1),
            skip_unchanged_sectors=data.get("skip_unchanged_sectors", True),
            force_full_erase=data.get("force_full_erase", False),
        )
    
    @classmethod
    def minimal(cls) -> ErasePolicy:
        """Create minimal erase policy."""
        return cls(mode=EraseMode.MINIMAL)
    
    @classmethod
    def balanced(cls) -> ErasePolicy:
        """Create balanced erase policy."""
        return cls(mode=EraseMode.BALANCED)
    
    @classmethod
    def full(cls) -> ErasePolicy:
        """Create full erase policy."""
        return cls(mode=EraseMode.FULL)


@dataclass
class SectorStats:
    """Statistics for a single flash sector."""
    
    sector_index: int
    erase_count: int = 0
    write_count: int = 0
    last_erase_at: datetime | None = None
    last_write_at: datetime | None = None
    
    # Thresholds
    max_erase_cycles: int = 100000  # Typical for STM32


@dataclass
class WearingWarning:
    """Warning about flash sector wear."""
    
    sector_index: int
    erase_count: int
    max_cycles: int
    wear_percent: float
    severity: str  # "warning" or "critical"
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "sector_index": self.sector_index,
            "erase_count": self.erase_count,
            "max_cycles": self.max_cycles,
            "wear_percent": round(self.wear_percent, 2),
            "severity": self.severity,
        }


@dataclass
class WearLevelingMonitor:
    """Monitors flash wear and provides warnings.
    
    Tracks erase counts per sector and warns when approaching limits.
    """
    
    db_path: str
    warning_threshold_percent: float = 80.0  # Warn at 80% of max cycles
    
    _db: Any = field(default=None, init=False)
    _stats: dict[int, SectorStats] = field(default_factory=dict)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    
    async def initialize(self) -> None:
        """Initialize database."""
        import aiosqlite
        
        self._db = await aiosqlite.connect(self.db_path)
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS sector_stats (
                sector_index INTEGER PRIMARY KEY,
                erase_count INTEGER DEFAULT 0,
                write_count INTEGER DEFAULT 0,
                last_erase_at TEXT,
                last_write_at TEXT
            )
        """)
        await self._db.commit()
        
        # Load existing stats
        cursor = await self._db.execute("SELECT * FROM sector_stats")
        async for row in cursor:
            stats = SectorStats(
                sector_index=row[0],
                erase_count=row[1],
                write_count=row[2],
                last_erase_at=datetime.fromisoformat(row[3]) if row[3] else None,
                last_write_at=datetime.fromisoformat(row[4]) if row[4] else None,
            )
            self._stats[stats.sector_index] = stats
    
    async def close(self) -> None:
        """Close database."""
        if self._db:
            await self._db.close()
            self._db = None
    
    async def record_erase(self, sector_index: int) -> None:
        """Record sector erase operation."""
        async with self._lock:
            if sector_index not in self._stats:
                self._stats[sector_index] = SectorStats(sector_index=sector_index)
            
            stats = self._stats[sector_index]
            stats.erase_count += 1
            stats.last_erase_at = datetime.now()
            
            if self._db:
                await self._db.execute("""
                    INSERT OR REPLACE INTO sector_stats
                    (sector_index, erase_count, write_count, last_erase_at, last_write_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    sector_index,
                    stats.erase_count,
                    stats.write_count,
                    stats.last_erase_at.isoformat() if stats.last_erase_at else None,
                    stats.last_write_at.isoformat() if stats.last_write_at else None,
                ))
                await self._db.commit()
    
    async def record_write(self, sector_index: int) -> None:
        """Record sector write operation."""
        async with self._lock:
            if sector_index not in self._stats:
                self._stats[sector_index] = SectorStats(sector_index=sector_index)
            
            stats = self._stats[sector_index]
            stats.write_count += 1
            stats.last_write_at = datetime.now()
    
    async def get_wear_warnings(self) -> list[WearingWarning]:
        """Get warnings for sectors approaching wear limits."""
        warnings = []
        
        for stats in self._stats.values():
            wear_percent = (stats.erase_count / stats.max_erase_cycles) * 100
            
            if wear_percent >= self.warning_threshold_percent:
                warnings.append(WearingWarning(
                    sector_index=stats.sector_index,
                    erase_count=stats.erase_count,
                    max_cycles=stats.max_erase_cycles,
                    wear_percent=wear_percent,
                    severity="critical" if wear_percent >= 95 else "warning",
                ))
        
        return warnings
    
    async def get_sector_stats(self, sector_index: int) -> SectorStats | None:
        """Get statistics for a sector."""
        return self._stats.get(sector_index)
    
    async def get_all_stats(self) -> list[SectorStats]:
        """Get all sector statistics."""
        return list(self._stats.values())
    
    async def get_total_erases(self) -> int:
        """Get total erase count across all sectors."""
        return sum(s.erase_count for s in self._stats.values())
    
    async def get_average_wear(self) -> float:
        """Get average wear percentage across all sectors."""
        if not self._stats:
            return 0.0
        
        total_wear = sum(
            s.erase_count / s.max_erase_cycles * 100
            for s in self._stats.values()
        )
        return total_wear / len(self._stats)
    
    async def export_stats(self) -> dict[str, Any]:
        """Export all statistics."""
        return {
            "total_sectors": len(self._stats),
            "total_erases": await self.get_total_erases(),
            "average_wear_percent": await self.get_average_wear(),
            "warnings": [w.to_dict() for w in await self.get_wear_warnings()],
            "sectors": [
                {
                    "index": s.sector_index,
                    "erase_count": s.erase_count,
                    "write_count": s.write_count,
                    "wear_percent": round(s.erase_count / s.max_erase_cycles * 100, 2),
                }
                for s in self._stats.values()
            ],
        }
