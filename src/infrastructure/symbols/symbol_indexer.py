"""Symbol Indexer - PC-to-source mapping and symbol resolution.

Provides:
- ELF symbol parsing
- Address-to-symbol mapping
- Symbol lookup with demangling
- Cross-reference tracking
- Symbol versioning support
- Efficient binary search indexing

Usage:
    indexer = SymbolIndexer(elf_path="/path/to/firmware.elf")
    await indexer.build_index()
    
    # Get symbol at address
    symbol = await indexer.get_symbol_at(pc_address)
    
    # Get all symbols in range
    symbols = await indexer.get_symbols_in_range(start, end)
    
    # Find symbol by name
    symbol = await indexer.find_symbol("main")
"""

from __future__ import annotations

import asyncio
import json
import logging
import struct
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class SymbolType(Enum):
    """Symbol types."""
    NOTYPE = "notype"
    OBJECT = "object"
    FUNC = "func"
    SECTION = "section"
    FILE = "file"
    COMMON = "common"
    TLS = "tls"


class SymbolBind(Enum):
    """Symbol binding."""
    LOCAL = "local"
    GLOBAL = "global"
    WEAK = "weak"


@dataclass
class Symbol:
    """Symbol entry."""
    name: str
    address: int
    size: int
    symbol_type: SymbolType
    binding: SymbolBind
    section_index: int
    demangled_name: str = ""
    version: str = ""
    is_defined: bool = True
    is_absolute: bool = False
    is_common: bool = False
    
    @property
    def end_address(self) -> int:
        return self.address + self.size
    
    def contains(self, address: int) -> bool:
        return self.address <= address < self.end_address
    
    def __str__(self) -> str:
        if self.demangled_name:
            return f"{self.demangled_name} @ 0x{self.address:08X}"
        return f"{self.name} @ 0x{self.address:08X}"


@dataclass
class Section:
    """ELF section."""
    name: str
    index: int
    address: int
    size: int
    type: int
    flags: int
    entry_size: int = 0
    alignment: int = 1
    
    def contains(self, address: int) -> bool:
        return self.address <= address < self.address + self.size


@dataclass
class Relocation:
    """Relocation entry."""
    offset: int
    symbol_index: int
    symbol_name: str
    reloc_type: str
    addend: int = 0
    resolved: bool = False
    resolved_address: int = 0


@dataclass
class SymbolIndex:
    """Complete symbol index for an ELF file."""
    elf_path: str
    build_id: str = ""
    arch: str = ""
    entry_point: int = 0
    symbols: list[Symbol] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
    relocations: list[Relocation] = field(default_factory=list)
    created_at: str = field(default_factory=datetime.now().isoformat)
    
    def to_dict(self) -> dict:
        return {
            "elf_path": self.elf_path,
            "build_id": self.build_id,
            "arch": self.arch,
            "entry_point": f"0x{self.entry_point:08X}",
            "symbols": [
                {
                    "name": s.name,
                    "address": f"0x{s.address:08X}",
                    "size": s.size,
                    "type": s.symbol_type.value,
                    "binding": s.binding.value,
                }
                for s in self.symbols[:100]  # Limit for JSON
            ],
            "symbol_count": len(self.symbols),
            "section_count": len(self.sections),
            "created_at": self.created_at,
        }


class SymbolIndexer:
    """Symbol indexer for ELF binaries.
    
    Parses ELF files and builds efficient indexes for:
    - Address-to-symbol lookup (O(log n))
    - Symbol name lookup
    - Section lookup
    - Relocation tracking
    """
    
    # ELF constants
    ELF_MAGIC = b'\x7fELF'
    
    # Section types
    SHT_NULL = 0
    SHT_PROGBITS = 1
    SHT_SYMTAB = 2
    SHT_STRTAB = 3
    SHT_RELA = 4
    SHT_NOBITS = 8
    SHT_REL = 9
    
    # Symbol bindings
    STB_LOCAL = 0
    STB_GLOBAL = 1
    STB_WEAK = 2
    
    # Symbol types
    STT_NOTYPE = 0
    STT_OBJECT = 1
    STT_FUNC = 2
    STT_SECTION = 3
    STT_FILE = 4
    STT_COMMON = 5
    STT_TLS = 6
    
    def __init__(self, elf_path: str | Path):
        self._elf_path = Path(elf_path)
        self._elf_data: bytes | None = None
        self._index: SymbolIndex | None = None
        
        # Built indexes
        self._addr_to_symbol: dict[int, Symbol] = {}
        self._name_to_symbols: dict[str, list[Symbol]] = {}
        self._section_at_addr: dict[int, Section] = {}
        self._symbols_by_addr: list[tuple[int, Symbol]] = []
        
        self._initialized = False
    
    async def build_index(self) -> SymbolIndex:
        """Build complete symbol index."""
        if not self._elf_path.exists():
            raise FileNotFoundError(f"ELF file not found: {self._elf_path}")
        
        with open(self._elf_path, "rb") as f:
            self._elf_data = f.read()
        
        # Parse ELF header
        header = self._parse_elf_header()
        
        # Parse sections
        sections = self._parse_sections(header)
        
        # Parse symbols
        symbols = self._parse_symbols(header, sections)
        
        # Parse relocations
        relocations = self._parse_relocations(header, sections)
        
        # Build indexes
        self._build_address_index(symbols)
        self._build_name_index(symbols)
        self._build_section_index(sections)
        
        # Create index object
        self._index = SymbolIndex(
            elf_path=str(self._elf_path),
            build_id=self._get_build_id(),
            arch=self._get_arch(header),
            entry_point=header.get("e_entry", 0),
            symbols=symbols,
            sections=sections,
            relocations=relocations,
        )
        
        self._initialized = True
        
        logger.info(
            "symbol_index_built",
            path=str(self._elf_path),
            symbols=len(symbols),
            sections=len(sections),
        )
        
        return self._index
    
    def _parse_elf_header(self) -> dict[str, Any]:
        """Parse ELF header."""
        if not self._elf_data or len(self._elf_data) < 64:
            raise ValueError("Invalid ELF file")
        
        # Check magic
        if self._elf_data[:4] != self.ELF_MAGIC:
            raise ValueError("Not an ELF file")
        
        ei_class = self._elf_data[4]  # 1=32, 2=64
        ei_data = self._elf_data[5]   # 1=LE, 2=BE
        e_type = struct.unpack("<H", self._elf_data[16:18])[0]
        
        if ei_class == 1:  # 32-bit
            e_entry = struct.unpack("<I", self._elf_data[24:28])[0]
            e_phoff = struct.unpack("<I", self._elf_data[28:32])[0]
            e_shoff = struct.unpack("<I", self._elf_data[32:36])[0]
            e_flags = struct.unpack("<I", self._elf_data[36:40])[0]
            e_ehsize = struct.unpack("<H", self._elf_data[40:42])[0]
            e_phentsize = struct.unpack("<H", self._elf_data[42:44])[0]
            e_phnum = struct.unpack("<H", self._elf_data[44:46])[0]
            e_shentsize = struct.unpack("<H", self._elf_data[46:48])[0]
            e_shnum = struct.unpack("<H", self._elf_data[48:50])[0]
            e_shstrndx = struct.unpack("<H", self._elf_data[50:52])[0]
        else:  # 64-bit
            e_entry = struct.unpack("<Q", self._elf_data[24:32])[0]
            e_phoff = struct.unpack("<Q", self._elf_data[32:40])[0]
            e_shoff = struct.unpack("<Q", self._elf_data[40:48])[0]
            e_flags = struct.unpack("<I", self._elf_data[48:52])[0]
            e_ehsize = struct.unpack("<H", self._elf_data[52:54])[0]
            e_phentsize = struct.unpack("<H", self._elf_data[54:56])[0]
            e_phnum = struct.unpack("<H", self._elf_data[56:58])[0]
            e_shentsize = struct.unpack("<H", self._elf_data[58:60])[0]
            e_shnum = struct.unpack("<H", self._elf_data[60:62])[0]
            e_shstrndx = struct.unpack("<H", self._elf_data[62:64])[0]
        
        return {
            "ei_class": ei_class,
            "ei_data": ei_data,
            "e_type": e_type,
            "e_entry": e_entry,
            "e_shoff": e_shoff,
            "e_shentsize": e_shentsize,
            "e_shnum": e_shnum,
            "e_shstrndx": e_shstrndx,
        }
    
    def _parse_sections(self, header: dict[str, Any]) -> list[Section]:
        """Parse ELF sections."""
        sections = []
        strtab_data = b""
        
        e_shoff = header["e_shoff"]
        e_shentsize = header["e_shentsize"]
        e_shnum = header["e_shnum"]
        e_shstrndx = header["e_shstrndx"]
        is_64bit = header["ei_class"] == 2
        
        # Read string table
        if e_shstrndx > 0 and e_shoff > 0:
            strtab_offset = self._get_section_offset(header, e_shstrndx)
            if strtab_offset:
                strtab_offset += strtab_offset  # sh_offset
                # Re-read section header
                strtab_hdr = self._read_section_header(header, e_shstrndx)
                strtab_data = self._read_section_data(header, strtab_hdr)
        
        # Parse all section headers
        for i in range(e_shnum):
            sec_hdr = self._read_section_header(header, i)
            if not sec_hdr:
                continue
            
            name_offset = sec_hdr["sh_name"]
            name = self._read_string(strtab_data, name_offset)
            
            section = Section(
                name=name,
                index=i,
                address=sec_hdr["sh_addr"],
                size=sec_hdr["sh_size"],
                type=sec_hdr["sh_type"],
                flags=sec_hdr["sh_flags"],
                entry_size=sec_hdr.get("sh_entsize", 0),
                alignment=sec_hdr.get("sh_addralign", 1),
            )
            
            sections.append(section)
        
        return sections
    
    def _read_section_header(self, header: dict[str, Any], index: int) -> dict[str, int]:
        """Read a section header."""
        e_shoff = header["e_shoff"]
        e_shentsize = header["e_shentsize"]
        is_64bit = header["ei_class"] == 2
        
        offset = e_shoff + index * e_shentsize
        
        if is_64bit:
            if offset + 64 > len(self._elf_data):
                return {}
            return {
                "sh_name": struct.unpack("<I", self._elf_data[offset:offset + 4])[0],
                "sh_type": struct.unpack("<I", self._elf_data[offset + 4:offset + 8])[0],
                "sh_flags": struct.unpack("<Q", self._elf_data[offset + 8:offset + 16])[0],
                "sh_addr": struct.unpack("<Q", self._elf_data[offset + 16:offset + 24])[0],
                "sh_offset": struct.unpack("<Q", self._elf_data[offset + 24:offset + 32])[0],
                "sh_size": struct.unpack("<Q", self._elf_data[offset + 32:offset + 40])[0],
                "sh_link": struct.unpack("<I", self._elf_data[offset + 40:offset + 44])[0],
                "sh_info": struct.unpack("<I", self._elf_data[offset + 44:offset + 48])[0],
                "sh_addralign": struct.unpack("<Q", self._elf_data[offset + 48:offset + 56])[0],
                "sh_entsize": struct.unpack("<Q", self._elf_data[offset + 56:offset + 64])[0],
            }
        else:
            if offset + 40 > len(self._elf_data):
                return {}
            return {
                "sh_name": struct.unpack("<I", self._elf_data[offset:offset + 4])[0],
                "sh_type": struct.unpack("<I", self._elf_data[offset + 4:offset + 8])[0],
                "sh_flags": struct.unpack("<I", self._elf_data[offset + 8:offset + 12])[0],
                "sh_addr": struct.unpack("<I", self._elf_data[offset + 12:offset + 16])[0],
                "sh_offset": struct.unpack("<I", self._elf_data[offset + 16:offset + 20])[0],
                "sh_size": struct.unpack("<I", self._elf_data[offset + 20:offset + 24])[0],
                "sh_link": struct.unpack("<I", self._elf_data[offset + 24:offset + 28])[0],
                "sh_info": struct.unpack("<I", self._elf_data[offset + 28:offset + 32])[0],
                "sh_addralign": struct.unpack("<I", self._elf_data[offset + 32:offset + 36])[0],
                "sh_entsize": struct.unpack("<I", self._elf_data[offset + 36:offset + 40])[0],
            }
    
    def _get_section_offset(self, header: dict[str, Any], index: int) -> int | None:
        """Get section file offset."""
        sec_hdr = self._read_section_header(header, index)
        if not sec_hdr:
            return None
        return sec_hdr.get("sh_offset", 0)
    
    def _read_section_data(self, header: dict[str, Any], sec_hdr: dict[str, int]) -> bytes:
        """Read section data."""
        offset = sec_hdr.get("sh_offset", 0)
        size = sec_hdr.get("sh_size", 0)
        return self._elf_data[offset:offset + size] if self._elf_data else b""
    
    def _read_string(self, data: bytes, offset: int) -> str:
        """Read null-terminated string."""
        if offset >= len(data):
            return ""
        end = data.find(b'\x00', offset)
        if end < 0:
            return ""
        return data[offset:end].decode('utf-8', errors='replace')
    
    def _parse_symbols(self, header: dict[str, Any], sections: list[Section]) -> list[Symbol]:
        """Parse symbol table."""
        symbols = []
        
        # Find .symtab and .strtab sections
        symtab = None
        strtab = None
        for sec in sections:
            if sec.name == ".symtab":
                symtab = sec
            elif sec.name == ".strtab":
                strtab = sec
        
        if not symtab or not strtab:
            return symbols
        
        # Read string table
        strtab_hdr = self._read_section_header(header, strtab.index)
        strtab_data = self._read_section_data(header, strtab_hdr)
        
        # Read symbol entries
        entry_size = symtab.entry_size if symtab.entry_size > 0 else (16 if header["ei_class"] == 2 else 12)
        
        is_64bit = header["ei_class"] == 2
        symtab_offset = self._get_section_offset(header, symtab.index)
        symtab_data = self._read_section_data(header, symtab_hdr := {
            **symtab.__dict__,
            **self._read_section_header(header, symtab.index)
        }) if False else self._elf_data[symtab_offset:symtab_offset + symtab.size] if self._elf_data else b""
        
        offset = 0
        sym_index = 0
        
        while offset + entry_size <= len(symtab_data):
            if is_64bit:
                st_name = struct.unpack("<I", symtab_data[offset:offset + 4])[0]
                st_info = symtab_data[offset + 4]
                st_other = symtab_data[offset + 5]
                st_shndx = struct.unpack("<H", symtab_data[offset + 6:offset + 8])[0]
                st_value = struct.unpack("<Q", symtab_data[offset + 8:offset + 16])[0]
                st_size = struct.unpack("<Q", symtab_data[offset + 16:offset + 24])[0]
            else:
                st_name = struct.unpack("<I", symtab_data[offset:offset + 4])[0]
                st_value = struct.unpack("<I", symtab_data[offset + 4:offset + 8])[0]
                st_size = struct.unpack("<I", symtab_data[offset + 8:offset + 12])[0]
                st_info = symtab_data[offset + 12]
                st_other = symtab_data[offset + 13]
                st_shndx = struct.unpack("<H", symtab_data[offset + 14:offset + 16])[0]
            
            # Parse binding and type
            binding = (st_info >> 4) & 0xF
            sym_type = st_info & 0xF
            
            name = self._read_string(strtab_data, st_name)
            
            # Skip empty symbols
            if not name and sym_type != self.STT_SECTION:
                offset += entry_size
                sym_index += 1
                continue
            
            # Map to enums
            symbol_type = self._map_symbol_type(sym_type)
            symbol_bind = self._map_symbol_bind(binding)
            
            # Get section info
            section = sections[st_shndx] if st_shndx < len(sections) else None
            
            symbol = Symbol(
                name=name,
                address=st_value,
                size=st_size,
                symbol_type=symbol_type,
                binding=symbol_bind,
                section_index=st_shndx,
                is_defined=st_shndx != 0,
                is_absolute=st_shndx == 0xFFFF,  # SHN_ABS
                is_common=sym_type == self.STT_COMMON,
            )
            
            # Demangle if possible
            symbol.demangled_name = self._try_demangle(name)
            
            symbols.append(symbol)
            
            offset += entry_size
            sym_index += 1
        
        return symbols
    
    def _map_symbol_type(self, st_type: int) -> SymbolType:
        """Map ELF symbol type to enum."""
        types = {
            self.STT_NOTYPE: SymbolType.NOTYPE,
            self.STT_OBJECT: SymbolType.OBJECT,
            self.STT_FUNC: SymbolType.FUNC,
            self.STT_SECTION: SymbolType.SECTION,
            self.STT_FILE: SymbolType.FILE,
            self.STT_COMMON: SymbolType.COMMON,
            self.STT_TLS: SymbolType.TLS,
        }
        return types.get(st_type, SymbolType.NOTYPE)
    
    def _map_symbol_bind(self, st_bind: int) -> SymbolBind:
        """Map ELF symbol binding to enum."""
        binds = {
            self.STB_LOCAL: SymbolBind.LOCAL,
            self.STB_GLOBAL: SymbolBind.GLOBAL,
            self.STB_WEAK: SymbolBind.WEAK,
        }
        return binds.get(st_bind, SymbolBind.LOCAL)
    
    def _try_demangle(self, name: str) -> str:
        """Try to demangle C++ symbol name."""
        # Simple C++ name demangling (Itanium ABI)
        if not name.startswith("_Z"):
            return ""
        
        try:
            # Very simplified demangler
            return self._demangle_itanium(name)
        except Exception:
            return ""
    
    def _demangle_itanium(self, name: str) -> str:
        """Simplified Itanium C++ ABI demangler."""
        if not name.startswith("_Z"):
            return name
        
        pos = 2  # Skip "_Z"
        
        def parse_name():
            nonlocal pos
            length = 0
            while pos < len(name) and name[pos].isdigit():
                length = length * 10 + int(name[pos])
                pos += 1
            if length > 0:
                result = name[pos:pos + length]
                pos += length
                return result
            return None
        
        # Parse nested names
        parts = []
        while pos < len(name):
            if name[pos] == 'N':
                pos += 1
                while True:
                    p = parse_name()
                    if p:
                        parts.append(p)
                    if pos < len(name) and name[pos] == 'E':
                        pos += 1
                        break
            else:
                p = parse_name()
                if p:
                    parts.append(p)
                break
        
        return "::".join(parts) if parts else name
    
    def _parse_relocations(self, header: dict[str, Any], sections: list[Section]) -> list[Relocation]:
        """Parse relocation entries."""
        relocations = []
        
        for sec in sections:
            if sec.type not in (self.SHT_REL, self.SHT_RELA):
                continue
            
            sec_hdr = self._read_section_header(header, sec.index)
            data = self._read_section_data(header, sec_hdr)
            
            entry_size = sec.entry_size if sec.entry_size > 0 else (16 if header["ei_class"] == 2 else 8)
            
            offset = 0
            while offset + entry_size <= len(data):
                if header["ei_class"] == 2:  # 64-bit
                    r_offset = struct.unpack("<Q", data[offset:offset + 8])[0]
                    r_info = struct.unpack("<Q", data[offset + 8:offset + 16])[0]
                    if sec.type == self.SHT_RELA:
                        r_addend = struct.unpack("<q", data[offset + 16:offset + 24])[0]
                    else:
                        r_addend = 0
                else:  # 32-bit
                    r_offset = struct.unpack("<I", data[offset:offset + 4])[0]
                    r_info = struct.unpack("<I", data[offset + 4:offset + 8])[0]
                    r_addend = struct.unpack("<i", data[offset + 8:offset + 12])[0] if sec.type == self.SHT_RELA else 0
                
                reloc = Relocation(
                    offset=r_offset,
                    symbol_index=r_info >> 8,
                    symbol_name="",
                    reloc_type=self._get_reloc_type_name(r_info & 0xFF),
                    addend=r_addend,
                )
                relocations.append(reloc)
                
                offset += entry_size
        
        return relocations
    
    def _get_reloc_type_name(self, r_type: int) -> str:
        """Get relocation type name."""
        arm_reloc_types = {
            1: "R_ARM_JUMP_SLOT", 2: "R_ARM_GLOB_DAT", 3: "R_ARM_RELATIVE",
            4: "R_ARM_ABS32", 5: "R_ARM_REL32", 28: "R_ARM_CALL",
        }
        return arm_reloc_types.get(r_type, f"R_ARM_{r_type}")
    
    def _get_build_id(self) -> str:
        """Get build ID if present."""
        for sec in self._index.sections if self._index else []:
            if sec.name == ".note.gnu.build-id":
                # Read build ID
                pass
        return ""
    
    def _get_arch(self, header: dict[str, Any]) -> str:
        """Get architecture."""
        # Check machine type
        machine = struct.unpack("<H", self._elf_data[18:20])[0]
        arches = {
            0x28: "ARM",
            0xB6: "ARMv8-M",
            0xF3: "RISC-V",
            0x03: "i386",
            0x3E: "x86_64",
        }
        return arches.get(machine, f"Unknown(0x{machine:04X})")
    
    def _build_address_index(self, symbols: list[Symbol]) -> None:
        """Build address-to-symbol index with binary search."""
        # Sort by address
        self._symbols_by_addr = sorted(
            [(s.address, s) for s in symbols if s.is_defined],
            key=lambda x: x[0]
        )
        
        # Add to dict for O(1) exact lookup
        for sym in symbols:
            self._addr_to_symbol[sym.address] = sym
    
    def _build_name_index(self, symbols: list[Symbol]) -> None:
        """Build name-to-symbols index."""
        for sym in symbols:
            if sym.name not in self._name_to_symbols:
                self._name_to_symbols[sym.name] = []
            self._name_to_symbols[sym.name].append(sym)
    
    def _build_section_index(self, sections: list[Section]) -> None:
        """Build section-by-address index."""
        for sec in sections:
            if sec.address > 0:
                self._section_at_addr[sec.address] = sec
    
    async def get_symbol_at(self, address: int) -> Symbol | None:
        """Get symbol containing an address."""
        if not self._initialized:
            return None
        
        # Binary search for containing symbol
        left, right = 0, len(self._symbols_by_addr) - 1
        result = None
        
        while left <= right:
            mid = (left + right) // 2
            addr, sym = self._symbols_by_addr[mid]
            
            if sym.contains(address):
                return sym
            elif address < sym.address:
                right = mid - 1
            else:
                result = sym  # Remember the closest below
                left = mid + 1
        
        return result
    
    async def get_symbols_in_range(self, start: int, end: int) -> list[Symbol]:
        """Get all symbols within an address range."""
        if not self._initialized:
            return []
        
        symbols = []
        for addr, sym in self._symbols_by_addr:
            if addr >= start and addr < end:
                symbols.append(sym)
            elif addr > end:
                break
        
        return symbols
    
    async def find_symbol(self, name: str) -> list[Symbol]:
        """Find symbols by name."""
        if not self._initialized:
            return []
        
        return self._name_to_symbols.get(name, [])
    
    async def get_function_at(self, address: int) -> Symbol | None:
        """Get function symbol at address."""
        sym = await self.get_symbol_at(address)
        if sym and sym.symbol_type == SymbolType.FUNC:
            return sym
        return None
    
    async def get_section_at(self, address: int) -> Section | None:
        """Get section containing address."""
        if not self._initialized:
            return None
        
        # Find closest section start
        for sec_addr in sorted(self._section_at_addr.keys(), reverse=True):
            if sec_addr <= address:
                sec = self._section_at_addr[sec_addr]
                if sec.contains(address):
                    return sec
        
        return None
    
    def get_index(self) -> SymbolIndex | None:
        """Get the complete symbol index."""
        return self._index


# Global cache
_index_cache: dict[str, SymbolIndexer] = {}


def get_symbol_indexer(elf_path: str | Path) -> SymbolIndexer:
    """Get or create symbol indexer."""
    path = str(elf_path)
    
    if path not in _index_cache:
        _index_cache[path] = SymbolIndexer(elf_path)
    
    return _index_cache[path]


async def index_elf_symbols(elf_path: str | Path) -> SymbolIndex | None:
    """Build and return symbol index for an ELF file."""
    indexer = get_symbol_indexer(elf_path)
    
    if not indexer._initialized:
        await indexer.build_index()
    
    return indexer.get_index()


if __name__ == "__main__":
    print("Symbol Indexer")
    print("=" * 40)
    print("PC-to-source mapping and symbol resolution")
    print()
    print("Features:")
    print("  - ELF symbol parsing")
    print("  - O(log n) address-to-symbol lookup")
    print("  - Symbol demangling")
    print("  - Section tracking")
    print("  - Relocation support")
