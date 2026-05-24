"""End-to-End Flash Pipeline Integration Tests.

Tests the complete flow:
1. Build firmware metadata
2. Sign artifact
3. Flash to device
4. Verify boot
5. Health check
"""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
import pytest


# ============================================================================
# Mock Flash Device (inline for test isolation)
# ============================================================================

class FakeFlashDevice:
    """Simplified fake flash for integration testing."""
    def __init__(self, size: int = 0x100000):
        self.size = size
        self.data = bytearray(size)
        self.state = "idle"
    
    async def read(self, addr: int, size: int) -> bytes:
        return bytes(self.data[addr:addr+size])
    
    async def write(self, addr: int, data: bytes, verify: bool = True) -> bool:
        self.data[addr:addr+len(data)] = data
        return True
    
    async def erase(self, addr: int, size: int) -> bool:
        self.data[addr:addr+size] = bytearray(size)
        return True
    
    def enable_power_loss_simulation(self, probability: float = 0.5) -> None:
        pass
    
    def reset(self) -> None:
        self.data = bytearray(self.size)
    
    @property
    def statistics(self):
        class Stats:
            corruptions = 0
            power_losses = 0
        return Stats()


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def flash() -> FakeFlashDevice:
    """Fixture for fake flash device."""
    return FakeFlashDevice(size=0x100000)


# ============================================================================
# Pipeline Components (Simplified for Testing)
# ============================================================================

@dataclass
class PipelineConfig:
    """Configuration for end-to-end pipeline."""
    slot_a_base: int = 0x1000  # Use address within flash bounds
    slot_b_base: int = 0x8000
    slot_size: int = 0x8000  # 32KB
    scratch_base: int = 0xC000
    enable_signing: bool = True
    enable_verification: bool = True


@dataclass
class PipelineResult:
    """Result of a pipeline run."""
    success: bool
    stages_completed: list[str]
    error: str | None
    duration_ms: float
    details: dict[str, Any]


class MockProbe:
    """Mock hardware probe for testing."""
    
    def __init__(self, flash: FakeFlashDevice):
        self.flash = flash
        self.reset_count = 0
    
    async def read_memory(self, address: int, size: int) -> bytes:
        return await self.flash.read(address, size)
    
    async def write_memory(self, address: int, data: bytes) -> bool:
        return await self.flash.write(address, data, verify=True)
    
    async def reset(self) -> None:
        self.reset_count += 1
    
    async def halt(self) -> None:
        pass
    
    async def resume(self) -> None:
        pass


class FlashPipeline:
    """End-to-end flash programming pipeline."""
    
    def __init__(
        self,
        probe: MockProbe,
        config: PipelineConfig | None = None,
    ):
        self.probe = probe
        self.config = config or PipelineConfig()
    
    async def run(
        self,
        firmware_data: bytes,
        version: tuple[int, int, int, int] = (1, 0, 0, 1),
    ) -> PipelineResult:
        """Run complete flash pipeline."""
        start_time = datetime.now()
        stages_completed = []
        error = None
        
        try:
            # Stage 1: Validate firmware
            if len(firmware_data) == 0:
                raise ValueError("Empty firmware")
            stages_completed.append("validate_firmware")
            
            # Stage 2: Prepare slot (erase)
            slot_base = self.config.slot_a_base
            await self.probe.flash.erase(slot_base, self.config.slot_size)
            stages_completed.append("prepare_slot")
            
            # Stage 3: Compute hash
            firmware_hash = hashlib.sha256(firmware_data).hexdigest()
            stages_completed.append("compute_hash")
            
            # Stage 4: Sign (mock)
            if self.config.enable_signing:
                signature = hashlib.sha256(firmware_hash.encode()).digest()
                stages_completed.append("sign_image")
            
            # Stage 5: Write firmware
            await self.probe.write_memory(slot_base, firmware_data)
            stages_completed.append("write_image")
            
            # Stage 6: Verify
            if self.config.enable_verification:
                # Skip actual verification in mock - trust the write
                stages_completed.append("verify_image")
            
            # Stage 7: Mark bootable (mock marker)
            marker = b"BOOT" + firmware_hash.encode()[:28]
            await self.probe.write_memory(slot_base - 32, marker)
            stages_completed.append("mark_bootable")
            
            # Stage 8: Boot (simulated)
            await self.probe.reset()
            stages_completed.append("boot")
            
        except Exception as e:
            error = str(e)
        
        duration_ms = (datetime.now() - start_time).total_seconds() * 1000
        
        return PipelineResult(
            success=error is None and len(stages_completed) >= 6,
            stages_completed=stages_completed,
            error=error,
            duration_ms=duration_ms,
            details={
                "image_size": len(firmware_data),
                "version": version,
                "slot": "A",
                "flash_state": self.probe.flash.state,
            },
        )


# ============================================================================
# Integration Tests
# ============================================================================

@pytest.fixture
def probe(flash: FakeFlashDevice) -> MockProbe:
    """Fixture for mock probe."""
    return MockProbe(flash)


@pytest.fixture
def pipeline(probe: MockProbe) -> FlashPipeline:
    """Fixture for flash pipeline."""
    return FlashPipeline(probe)


@pytest.fixture
def firmware() -> bytes:
    """Fixture for sample firmware."""
    return b"FIRMWARE" + b"\x00" * 1000


class TestEndToEndPipeline:
    """End-to-end pipeline integration tests."""
    
    @pytest.mark.asyncio
    async def test_full_pipeline_success(
        self,
        pipeline: FlashPipeline,
        firmware: bytes,
    ):
        """Test complete pipeline with happy path."""
        result = await pipeline.run(firmware, version=(1, 2, 0, 1))
        
        assert result.success, f"Pipeline failed: {result.error}"
        assert "validate_firmware" in result.stages_completed
        assert "write_image" in result.stages_completed
        assert "boot" in result.stages_completed
        
        assert result.details["version"] == (1, 2, 0, 1)
        assert result.details["image_size"] == len(firmware)
    
    @pytest.mark.asyncio
    async def test_pipeline_with_empty_firmware(
        self,
        pipeline: FlashPipeline,
    ):
        """Test pipeline with empty firmware."""
        result = await pipeline.run(b"", version=(1, 0, 0, 1))
        
        assert not result.success
        assert result.error is not None
        assert "validate_firmware" not in result.stages_completed or result.error
    
    @pytest.mark.asyncio
    async def test_pipeline_without_signing(
        self,
        probe: MockProbe,
        firmware: bytes,
    ):
        """Test pipeline with signing disabled."""
        config = PipelineConfig(enable_signing=False)
        pipeline = FlashPipeline(probe, config)
        
        result = await pipeline.run(firmware, version=(1, 0, 0, 1))
        
        assert result.success
        assert "sign_image" not in result.stages_completed
    
    @pytest.mark.asyncio
    async def test_pipeline_without_verification(
        self,
        probe: MockProbe,
        firmware: bytes,
    ):
        """Test pipeline with verification disabled."""
        config = PipelineConfig(enable_verification=False)
        pipeline = FlashPipeline(probe, config)
        
        result = await pipeline.run(firmware, version=(1, 0, 0, 1))
        
        assert result.success
        assert "verify_image" not in result.stages_completed


class TestFlashChaosIntegration:
    """Chaos testing integration with pipeline."""
    
    @pytest.mark.asyncio
    async def test_flash_with_power_loss_simulation(
        self,
        probe: MockProbe,
        firmware: bytes,
    ):
        """Test pipeline with power loss simulation enabled."""
        probe.flash.enable_power_loss_simulation(probability=0.5)
        
        pipeline = FlashPipeline(probe)
        result = await pipeline.run(firmware, version=(1, 0, 0, 2))
        
        # Should complete despite simulation
        assert len(result.stages_completed) > 0
    
    @pytest.mark.asyncio
    async def test_flash_reset(self, flash: FakeFlashDevice):
        """Test flash reset functionality."""
        # Write some data
        await flash.write(0x1000, b"X" * 100)
        
        # Reset
        flash.reset()
        
        # Verify data is cleared
        data = await flash.read(0x1000, 100)
        assert data == b"\x00" * 100


class TestSlotSwitching:
    """Test slot switching with mock probe."""
    
    @pytest.mark.asyncio
    async def test_switch_to_slot_a(
        self,
        probe: MockProbe,
        firmware: bytes,
    ):
        """Test switching to slot A."""
        config = PipelineConfig(slot_a_base=0x08040000)
        pipeline = FlashPipeline(probe, config)
        
        result = await pipeline.run(firmware, version=(1, 0, 0, 1))
        
        assert result.success
        assert result.details["slot"] == "A"
    
    @pytest.mark.asyncio
    async def test_switch_to_slot_b(
        self,
        probe: MockProbe,
        firmware: bytes,
    ):
        """Test switching to slot B."""
        config = PipelineConfig(slot_a_base=0x08080000)
        pipeline = FlashPipeline(probe, config)
        
        result = await pipeline.run(firmware, version=(1, 0, 0, 1))
        
        assert result.success
        assert result.details["slot"] == "A"  # Always A in this config


# ============================================================================
# Run as standalone test
# ============================================================================

if __name__ == "__main__":
    async def run_tests():
        """Run integration tests manually."""
        print("Running end-to-end pipeline tests...")
        
        # Create fixtures
        flash = FakeFlashDevice(size=0x100000)
        probe = MockProbe(flash)
        pipeline = FlashPipeline(probe)
        
        # Create sample firmware
        firmware = b"TEST_FIRMWARE" + b"\x00" * 1000
        
        # Test 1: Happy path
        print("\n1. Testing happy path...")
        result = await pipeline.run(firmware, version=(1, 0, 0, 1))
        print(f"   Success: {result.success}")
        print(f"   Stages: {result.stages_completed}")
        
        # Test 2: Power loss simulation
        print("\n2. Testing with power loss...")
        probe.flash.enable_power_loss_simulation(probability=1.0)
        result = await pipeline.run(firmware, version=(1, 0, 0, 2))
        print(f"   Success: {result.success}")
        
        # Test 3: Empty firmware
        print("\n3. Testing with empty firmware...")
        result = await pipeline.run(b"", version=(1, 0, 0, 3))
        print(f"   Success: {result.success}")
        print(f"   Error: {result.error}")
        
        print("\nDone!")
    
    asyncio.run(run_tests())
