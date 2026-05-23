"""Tests for STM32 simulator."""

import pytest
from src.infrastructure.hil.stm32_simulator import (
    STM32Simulator,
    SimulatorState,
    MemoryRegion,
    Breakpoint,
)


class TestMemoryRegion:
    def test_memory_region_properties(self):
        region = MemoryRegion("flash", 0x08000000, 0x100000)
        assert region.name == "flash"
        assert region.start == 0x08000000
        assert region.end == 0x08100000
        assert region.size == 0x100000


class TestBreakpoint:
    def test_breakpoint_creation(self):
        bp = Breakpoint(address=0x08000000)
        assert bp.address == 0x08000000
        assert bp.enabled is True
        assert bp.condition == ""


class TestSTM32Simulator:
    def test_simulator_creation(self):
        sim = STM32Simulator()
        assert sim._machine == "STM32F407VG"
        assert sim.get_state() == SimulatorState.STOPPED

    def test_memory_regions(self):
        sim = STM32Simulator()
        regions = sim.get_memory_regions()
        assert len(regions) == 3
        assert any(r.name == "flash" for r in regions)
        assert any(r.name == "sram1" for r in regions)

    def test_breakpoint_management(self):
        sim = STM32Simulator()
        bp_id = sim.add_breakpoint(0x08000000)
        assert bp_id == 0
        assert len(sim._breakpoints) == 1

        assert sim.remove_breakpoint(0) is True
        assert len(sim._breakpoints) == 0

    def test_register_operations(self):
        sim = STM32Simulator()
        sim._registers.pc = 0x08000000
        
        assert sim.read_register("pc") == 0x08000000
        assert sim.write_register("pc", 0x08000010) is True
        assert sim.read_register("pc") == 0x08000010
        
        assert sim.read_register("nonexistent") == 0
