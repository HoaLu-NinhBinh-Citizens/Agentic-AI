"""Mock ELF fixtures for testing DWARF parsing without real firmware.

This module provides fake ELF files with realistic DWARF debug info
for testing the coredump parser and stack trace functionality.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Any


# Minimal ELF constants
ELFMAG = b"\x7fELF"
ELFCLASS32 = 1
ELFDATA2LSB = 1
EV_CURRENT = 1
ET_EXEC = 2
EM_ARM = 40

# Section types
SHT_NULL = 0
SHT_PROGBITS = 1
SHT_STRTAB = 3
SHT_SYMTAB = 2
SHT_DWARF = 0

# DWARF constants
DW_TAG_compile_unit = 0x11
DW_TAG_subprogram = 0x2e
DW_TAG_base_type = 0x24
DW_TAG_pointer_type = 0x0f
DW_TAG_variable = 0x34

DW_FORM_string = 0x08
DW_FORM_data4 = 0x06
DW_AT_name = 0x03
DW_AT_decl_file = 0x1a
DW_AT_decl_line = 0x1b
DW_AT_low_pc = 0x11
DW_AT_high_pc = 0x12
DW_AT_type = 0x49


@dataclass
class MockDWARFEntry:
    """Mock DWARF debug info entry."""
    tag: int
    attributes: dict[int, Any]


class MockELFFixture:
    """Creates minimal ELF files with DWARF debug info for testing."""
    
    def __init__(self):
        self.sections: dict[str, bytes] = {}
        self.symbols: list[dict[str, Any]] = []
        self.dwarf_entries: list[MockDWARFEntry] = []
    
    def add_function(
        self,
        name: str,
        low_pc: int,
        high_pc: int,
        decl_file: str = "main.c",
        decl_line: int = 1,
    ) -> None:
        """Add a function to the debug info."""
        self.dwarf_entries.append(MockDWARFEntry(
            tag=DW_TAG_subprogram,
            attributes={
                DW_AT_name: name,
                DW_AT_low_pc: low_pc,
                DW_AT_high_pc: high_pc,
                DW_AT_decl_file: decl_file,
                DW_AT_decl_line: decl_line,
            }
        ))
        self.symbols.append({
            "name": name,
            "value": low_pc,
            "size": high_pc - low_pc,
            "type": "function",
        })
    
    def add_variable(
        self,
        name: str,
        address: int,
        decl_file: str = "main.c",
        decl_line: int = 1,
    ) -> None:
        """Add a variable to the debug info."""
        self.dwarf_entries.append(MockDWARFEntry(
            tag=DW_TAG_variable,
            attributes={
                DW_AT_name: name,
                DW_AT_decl_file: decl_file,
                DW_AT_decl_line: decl_line,
            }
        ))
        self.symbols.append({
            "name": name,
            "value": address,
            "size": 4,
            "type": "object",
        })
    
    def add_base_type(
        self,
        name: str,
        byte_size: int,
        encoding: int = 5,  # DW_ATE_signed
    ) -> None:
        """Add a base type to the debug info."""
        self.dwarf_entries.append(MockDWARFEntry(
            tag=DW_TAG_base_type,
            attributes={
                DW_AT_name: name,
                DW_FORM_data4: byte_size,
            }
        ))
    
    def build_elf_header(self, entry_point: int = 0x08000000) -> bytes:
        """Build minimal ELF header."""
        # ELF header (52 bytes for 32-bit ARM)
        header = struct.pack(
            "<16sHHIIIIIHHHHHH",
            ELFMAG,                    # Magic
            ELFCLASS32,                # Class
            ELFDATA2LSB,              # Data encoding
            EV_CURRENT,                # Version
            0,                         # OS/ABI
            0,                         # ABI version
            0,                         # Type (ET_EXEC)
            EM_ARM,                    # Machine (ARM)
            EV_CURRENT,                # ELF version
            entry_point,               # Entry point
            0,                         # Program header offset
            0,                         # Section header offset
            0,                         # Flags
            52,                        # Header size
            0,                         # Program header entry size
            0,                         # Program header count
            0,                         # Section header entry size
            0,                         # Section header count
            0,                         # String table index
        )
        return header
    
    def build_symtab(self) -> bytes:
        """Build symbol table section."""
        entries = []
        for sym in self.symbols:
            name_offset = 0  # Simplified
            info = 0x12 if sym["type"] == "function" else 0x11  # STB_GLOBAL
            other = 0
            
            entry = struct.pack(
                "<IIBBH",
                name_offset,     # st_name
                sym["value"],   # st_value
                sym["size"],    # st_size
                info,           # st_info
                other,          # st_other
                0,              # st_shndx
            )
            entries.append(entry)
        
        return b"".join(entries)
    
    def build_strtab(self) -> bytes:
        """Build string table section."""
        # First byte is null
        strings = [b"\x00"]
        for sym in self.symbols:
            strings.append(sym["name"].encode("utf-8") + b"\x00")
        return b"".join(strings)
    
    def build_dwarf_debug_line(self) -> bytes:
        """Build minimal .debug_line section."""
        # Simplified DWARF line number program
        # In reality, this is a complex format
        header = struct.pack(
            "<IHBBHH",
            0,      # unit_length
            2,      # version
            0,      # prologue_length
            1,      # minimum_instruction_length
            1,      # maximum_operations_per_instruction
            1,      # default_is_stmt
        )
        return header
    
    def to_bytes(self) -> bytes:
        """Build complete ELF file as bytes."""
        elf = bytearray()
        
        # ELF header
        elf.extend(self.build_elf_header())
        
        # Symbol table
        elf.extend(self.build_symtab())
        
        # String table
        elf.extend(self.build_strtab())
        
        # Debug line info
        elf.extend(self.build_dwarf_debug_line())
        
        return bytes(elf)
    
    def save(self, path: str) -> None:
        """Save ELF file to path."""
        with open(path, "wb") as f:
            f.write(self.to_bytes())


def create_firmware_fixture(
    name: str = "test_firmware",
    pc: int = 0x08000100,
    sp: int = 0x20001000,
    lr: int = 0x08000200,
) -> tuple[bytes, dict[str, Any]]:
    """Create a mock firmware ELF with crash context.
    
    Returns:
        (elf_bytes, crash_context)
    """
    fixture = MockELFFixture()
    
    # Add functions
    fixture.add_function("main", 0x08000100, 0x08000150, "main.c", 10)
    fixture.add_function("process_data", 0x08000200, 0x08000280, "data.c", 25)
    fixture.add_function("handle_crash", 0x08000300, 0x08000340, "crash.c", 5)
    
    # Add variables
    fixture.add_variable("system_clock", 0x20000000, "main.c", 5)
    fixture.add_variable("buffer", 0x20000100, "data.c", 10)
    
    # Add base types
    fixture.add_base_type("int", 4)
    fixture.add_base_type("unsigned int", 4)
    fixture.add_base_type("void", 0)
    fixture.add_base_type("char", 1)
    
    elf_bytes = fixture.to_bytes()
    
    crash_context = {
        "pc": pc,
        "sp": sp,
        "lr": lr,
        "registers": {
            "r0": 0x12345678,
            "r1": 0xDEADBEEF,
            "r2": 0xCAFEBABE,
            "r3": 0x12345678,
            "r4": 0x20001000,
            "r5": 0x20001010,
            "r6": 0x20001020,
            "r7": 0x20001030,
            "r8": 0x20001040,
            "r9": 0x20001050,
            "r10": 0x20001060,
            "r11": 0x20001070,
            "r12": 0x08000300,
            "sp": sp,
            "lr": lr,
            "pc": pc,
            "xpsr": 0x01000000,
        },
        "stack_trace": [
            {"address": pc, "function": "main", "offset": 0},
            {"address": lr, "function": "process_data", "offset": 4},
        ],
    }
    
    return elf_bytes, crash_context


# Sample crash scenarios
CRASH_SCENARIOS = {
    "hardfault_nullptr": {
        "pc": 0x08000200,
        "sp": 0x20001000,
        "lr": 0x08000150,
        "fault_type": "HARD_FAULT",
        "description": "Null pointer dereference causing HardFault",
        "expected_functions": ["main", "process_data"],
    },
    "stack_overflow": {
        "pc": 0x08000300,
        "sp": 0x1FFFE000,
        "lr": 0x08000200,
        "fault_type": "STACK_OVERFLOW",
        "description": "Stack overflow detected",
        "expected_functions": ["main", "stack_overflow_test"],
    },
    "div_by_zero": {
        "pc": 0x08000250,
        "sp": 0x20001000,
        "lr": 0x08000100,
        "fault_type": "USAGE_FAULT",
        "description": "Division by zero",
        "expected_functions": ["main", "calculate"],
    },
}


def get_crash_scenario(name: str) -> dict[str, Any]:
    """Get a predefined crash scenario for testing."""
    return CRASH_SCENARIOS.get(name, CRASH_SCENARIOS["hardfault_nullptr"])


# Fixture data for coredump parsing tests
COREDUMP_FIXTURES = {
    "arm_cortex_m4_basic": {
        "format": "raw_registers",
        "registers": {
            "r0": 0x00000001, "r1": 0x00000002, "r2": 0x00000003,
            "r3": 0x00000004, "r4": 0x00000005, "r5": 0x00000006,
            "r6": 0x00000007, "r7": 0x00000008, "r8": 0x00000009,
            "r9": 0x0000000A, "r10": 0x0000000B, "r11": 0x0000000C,
            "r12": 0x0000000D,
            "sp": 0x20001000,
            "lr": 0x08000100,
            "pc": 0x08000200,
            "xpsr": 0x21000000,
        },
        "memory_regions": [
            {"start": 0x20000000, "size": 0x1000, "data": b"\xAA" * 0x100},
            {"start": 0x08000000, "size": 0x1000, "data": b"\x55" * 0x100},
        ],
    },
    "arm_cortex_m4_full": {
        "format": "elf_core",
        "registers": {
            "r0": 0x12345678, "r1": 0xDEADBEEF, "r2": 0xCAFEBABE,
            "r3": 0x12345678, "r4": 0x20001000, "r5": 0x20001010,
            "r6": 0x20001020, "r7": 0x20001030, "r8": 0x20001040,
            "r9": 0x20001050, "r10": 0x20001060, "r11": 0x20001070,
            "r12": 0x08000300,
            "sp": 0x2000FF00,
            "lr": 0x08000200,
            "pc": 0x08000300,
            "xpsr": 0x01000000,
        },
        "exception_info": {
            "type": "HARD_FAULT",
            "cfsr": 0x00008200,
            "hfsr": 0x40000000,
            "mmfar": 0xDEADBEEF,
            "bfar": 0x00000000,
        },
        "memory_regions": [
            {"start": 0x20000000, "size": 0x10000, "data": b"\x00" * 0x10000},
            {"start": 0x08000000, "size": 0x10000, "data": b"\xFF" * 0x10000},
        ],
    },
}
