"""Unit tests for Flash Layout."""

import pytest
from src.domain.hardware.flash.flash_layout import (
    LayoutType,
    Partition,
    FlashLayout,
    ActiveSlotDetector,
    SlotSelector,
)


class TestPartition:
    """Tests for Partition dataclass."""
    
    def test_partition_creation(self):
        """Test partition creation."""
        p = Partition(
            name="app_a",
            start_address=0x08010000,
            size=0x70000,
        )
        
        assert p.name == "app_a"
        assert p.start_address == 0x08010000
        assert p.size == 0x70000
        assert p.end_address == 0x08080000
    
    def test_contains_address(self):
        """Test address containment check."""
        p = Partition(
            name="test",
            start_address=0x08000000,
            size=0x10000,
        )
        
        assert p.contains_address(0x08000000)
        assert p.contains_address(0x08005FFF)
        assert not p.contains_address(0x08010000)
        assert not p.contains_address(0x07FFFFFF)
    
    def test_flags(self):
        """Test partition flags."""
        p = Partition(
            name="boot",
            start_address=0x08000000,
            size=0x10000,
            is_bootable=True,
            is_protected=True,
        )
        
        assert p.is_bootable
        assert p.is_protected


class TestFlashLayout:
    """Tests for FlashLayout."""
    
    def test_layout_creation(self):
        """Test layout creation."""
        layout = FlashLayout(
            layout_id="test_layout",
            layout_type=LayoutType.SINGLE,
            flash_size=0x100000,
        )
        
        assert layout.layout_id == "test_layout"
        assert layout.layout_type == LayoutType.SINGLE
        assert layout.flash_size == 0x100000
    
    def test_add_partition(self):
        """Test adding partitions."""
        layout = FlashLayout()
        layout.partitions.append(Partition(
            name="app",
            start_address=0x08010000,
            size=0x70000,
        ))
        
        assert layout.get_partition("app") is not None
        assert layout.get_partition("boot") is None
    
    def test_active_partition(self):
        """Test getting active partition."""
        layout = FlashLayout()
        layout.active_slot = "A"
        layout.partitions.extend([
            Partition(name="app_a", start_address=0x08010000, size=0x70000, slot_id="A"),
            Partition(name="app_b", start_address=0x08080000, size=0x70000, slot_id="B"),
        ])
        
        active = layout.get_active_partition()
        assert active is not None
        assert active.slot_id == "A"
    
    def test_inactive_partition(self):
        """Test getting inactive partition."""
        layout = FlashLayout()
        layout.active_slot = "A"
        layout.inactive_slot = "B"
        layout.partitions.extend([
            Partition(name="app_a", start_address=0x08010000, size=0x70000, slot_id="A"),
            Partition(name="app_b", start_address=0x08080000, size=0x70000, slot_id="B"),
        ])
        
        inactive = layout.get_inactive_partition()
        assert inactive is not None
        assert inactive.slot_id == "B"
    
    def test_validate_address(self):
        """Test address validation."""
        layout = FlashLayout(
            flash_size=0x100000,
            partitions=[
                Partition(name="boot", start_address=0x08000000, size=0x10000, is_protected=True),
            ],
        )
        
        valid, msg = layout.validate_address(0x08010000, 0x10000)
        assert valid
        
        # Overlaps protected
        valid, msg = layout.validate_address(0x08005000, 0x10000)
        assert not valid
        assert "protected" in msg
    
    def test_from_config(self):
        """Test creating layout from config."""
        config = {
            "id": "test",
            "type": "dual_bank",
            "flash_size": 0x200000,
            "partitions": [
                {"name": "boot", "start": 0x08000000, "size": 0x10000},
                {"name": "app_a", "start": 0x08010000, "size": 0xF8000, "slot": "A"},
                {"name": "app_b", "start": 0x080F8000, "size": 0xF8000, "slot": "B"},
            ],
            "active_slot": "A",
        }
        
        layout = FlashLayout.from_config(config)
        
        assert layout.layout_type == LayoutType.DUAL_BANK
        assert layout.active_slot == "A"
        assert len(layout.partitions) == 3
    
    def test_create_stm32_dual_bank(self):
        """Test creating STM32 dual-bank layout."""
        layout = FlashLayout.create_stm32_dual_bank(flash_size=0x100000)
        
        assert layout.layout_type == LayoutType.DUAL_BANK
        assert layout.slot_selector_address == 0x080FFFC
        assert len(layout.partitions) == 2
        
        bank_a = layout.get_partition("bank_a")
        bank_b = layout.get_partition("bank_b")
        assert bank_a is not None
        assert bank_b is not None
    
    def test_create_esp32_partition_table(self):
        """Test creating ESP32 partition table layout."""
        layout = FlashLayout.create_esp32_partition_table()
        
        assert layout.layout_type == LayoutType.PARTITION_TABLE
        assert len(layout.partitions) > 0
        
        # Check app partitions
        app_a = layout.get_partition("app_a")
        app_b = layout.get_partition("app_b")
        assert app_a is not None
        assert app_b is not None
        assert app_a.slot_id == "A"
        assert app_b.slot_id == "B"


class TestSlotSelector:
    """Tests for SlotSelector."""
    
    def test_single_slot_selection(self):
        """Test slot selection for single layout."""
        layout = FlashLayout(layout_type=LayoutType.SINGLE)
        layout.partitions.append(Partition(
            name="app",
            start_address=0x08010000,
            size=0xF0000,
            is_bootable=True,
        ))
        
        selector = SlotSelector(layout)
        target = selector.get_flash_target_slot()
        
        assert target is not None
        assert target.name == "app"
    
    def test_ab_slot_selection(self):
        """Test slot selection for A/B layout."""
        layout = FlashLayout()
        layout.layout_type = LayoutType.DUAL_BANK
        layout.active_slot = "A"
        layout.inactive_slot = "B"
        layout.partitions.extend([
            Partition(name="app_a", start_address=0x08010000, size=0x70000, slot_id="A"),
            Partition(name="app_b", start_address=0x08080000, size=0x70000, slot_id="B"),
        ])
        
        selector = SlotSelector(layout)
        target = selector.get_flash_target_slot()
        
        assert target is not None
        assert target.slot_id == "B"
    
    def test_get_rollback_slot(self):
        """Test getting rollback slot."""
        layout = FlashLayout()
        layout.layout_type = LayoutType.DUAL_BANK
        layout.active_slot = "A"
        layout.inactive_slot = "B"
        layout.partitions.extend([
            Partition(name="app_a", start_address=0x08010000, size=0x70000, slot_id="A"),
            Partition(name="app_b", start_address=0x08080000, size=0x70000, slot_id="B"),
        ])
        
        selector = SlotSelector(layout)
        rollback = selector.get_rollback_slot()
        
        assert rollback is not None
        assert rollback.slot_id == "A"
    
    def test_estimate_flash_time(self):
        """Test flash time estimation."""
        layout = FlashLayout()
        layout.partitions.append(Partition(
            name="app",
            start_address=0x08010000,
            size=0x100000,
        ))
        
        selector = SlotSelector(layout)
        times = selector.estimate_flash_time(
            firmware_size=1024 * 100,  # 100KB
            target_partition=layout.partitions[0],
        )
        
        assert "erase_time" in times
        assert "write_time" in times
        assert "verify_time" in times
        assert all(t >= 0 for t in times.values())


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
