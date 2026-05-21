"""Unit tests for Erase Policy and Wear Leveling."""

import pytest
from datetime import datetime
from src.domain.hardware.flash.erase_policy import (
    EraseMode,
    ErasePolicy,
    SectorStats,
    WearLevelingMonitor,
    WearingWarning,
)


class TestEraseMode:
    """Tests for EraseMode enum."""
    
    def test_all_modes_defined(self):
        """Test all erase modes exist."""
        assert EraseMode.MINIMAL.value == "minimal"
        assert EraseMode.BALANCED.value == "balanced"
        assert EraseMode.FULL.value == "full"


class TestErasePolicy:
    """Tests for ErasePolicy."""
    
    def test_minimal_mode(self):
        """Test minimal erase mode."""
        policy = ErasePolicy(mode=EraseMode.MINIMAL)
        
        sectors = policy.get_sectors_to_erase(
            firmware_address=0x08010000,
            firmware_size=0x10000,  # 64KB
            sector_size=0x800,      # 2KB sectors
            total_sectors=128,
        )
        
        # Should only erase sectors needed for firmware
        assert len(sectors) == 32  # 0x10000 / 0x800
    
    def test_balanced_mode(self):
        """Test balanced erase mode."""
        policy = ErasePolicy(
            mode=EraseMode.BALANCED,
            guard_sectors_before=1,
            guard_sectors_after=1,
        )
        
        sectors = policy.get_sectors_to_erase(
            firmware_address=0x08010800,  # Offset by 1 sector
            firmware_size=0x10000,
            sector_size=0x800,
            total_sectors=128,
        )
        
        # Should include guards
        assert len(sectors) > 32
    
    def test_full_mode(self):
        """Test full erase mode."""
        policy = ErasePolicy(mode=EraseMode.FULL)
        
        sectors = policy.get_sectors_to_erase(
            firmware_address=0x08010000,
            firmware_size=0x10000,
            sector_size=0x800,
            total_sectors=128,
        )
        
        # Should erase all sectors
        assert len(sectors) == 128
    
    def test_factory_methods(self):
        """Test factory methods."""
        minimal = ErasePolicy.minimal()
        assert minimal.mode == EraseMode.MINIMAL
        
        balanced = ErasePolicy.balanced()
        assert balanced.mode == EraseMode.BALANCED
        
        full = ErasePolicy.full()
        assert full.mode == EraseMode.FULL
    
    def test_to_dict(self):
        """Test serialization."""
        policy = ErasePolicy(
            mode=EraseMode.BALANCED,
            guard_sectors_before=2,
        )
        
        data = policy.to_dict()
        
        assert data["mode"] == "balanced"
        assert data["guard_sectors_before"] == 2


class TestSectorStats:
    """Tests for SectorStats."""
    
    def test_creation(self):
        """Test sector stats creation."""
        stats = SectorStats(sector_index=5)
        
        assert stats.sector_index == 5
        assert stats.erase_count == 0
        assert stats.write_count == 0
    
    def test_default_max_cycles(self):
        """Test default max erase cycles."""
        stats = SectorStats(sector_index=0)
        
        assert stats.max_erase_cycles == 100000


class TestWearingWarning:
    """Tests for WearingWarning."""
    
    def test_to_dict(self):
        """Test serialization."""
        warning = WearingWarning(
            sector_index=10,
            erase_count=90000,
            max_cycles=100000,
            wear_percent=90.0,
            severity="warning",
        )
        
        data = warning.to_dict()
        
        assert data["sector_index"] == 10
        assert data["wear_percent"] == 90.0
        assert data["severity"] == "warning"


class TestWearLevelingMonitor:
    """Tests for WearLevelingMonitor."""
    
    @pytest.fixture
    async def monitor(self, tmp_path):
        """Create monitor with temporary database."""
        db_path = str(tmp_path / "test_wear.db")
        monitor = WearLevelingMonitor(db_path=str(db_path))
        await monitor.initialize()
        yield monitor
        await monitor.close()
    
    @pytest.mark.asyncio
    async def test_record_erase(self, monitor):
        """Test recording erase operations."""
        await monitor.record_erase(5)
        
        stats = await monitor.get_sector_stats(5)
        assert stats is not None
        assert stats.erase_count == 1
    
    @pytest.mark.asyncio
    async def test_record_write(self, monitor):
        """Test recording write operations."""
        await monitor.record_write(3)
        
        stats = await monitor.get_sector_stats(3)
        assert stats is not None
        assert stats.write_count == 1
    
    @pytest.mark.asyncio
    async def test_multiple_erases(self, monitor):
        """Test multiple erase operations."""
        for _ in range(10):
            await monitor.record_erase(1)
        
        stats = await monitor.get_sector_stats(1)
        assert stats.erase_count == 10
    
    @pytest.mark.asyncio
    async def test_wear_warning(self, monitor):
        """Test wear warning generation."""
        # Simulate high wear
        for _ in range(85000):
            await monitor.record_erase(7)
        
        warnings = await monitor.get_wear_warnings()
        assert len(warnings) == 1
        assert warnings[0].severity == "warning"
    
    @pytest.mark.asyncio
    async def test_critical_wear_warning(self, monitor):
        """Test critical wear warning."""
        # Simulate critical wear
        for _ in range(96000):
            await monitor.record_erase(8)
        
        warnings = await monitor.get_wear_warnings()
        assert len(warnings) == 1
        assert warnings[0].severity == "critical"
    
    @pytest.mark.asyncio
    async def test_total_erases(self, monitor):
        """Test total erase count."""
        await monitor.record_erase(1)
        await monitor.record_erase(1)
        await monitor.record_erase(2)
        
        total = await monitor.get_total_erases()
        assert total == 3
    
    @pytest.mark.asyncio
    async def test_average_wear(self, monitor):
        """Test average wear calculation."""
        await monitor.record_erase(1)
        await monitor.record_erase(2)
        
        avg = await monitor.get_average_wear()
        assert avg >= 0
    
    @pytest.mark.asyncio
    async def test_export_stats(self, monitor):
        """Test stats export."""
        await monitor.record_erase(1)
        
        export = await monitor.export_stats()
        
        assert "total_sectors" in export
        assert "total_erases" in export
        assert "warnings" in export


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
