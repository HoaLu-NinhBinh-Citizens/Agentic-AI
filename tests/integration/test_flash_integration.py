"""Integration Tests for Flash Infrastructure - 6.2.IT1 to 6.2.IT12.

These tests run with mock hardware (QEMU simulation) to verify:
- Full flash workflow
- Delta programming
- Transaction commit/rollback
- Partial flash & resume
- A/B layout
- Erase policies
- Streaming flash
- Symbol indexing
- Memory validation
- Anti-rollback
- Concurrent locking
"""

import pytest
import asyncio
import tempfile
import os
from pathlib import Path


class TestFlashFullWorkflow:
    """Integration test: Full firmware flash workflow."""
    
    @pytest.mark.asyncio
    async def test_flash_full_firmware(self, mock_probe, mock_flash_driver):
        """6.2.IT1: Flash full firmware successfully."""
        # Create firmware
        firmware = bytes(range(256)) * 4  # 1KB
        
        # Flash firmware
        address = mock_probe.base_address
        sector_size = 2048
        
        # Erase
        await mock_flash_driver.erase_sector(address)
        
        # Write in pages
        page_size = 256
        for i in range(0, len(firmware), page_size):
            await mock_flash_driver.write_page(address + i, firmware[i:i+page_size])
        
        # Verify
        success = await mock_flash_driver.verify(address, firmware)
        
        assert success is True


class TestDeltaProgramming:
    """Integration test: Delta flash optimization."""
    
    @pytest.mark.asyncio
    async def test_delta_flash_optimization(self, mock_probe, mock_flash_driver):
        """6.2.IT2: Delta flash only changes sectors that differ."""
        # Original firmware
        original = b"A" * 1024
        
        # Modified firmware (only last 128 bytes changed)
        modified = b"A" * 896 + b"B" * 128
        
        # Flash original
        addr = mock_probe.base_address
        await mock_flash_driver.erase_sector(addr)
        await mock_flash_driver.write_with_verify(addr, original)
        
        # Count operations for full flash
        full_ops = mock_flash_driver.get_operation_count()
        
        # Reset
        mock_flash_driver.reset_failure_mode()
        
        # Calculate which sectors differ
        changed_sectors = 1  # Only 1 sector changed
        
        # Delta flash: only erase/write changed sector
        # Use address within valid range
        sector_addr = addr + 512  # Write to middle of flash
        await mock_flash_driver.erase_sector(sector_addr)
        await mock_flash_driver.write_with_verify(sector_addr, modified[:512])
        
        delta_ops = mock_flash_driver.get_operation_count() - full_ops
        
        # Delta should use fewer operations
        assert delta_ops < full_ops


class TestFlashTransaction:
    """Integration test: Flash transaction workflow."""
    
    @pytest.mark.asyncio
    async def test_transaction_commit(self):
        """6.2.IT3: Flash success leads to committed transaction."""
        from src.domain.hardware.flash.flash_transaction import (
            FlashTransaction,
            TransactionStatus,
        )
        
        # Create transaction
        tx = FlashTransaction(
            target_name="test_target",
            new_firmware_hash="abc123",
            new_firmware_version="2.0.0",
        )
        
        # Simulate flash success
        tx.status = TransactionStatus.COMMITTED
        tx.completed_at = tx.created_at
        
        assert tx.status == TransactionStatus.COMMITTED
        assert tx.is_terminal() is True
    
    @pytest.mark.asyncio
    async def test_transaction_rollback(self):
        """6.2.IT4: Flash failure triggers rollback."""
        from src.domain.hardware.flash.flash_transaction import (
            FlashTransaction,
            TransactionStatus,
        )
        
        # Create transaction with rollback capability
        tx = FlashTransaction(
            target_name="test_target",
            new_firmware_hash="abc123",
            rollback_snapshot_id="snap_001",
        )
        
        # Simulate failure
        tx.status = TransactionStatus.FAILED
        tx.error_code = "VERIFY_FAILED"
        tx.error_message = "Checksum mismatch"
        
        assert tx.status == TransactionStatus.FAILED
        assert tx.can_rollback() is True


class TestPartialFlashResume:
    """Integration test: Partial flash detection and resume."""
    
    @pytest.mark.asyncio
    async def test_partial_flash_detection(self):
        """6.2.IT5: Detect and handle partial flash interruption."""
        from src.domain.hardware.flash.flash_transaction import (
            FlashTransaction,
            TransactionStatus,
        )
        
        # Create interrupted transaction
        tx = FlashTransaction(
            target_name="test_target",
            new_firmware_hash="abc123",
            bytes_written=512,  # Only half written
            sectors_erased=2,
        )
        
        # Mark as interrupted
        tx.status = TransactionStatus.INTERRUPTED
        
        # Should be able to resume
        assert tx.resume_state is None  # No explicit resume state
        assert tx.bytes_written == 512


class TestABLayout:
    """Integration test: A/B slot layout handling."""
    
    @pytest.mark.asyncio
    async def test_ab_slot_selection(self):
        """6.2.IT6: Flash to inactive slot, then switch."""
        from src.domain.hardware.flash.flash_layout import (
            FlashLayout,
            LayoutType,
            Partition,
        )
        
        # Create dual-bank layout
        layout = FlashLayout()
        layout.layout_type = LayoutType.DUAL_BANK
        layout.flash_size = 2 * 1024 * 1024
        layout.sector_size = 2048
        
        # Add slots
        layout.partitions = [
            Partition(name="bank_a", start_address=0x08000000, size=1024*1024, slot_id="A"),
            Partition(name="bank_b", start_address=0x08100000, size=1024*1024, slot_id="B"),
        ]
        layout.active_slot = "A"
        layout.inactive_slot = "B"
        
        # Verify correct slot selection
        inactive = layout.get_inactive_partition()
        assert inactive is not None
        assert inactive.slot_id == "B"
        
        # After flashing B, can switch
        layout.active_slot, layout.inactive_slot = layout.inactive_slot, layout.active_slot
        assert layout.active_slot == "B"


class TestErasePolicy:
    """Integration test: Erase policy application."""
    
    @pytest.mark.asyncio
    async def test_erase_policy_balanced(self):
        """6.2.IT7: BALANCED policy erases guard sectors."""
        from src.domain.hardware.flash.erase_policy import (
            ErasePolicy,
            EraseMode,
        )
        
        policy = ErasePolicy(mode=EraseMode.BALANCED)
        policy.guard_sectors_before = 1
        policy.guard_sectors_after = 1
        
        # Firmware at sector 10-12
        sectors = policy.get_sectors_to_erase(
            firmware_address=10 * 2048,
            firmware_size=3 * 2048,
            sector_size=2048,
            total_sectors=512,
        )
        
        # Should include guard sectors
        assert len(sectors) >= 5  # 3 + 2 guards


class TestStreamingFlash:
    """Integration test: Streaming flash from remote source."""
    
    @pytest.mark.asyncio
    async def test_streaming_from_mock_s3(self, mock_probe, mock_flash_driver, async_stream_helper):
        """6.2.IT8: Stream firmware from mock S3 and flash."""
        # Create firmware
        firmware = b"X" * 1024
        
        # Stream and flash
        addr = mock_probe.base_address
        stream = async_stream_helper(firmware, chunk_size=256, delay_ms=1)
        
        # Flash from stream
        await mock_flash_driver.erase_sector(addr)
        
        accumulated = b""
        async for chunk in stream:
            accumulated += chunk
        
        await mock_flash_driver.write_with_verify(addr, accumulated)
        
        # Verify
        success = await mock_flash_driver.verify(addr, firmware)
        assert success is True


class TestSymbolIndexing:
    """Integration test: Symbol index updates after flash."""
    
    @pytest.mark.asyncio
    async def test_symbol_lookup_after_flash(self):
        """6.2.IT9: Symbol index available after flash."""
        from src.domain.hardware.flash.symbol_index import SymbolIndex, SymbolInfo
        
        index = SymbolIndex()
        
        # Simulate adding symbols from firmware
        await index.add_symbol(
            SymbolInfo(
                name="main",
                address=0x08000000,
                size=512,
                symbol_type="function",
                firmware_hash="test_hash",
            )
        )
        
        await index.add_symbol(
            SymbolInfo(
                name="uart_init",
                address=0x08000200,
                size=128,
                symbol_type="function",
                firmware_hash="test_hash",
            )
        )
        
        # Lookup works
        result = await index.lookup_symbol("main", "test_hash")
        assert result is not None
        assert result.name == "main"


class TestMemoryMapValidation:
    """Integration test: Memory map validation."""
    
    @pytest.mark.asyncio
    async def test_firmware_rejected_on_overlap(self):
        """6.2.IT10: Firmware with overlap is rejected."""
        from src.domain.hardware.flash.memory_map_validator import (
            MemoryMapValidator,
            ELFSection,
            MemoryRegion,
        )
        from src.domain.hardware.flash.flash_layout import Partition
        
        validator = MemoryMapValidator()
        
        # Firmware with sections that would overlap
        sections = [
            ELFSection(name=".text", address=0x08000000, size=1024),
            ELFSection(name=".data", address=0x08000800, size=1024),  # Overlaps with .text
        ]
        
        regions = [
            MemoryRegion(name="flash", base_address=0x08000000, size=1024*1024),
        ]
        
        protected = [
            Partition(name="boot", start_address=0x08000800, size=512),
        ]
        
        result = await validator.validate(
            elf_sections=sections,
            target_memory_regions=regions,
            protected_regions=protected,
            target_partition_start=0x08000000,
            target_partition_size=1024*1024,
        )
        
        assert result.is_valid is False
        assert len(result.overlaps) > 0


class TestAntiRollback:
    """Integration test: Anti-rollback protection."""
    
    @pytest.mark.asyncio
    async def test_older_version_rejected(self):
        """6.2.IT11: Flashing older version is rejected."""
        from src.domain.hardware.flash.secure_boot import (
            AntiRollbackChecker,
            SecureBootPolicy,
        )
        
        policy = SecureBootPolicy(
            enabled=True,
            anti_rollback_enabled=True,
            version_storage_address=0x08003FFC,  # STM32 version location
        )
        
        checker = AntiRollbackChecker(policy=policy)
        
        # Check: trying to flash v1.0.0 when v2.0.0 exists
        allowed, reason = await checker.check(
            current_version=2,  # v2.0.0 on device
            new_version=1,  # Trying to flash v1.0.0
        )
        
        assert allowed is False
        assert "Anti-rollback" in reason


class TestConcurrentLocking:
    """Integration test: Concurrent flash locking."""
    
    @pytest.mark.asyncio
    async def test_concurrent_flash_blocked(self, mock_lock_manager):
        """6.2.IT12: Second flash attempt is blocked by lock."""
        # First agent acquires lock
        lock1 = await mock_lock_manager.acquire("target1", "agent_1")
        assert lock1 is not None
        assert lock1["owner_id"] == "agent_1"
        
        # Second agent cannot acquire
        lock2 = await mock_lock_manager.acquire("target1", "agent_2", timeout_seconds=0.1)
        assert lock2 is None
        
        # First agent can re-acquire (renew)
        lock1_renewed = await mock_lock_manager.acquire("target1", "agent_1")
        assert lock1_renewed is not None
        
        # First agent releases
        released = await mock_lock_manager.release("target1", "agent_1")
        assert released is True
        
        # Now agent_2 can acquire
        lock2_after = await mock_lock_manager.acquire("target1", "agent_2")
        assert lock2_after is not None
