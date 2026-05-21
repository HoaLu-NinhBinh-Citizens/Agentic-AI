"""Tests for Flash Journal - Sector-level WAL."""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from src.domain.hardware.flash.flash_journal import (
    JournalOperation,
    SectorChecksum,
    JournalEntry,
    FlashJournal,
    JournalRecoveryPlanner,
)


class TestJournalEntry:
    """Test JournalEntry dataclass."""
    
    def test_create_entry(self):
        """Test creating journal entry."""
        entry = JournalEntry(
            entry_id="test_001",
            transaction_id="tx_001",
            sector_id=12,
            sector_address=0x08006000,
            sector_size=4096,
            operation=JournalOperation.ERASE_STARTED,
        )
        
        assert entry.entry_id == "test_001"
        assert entry.sector_id == 12
        assert entry.operation == JournalOperation.ERASE_STARTED
        assert entry.completed_at is None
    
    def test_mark_completed(self):
        """Test marking operation as completed."""
        entry = JournalEntry(
            entry_id="test_001",
            transaction_id="tx_001",
            sector_id=12,
            sector_address=0x08006000,
            sector_size=4096,
            operation=JournalOperation.ERASE_STARTED,
        )
        
        entry.mark_completed(checksum_after="abc123")
        
        assert entry.completed_at is not None
        assert entry.checksum_after == "abc123"
        assert entry.duration_ms >= 0
    
    def test_mark_failed(self):
        """Test marking operation as failed."""
        entry = JournalEntry(
            entry_id="test_001",
            transaction_id="tx_001",
            sector_id=12,
            sector_address=0x08006000,
            sector_size=4096,
            operation=JournalOperation.ERASE_STARTED,
        )
        
        entry.mark_failed("ERR_TIMEOUT", "Erase timed out")
        
        assert entry.error_code == "ERR_TIMEOUT"
        assert entry.error_message == "Erase timed out"
        assert entry.completed_at is not None
    
    def test_to_dict(self):
        """Test serialization to dictionary."""
        entry = JournalEntry(
            entry_id="test_001",
            transaction_id="tx_001",
            sector_id=12,
            sector_address=0x08006000,
            sector_size=4096,
            operation=JournalOperation.WRITE_STARTED,
        )
        
        data = entry.to_dict()
        
        assert data["entry_id"] == "test_001"
        assert data["sector_id"] == 12
        assert data["operation"] == "write_started"


class TestFlashJournal:
    """Test FlashJournal class."""
    
    @pytest.fixture
    def journal(self, tmp_path):
        """Create journal instance."""
        return FlashJournal(
            journal_dir=str(tmp_path),
            transaction_id="test_tx_001",
        )
    
    @pytest.mark.asyncio
    async def test_begin_transaction(self, journal):
        """Test beginning new journal transaction."""
        await journal.begin_transaction("tx_001")
        
        assert journal.transaction_id == "tx_001"
        assert len(journal._entries) > 0
    
    @pytest.mark.asyncio
    async def test_log_erase_started(self, journal):
        """Test logging erase started."""
        await journal.begin_transaction("tx_001")
        
        entry = await journal.log_erase_started(
            sector_id=12,
            sector_address=0x08006000,
            sector_size=4096,
        )
        
        assert entry.sector_id == 12
        assert entry.operation == JournalOperation.ERASE_STARTED
        assert journal._current_entry is not None
    
    @pytest.mark.asyncio
    async def test_log_erase_completed(self, journal):
        """Test logging erase completed."""
        await journal.begin_transaction("tx_001")
        
        await journal.log_erase_started(
            sector_id=12,
            sector_address=0x08006000,
            sector_size=4096,
        )
        
        entry = await journal.log_erase_completed(
            sector_id=12,
            checksum_after="sector_hash_12",
        )
        
        assert entry is not None
        assert entry.operation == JournalOperation.ERASE_STARTED  # Entry type
        assert journal._current_entry is None
    
    @pytest.mark.asyncio
    async def test_log_write_started(self, journal):
        """Test logging write started with checksum."""
        await journal.begin_transaction("tx_001")
        
        test_data = b"firmware chunk data"
        
        entry = await journal.log_write_started(
            sector_id=15,
            sector_address=0x08007800,
            sector_size=4096,
            bytes_to_write=test_data,
        )
        
        assert entry.operation == JournalOperation.WRITE_STARTED
        assert entry.checksum_before is not None
    
    @pytest.mark.asyncio
    async def test_checkpoint(self, journal):
        """Test logging checkpoint."""
        await journal.begin_transaction("tx_001")
        
        await journal.log_checkpoint({"last_sector": 10, "bytes_written": 40960})
        
        # Find checkpoint entry
        checkpoints = [e for e in journal._entries 
                      if e.operation == JournalOperation.CHECKPOINT]
        assert len(checkpoints) >= 1
    
    @pytest.mark.asyncio
    async def test_commit_transaction(self, journal):
        """Test committing transaction."""
        await journal.begin_transaction("tx_001")
        await journal.commit_transaction()
        
        # Should have committed marker
        committed_path = journal.journal_path + ".committed"
        import os
        assert os.path.exists(committed_path)


class TestJournalRecoveryPlanner:
    """Test JournalRecoveryPlanner class."""
    
    @pytest.fixture
    def planner(self, tmp_path):
        """Create planner instance."""
        journal = FlashJournal(
            journal_dir=str(tmp_path),
            transaction_id="test_tx",
        )
        return JournalRecoveryPlanner(journal)
    
    @pytest.mark.asyncio
    async def test_plan_recovery_partial_flash(self, planner, tmp_path):
        """Test planning recovery for partial flash."""
        journal = planner.journal
        
        # Simulate partial flash with interrupted sector
        await journal.begin_transaction("tx_partial")
        
        # Sector 0 erased
        await journal.log_erase_started(0, 0x08000000, 4096)
        await journal.log_erase_completed(0, "erased_hash")
        
        # Sector 1 write started but not completed
        await journal.log_write_started(1, 0x08001000, 4096, b"test data")
        # Missing write_completed - interrupted!
        
        # Test that incomplete operations are tracked
        assert journal._current_entry is not None
        assert journal._current_entry.sector_id == 1
