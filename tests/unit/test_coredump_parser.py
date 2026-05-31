"""Tests for Core Dump Parser (Phase 6.6).

Unit tests for ARM core dump parsing and analysis.
"""

import struct

import pytest
from src.domain.hardware.coredump.coredump_parser import (
    CoreDumpFormat,
    ExceptionType,
    RegisterSet,
    StackFrame,
    MemoryRegion,
    CoreDumpInfo,
    CoreDumpParser,
    create_mock_core_dump,
)


class TestRegisterSet:
    """Test RegisterSet class."""
    
    def test_register_set_creation(self):
        """UT6.1: Create register set."""
        regs = RegisterSet(
            r0=0x12345678,
            r1=0x87654321,
            pc=0x08001000,
            sp=0x20002000,
        )
        
        assert regs.r0 == 0x12345678
        assert regs.pc == 0x08001000
    
    def test_register_set_to_dict(self):
        """UT6.2: Convert register set to dict."""
        regs = RegisterSet(r0=0x10, r1=0x20)
        result = regs.to_dict()
        
        assert result["r0"] == 0x10
        assert result["r1"] == 0x20
        assert "sp" in result
        assert "pc" in result
    
    def test_register_set_from_bytes(self):
        """UT6.3: Parse register set from bytes."""
        data = struct.pack("<17I", 
            0x01, 0x02, 0x03, 0x04,  # R0-R3
            0x05, 0x06, 0x07, 0x08,  # R4-R7
            0x09, 0x0A, 0x0B, 0x0C,  # R8-R11
            0x0D, 0x0E, 0x0F, 0x10,  # R12, SP, LR, PC
            0x11,  # xPSR
        )
        
        regs = RegisterSet.from_bytes(data)
        
        assert regs.r0 == 0x01
        assert regs.r4 == 0x05
        assert regs.r12 == 0x0D


class TestStackFrame:
    """Test StackFrame class."""
    
    def test_stack_frame_creation(self):
        """UT6.4: Create stack frame."""
        frame = StackFrame(
            address=0x08001234,
            function_name="main",
            offset=0x10,
        )
        
        assert frame.address == 0x08001234
        assert frame.function_name == "main"
    
    def test_stack_frame_to_dict(self):
        """UT6.5: Convert stack frame to dict."""
        frame = StackFrame(
            address=0x08001234,
            function_name="main",
            source_file="main.c",
            source_line=42,
        )
        
        result = frame.to_dict()
        
        assert "0x08001234" in result["address"]
        assert result["function"] == "main"
        assert "main.c:42" in result["source"]


class TestMemoryRegion:
    """Test MemoryRegion class."""
    
    def test_memory_region_creation(self):
        """UT6.6: Create memory region."""
        data = b"\x01\x02\x03\x04"
        region = MemoryRegion(
            start=0x20000000,
            end=0x20000004,
            data=data,
        )
        
        assert region.start == 0x20000000
        assert region.size == 4
    
    def test_memory_region_address_range(self):
        """UT6.7: Get address range string."""
        region = MemoryRegion(
            start=0x20000000,
            end=0x20000100,
            data=b"\x00" * 0x100,
        )
        
        assert "0x20000000" in region.address_range
        assert "0x20000100" in region.address_range
    
    def test_memory_region_read_word(self):
        """UT6.8: Read 32-bit word."""
        data = struct.pack("<I", 0x12345678) + b"\x00" * 4
        region = MemoryRegion(
            start=0x20000000,
            end=0x20000008,
            data=data,
        )
        
        word = region.read_word(0)
        assert word == 0x12345678


class TestExceptionType:
    """Test ExceptionType enum."""
    
    def test_all_exception_types(self):
        """UT6.9: All exception types defined."""
        assert ExceptionType.HARD_FAULT.value == "hard_fault"
        assert ExceptionType.MEM_MANAGE_FAULT.value == "mem_manage_fault"
        assert ExceptionType.BUS_FAULT.value == "bus_fault"
        assert ExceptionType.USAGE_FAULT.value == "usage_fault"


class TestCoreDumpInfo:
    """Test CoreDumpInfo class."""
    
    def test_coredump_info_creation(self):
        """UT6.10: Create core dump info."""
        info = CoreDumpInfo(
            format=CoreDumpFormat.ELF_CORE,
            timestamp=123456.0,
        )
        
        assert info.format == CoreDumpFormat.ELF_CORE
        assert info.timestamp == 123456.0
        assert info.exception_type == ExceptionType.NONE
    
    def test_coredump_info_to_dict(self):
        """UT6.11: Convert to dict."""
        info = CoreDumpInfo(
            format=CoreDumpFormat.ELF_CORE,
            timestamp=1000.0,
            exception_type=ExceptionType.HARD_FAULT,
            exception_address=0x08001000,
        )
        
        result = info.to_dict()
        
        assert result["format"] == "elf_core"
        assert result["exception"]["type"] == "hard_fault"
        assert "0x08001000" in result["exception"]["address"]


class TestCoreDumpParser:
    """Test CoreDumpParser class."""
    
    @pytest.fixture
    def parser(self):
        """Create core dump parser."""
        return CoreDumpParser()
    
    @pytest.fixture
    def parser_with_symbols(self):
        """Create parser with symbol table."""
        return CoreDumpParser(symbol_table={
            0x08001000: "HardFault_Handler",
            0x08001100: "SystemInit",
            0x08001200: "main",
        })
    
    def test_parser_creation(self, parser):
        """UT6.12: Create parser."""
        assert parser._elf_file is None
        assert len(parser._symbol_table) == 0
    
    def test_lookup_symbol_exact(self, parser_with_symbols):
        """UT6.13: Lookup exact symbol."""
        name = parser_with_symbols._lookup_symbol(0x08001000)
        assert name == "HardFault_Handler"
    
    def test_lookup_symbol_nearest(self, parser_with_symbols):
        """UT6.14: Lookup nearest symbol with offset."""
        name = parser_with_symbols._lookup_symbol(0x08001020)
        assert "HardFault_Handler" in name
        assert "+0x" in name
    
    def test_lookup_symbol_not_found(self, parser):
        """UT6.15: Lookup non-existent symbol."""
        name = parser._lookup_symbol(0x10000000)
        assert name == ""
    
    def test_generate_stack_trace(self, parser_with_symbols):
        """UT6.16: Generate stack trace."""
        frames = parser_with_symbols.generate_stack_trace(
            sp=0x20002000,
            lr=0x08001200,
            pc=0x08001000,
        )
        
        assert len(frames) >= 2
        assert frames[0].address == 0x08001000  # PC
        assert "HardFault_Handler" in frames[0].function_name
    
    def test_generate_crash_report(self, parser_with_symbols):
        """UT6.17: Generate crash report."""
        info = CoreDumpInfo(
            format=CoreDumpFormat.ELF_CORE,
            timestamp=1000.0,
            exception_type=ExceptionType.HARD_FAULT,
            exception_address=0x08001000,
            registers=RegisterSet(
                pc=0x08001000,
                sp=0x20002000,
                lr=0x08001200,
            ),
        )
        info.stack_trace = parser_with_symbols.generate_stack_trace(
            sp=0x20002000,
            lr=0x08001200,
            pc=0x08001000,
        )
        
        report = parser_with_symbols.generate_crash_report(info)
        
        assert "CORE DUMP" in report
        assert "hard_fault" in report
        assert "REGISTER DUMP" in report
        assert "0x08001000" in report
    
    def test_analyze_stack_usage(self, parser):
        """UT6.18: Analyze stack usage."""
        # Create memory with some usage pattern
        memory = MemoryRegion(
            start=0x20000000,
            end=0x20001000,
            data=b"\xBE" * 0x200 + b"\x00" * 0xE00,
        )
        
        analysis = parser.analyze_stack_usage(
            sp=0x20000200,
            stack_size=0x1000,
            memory=memory,
        )
        
        assert analysis["total_size"] == 0x1000
        assert "used_bytes" in analysis
        assert "used_percent" in analysis
        assert not analysis["overflow_detected"]


class TestCreateMockCoreDump:
    """Test mock core dump creation."""
    
    def test_create_mock_coredump(self):
        """UT6.19: Create mock core dump."""
        dump = create_mock_core_dump()
        
        assert dump.startswith(b"ARM_COREDUMP")
        assert b"REGISTERS:" in dump
        assert b"EXCEPTION:" in dump


class TestCoreDumpParserFileOperations:
    """Test file-based parsing."""
    
    @pytest.fixture
    def parser(self, tmp_path):
        """Create parser with temp path."""
        return CoreDumpParser()
    
    def test_parse_nonexistent_file(self, parser, tmp_path):
        """UT6.20: Parse non-existent file raises error."""
        nonexistent = tmp_path / "nonexistent.bin"
        
        with pytest.raises(FileNotFoundError):
            parser.parse_file(nonexistent)
    
    def test_parse_custom_format(self, parser, tmp_path):
        """UT6.21: Parse custom format file."""
        dump = create_mock_core_dump()
        dump_file = tmp_path / "core.bin"
        dump_file.write_bytes(dump)
        
        info = parser.parse_file(dump_file)
        
        assert info.format == CoreDumpFormat.ELF_CORE  # Our custom format reuses this
        assert info.exception_type in [ExceptionType.HARD_FAULT, ExceptionType.UNKNOWN]
    
    def test_parse_raw_dump(self, parser, tmp_path):
        """UT6.22: Parse raw memory dump."""
        raw_data = b"\x01\x02\x03\x04" * 100
        dump_file = tmp_path / "raw.bin"
        dump_file.write_bytes(raw_data)
        
        info = parser.parse_file(dump_file)
        
        assert info.format == CoreDumpFormat.RAW_MEMORY
        assert len(info.memory_regions) == 1
        assert info.memory_regions[0].size == len(raw_data)
