"""Unit tests for Flash Resume."""

import pytest
import os
import json
from src.domain.hardware.flash.flash_resume import (
    FlashResumeState,
    FlashResult,
    ResumableFlashWriter,
)


class TestFlashResumeState:
    """Tests for FlashResumeState."""
    
    def test_creation(self):
        """Test resume state creation."""
        state = FlashResumeState(
            transaction_id="tx_123",
            firmware_hash="abc123",
            firmware_size=1024,
        )
        
        assert state.transaction_id == "tx_123"
        assert state.firmware_hash == "abc123"
        assert state.firmware_size == 1024
        assert state.total_bytes_written == 0
        assert state.last_sector_written == 0
    
    def test_is_complete(self):
        """Test completion check."""
        state = FlashResumeState(
            transaction_id="tx_123",
            firmware_hash="abc",
            firmware_size=1000,
        )
        
        assert not state.is_complete()
        
        state.total_bytes_written = 1000
        assert state.is_complete()
    
    def test_remaining_bytes(self):
        """Test remaining bytes calculation."""
        state = FlashResumeState(
            transaction_id="tx",
            firmware_hash="abc",
            firmware_size=1000,
        )
        
        assert state.remaining_bytes() == 1000
        
        state.total_bytes_written = 500
        assert state.remaining_bytes() == 500
        
        state.total_bytes_written = 2000
        assert state.remaining_bytes() == 0
    
    def test_progress_percent(self):
        """Test progress percentage."""
        state = FlashResumeState(
            transaction_id="tx",
            firmware_hash="abc",
            firmware_size=1000,
        )
        
        assert state.progress_percent() == 0.0
        
        state.total_bytes_written = 500
        assert state.progress_percent() == 50.0
        
        state.total_bytes_written = 1000
        assert state.progress_percent() == 100.0
    
    def test_to_dict(self):
        """Test serialization."""
        state = FlashResumeState(
            transaction_id="tx_123",
            firmware_hash="abc",
            firmware_size=1000,
            last_sector_written=5,
            total_bytes_written=500,
        )
        
        data = state.to_dict()
        
        assert data["transaction_id"] == "tx_123"
        assert data["last_sector_written"] == 5
        assert data["total_bytes_written"] == 500
    
    def test_from_dict(self):
        """Test deserialization."""
        data = {
            "transaction_id": "tx_456",
            "firmware_hash": "def",
            "firmware_size": 2000,
            "last_sector_written": 10,
            "total_bytes_written": 1000,
            "verified_sectors": {0: "hash0", 1: "hash1"},
            "created_at": "2024-01-01T00:00:00",
            "updated_at": "2024-01-01T00:01:00",
        }
        
        state = FlashResumeState.from_dict(data)
        
        assert state.transaction_id == "tx_456"
        assert state.last_sector_written == 10
        assert state.total_bytes_written == 1000
        assert len(state.verified_sectors) == 2
    
    def test_json_roundtrip(self):
        """Test JSON serialization roundtrip."""
        state = FlashResumeState(
            transaction_id="tx_789",
            firmware_hash="xyz",
            firmware_size=500,
            verified_sectors={2: "abc", 3: "def"},
        )
        
        json_str = state.to_json()
        restored = FlashResumeState.from_json(json_str)
        
        assert restored.transaction_id == state.transaction_id
        assert restored.firmware_hash == state.firmware_hash
        assert restored.verified_sectors == state.verified_sectors


class TestFlashResult:
    """Tests for FlashResult."""
    
    def test_success_result(self):
        """Test successful result."""
        result = FlashResult(
            success=True,
            bytes_written=1024,
            sectors_erased=8,
            duration_ms=500.0,
        )
        
        assert result.success
        assert result.bytes_written == 1024
        assert result.error_code is None
    
    def test_failure_result(self):
        """Test failure result."""
        result = FlashResult(
            success=False,
            error_code="VERIFY_FAILED",
            error_message="Verification failed at sector 5",
        )
        
        assert not result.success
        assert result.error_code == "VERIFY_FAILED"
    
    def test_to_dict(self):
        """Test serialization."""
        result = FlashResult(
            success=True,
            bytes_written=1000,
            duration_ms=300.0,
        )
        
        data = result.to_dict()
        
        assert data["success"] is True
        assert data["bytes_written"] == 1000


class TestResumableFlashWriter:
    """Tests for ResumableFlashWriter."""
    
    @pytest.fixture
    def mock_probe(self):
        """Create mock probe."""
        class MockProbe:
            def __init__(self):
                self.memory = {}
            
            async def write_memory(self, addr, data):
                self.memory[addr] = data
            
            async def read_memory(self, addr, size):
                return self.memory.get(addr, b'\xff' * size)
        
        return MockProbe()
    
    @pytest.fixture
    def writer(self, tmp_path):
        """Create writer with temp directory."""
        return ResumableFlashWriter(
            probe=MockProbe(),
            resume_state_path=str(tmp_path / "resume"),
            resume_enabled=True,
        )
    
    @pytest.mark.asyncio
    async def test_no_resume_state(self, writer, mock_probe):
        """Test when no resume state exists."""
        state = await writer.check_for_resume("tx_new", "newhash")
        assert state is None
    
    @pytest.mark.asyncio
    async def test_save_and_load_state(self, tmp_path):
        """Test saving and loading resume state."""
        writer = ResumableFlashWriter(
            probe=MockProbe(),
            resume_state_path=str(tmp_path / "resume"),
            resume_enabled=True,
        )
        
        state = FlashResumeState(
            transaction_id="tx_123",
            firmware_hash="abc",
            firmware_size=1000,
            total_bytes_written=500,
        )
        
        await writer._save_state(state)
        
        loaded = await writer.check_for_resume("tx_123", "abc")
        assert loaded is not None
        assert loaded.total_bytes_written == 500
    
    @pytest.mark.asyncio
    async def test_clear_state(self, tmp_path):
        """Test clearing resume state."""
        writer = ResumableFlashWriter(
            probe=MockProbe(),
            resume_state_path=str(tmp_path / "resume"),
            resume_enabled=True,
        )
        
        state = FlashResumeState(
            transaction_id="tx_clear",
            firmware_hash="abc",
            firmware_size=1000,
        )
        
        await writer._save_state(state)
        await writer.clear_state("tx_clear")
        
        loaded = await writer.check_for_resume("tx_clear", "abc")
        assert loaded is None
    
    @pytest.mark.asyncio
    async def test_firmware_mismatch(self, tmp_path):
        """Test firmware hash mismatch detection."""
        writer = ResumableFlashWriter(
            probe=MockProbe(),
            resume_state_path=str(tmp_path / "resume"),
            resume_enabled=True,
        )
        
        state = FlashResumeState(
            transaction_id="tx_mismatch",
            firmware_hash="original_hash",
            firmware_size=1000,
        )
        
        await writer._save_state(state)
        
        # Try to resume with different hash
        loaded = await writer.check_for_resume("tx_mismatch", "different_hash")
        assert loaded is None
    
    @pytest.mark.asyncio
    async def test_list_resumable(self, tmp_path):
        """Test listing resumable transactions."""
        writer = ResumableFlashWriter(
            probe=MockProbe(),
            resume_state_path=str(tmp_path / "resume"),
            resume_enabled=True,
        )
        
        # Create incomplete state
        state1 = FlashResumeState(
            transaction_id="tx_incomplete",
            firmware_hash="hash1",
            firmware_size=1000,
            total_bytes_written=500,
        )
        await writer._save_state(state1)
        
        # Create complete state
        state2 = FlashResumeState(
            transaction_id="tx_complete",
            firmware_hash="hash2",
            firmware_size=1000,
            total_bytes_written=1000,
        )
        await writer._save_state(state2)
        
        resumable = await writer.list_resumable_transactions()
        
        # Only incomplete should be returned
        assert len(resumable) == 1
        assert resumable[0].transaction_id == "tx_incomplete"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
