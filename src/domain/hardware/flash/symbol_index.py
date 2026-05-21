"""Symbol Index - ELF/DWARF symbol indexing for crash analysis.

Phase 6.2: Implements symbol indexing for:
- Fast symbol lookup
- PC to source mapping
- Function resolution
- Integration with crash stack analysis
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SymbolInfo:
    """Information about a symbol."""
    
    name: str
    address: int
    size: int
    symbol_type: str  # function, variable, object
    
    source_file: str | None = None
    line_number: int | None = None
    
    demangled_name: str | None = None
    
    firmware_hash: str | None = None


@dataclass
class SourceLocation:
    """Source code location."""
    
    file_path: str
    line_number: int
    column: int = 0
    
    function_name: str | None = None
    
    address: int | None = None
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "file_path": self.file_path,
            "line_number": self.line_number,
            "column": self.column,
            "function_name": self.function_name,
            "address": hex(self.address) if self.address else None,
        }


@dataclass
class SymbolIndex:
    """Symbol index for firmware ELF files.
    
    Uses in-memory index with optional LMDB persistence.
    Indexes:
    - symbol_name → address
    - address → symbol_name
    - source_file → symbols
    - function → line_numbers
    """
    
    db_path: str | None = None
    
    _symbols_by_name: dict[str, list[SymbolInfo]] = field(default_factory=dict)
    _symbols_by_addr: dict[tuple[int, str], str] = field(default_factory=dict)  # (addr, hash) → name
    _symbols_by_file: dict[tuple[str, str], list[str]] = field(default_factory=dict)  # (file, hash) → names
    
    _env: Any = field(default=None, init=False)
    
    async def initialize(self) -> None:
        """Initialize symbol index."""
        if self.db_path:
            try:
                import lmdb
                import os
                os.makedirs(self.db_path, exist_ok=True)
                self._env = lmdb.open(self.db_path, map_size=100 * 1024 * 1024)
            except ImportError:
                logger.warning("lmdb_not_installed_using_memory")
                self.db_path = None
    
    async def close(self) -> None:
        """Close LMDB environment."""
        if self._env:
            self._env.close()
            self._env = None
    
    async def index_elf(self, elf_path: str, firmware_hash: str) -> int:
        """Index symbols from ELF file.
        
        Uses pyelftools to parse DWARF information.
        
        Returns:
            Number of symbols indexed
        """
        try:
            from elftools.elf.elffile import ELFFile
        except ImportError:
            logger.error("pyelftools_not_installed")
            return 0
        
        count = 0
        
        try:
            with open(elf_path, "rb") as f:
                elf = ELFFile(f)
                
                # Index symbols from symbol table
                for sym in elf.iter_symbols():
                    name = sym.name
                    if not name or name.startswith("_"):
                        continue
                    
                    info = SymbolInfo(
                        name=name,
                        address=sym["st_value"],
                        size=sym["st_size"],
                        symbol_type=self._get_symbol_type(sym["st_info"]["type"]),
                        firmware_hash=firmware_hash,
                    )
                    
                    await self.add_symbol(info)
                    count += 1
                
                # Index line information from DWARF
                if elf.has_dwarf_info():
                    dwarfinfo = elf.get_dwarf_info()
                    
                    for comp_unit in dwarfinfo.iter_CUs():
                        lineprog = dwarfinfo.line_program_for_CU(comp_unit)
                        if lineprog:
                            prev_addr = 0
                            for entry in lineprog.get_entries():
                                if entry.state and entry.state.address >= prev_addr:
                                    addr = entry.state.address
                                    filename = str(entry.state.filename) if entry.state.filename else ""
                                    line = entry.state.line
                                    
                                    if filename and line:
                                        key = (filename, firmware_hash)
                                        if key not in self._symbols_by_file:
                                            self._symbols_by_file[key] = []
                                        self._symbols_by_file[key].append(f"{addr}:{line}")
                                    
                                    prev_addr = addr
        except Exception as e:
            logger.error("elf_index_error", error=str(e))
        
        return count
    
    async def add_symbol(self, info: SymbolInfo) -> None:
        """Add symbol to index."""
        hash_key = info.firmware_hash or ""
        
        # By name
        key = info.name
        if key not in self._symbols_by_name:
            self._symbols_by_name[key] = []
        
        # Avoid duplicates
        existing = [s for s in self._symbols_by_name[key] 
                   if s.address == info.address and s.firmware_hash == info.firmware_hash]
        if not existing:
            self._symbols_by_name[key].append(info)
        
        # By address
        addr_key = (info.address, hash_key)
        self._symbols_by_addr[addr_key] = info.name
        
        # Persist to LMDB if available
        if self._env:
            await self._persist_symbol(info)
    
    async def _persist_symbol(self, info: SymbolInfo) -> None:
        """Persist symbol to LMDB."""
        if not self._env:
            return
        
        hash_key = info.firmware_hash or ""
        
        with self._env.begin(write=True) as txn:
            data = json.dumps({
                "name": info.name,
                "address": info.address,
                "size": info.size,
                "type": info.symbol_type,
                "source_file": info.source_file,
                "line_number": info.line_number,
                "demangled_name": info.demangled_name,
            })
            
            txn.put(f"sym:{info.name}:{hash_key}".encode(), str(info.address).encode())
            txn.put(f"addr:{info.address}:{hash_key}".encode(), info.name.encode())
            txn.put(f"info:{info.name}:{info.address}:{hash_key}".encode(), data.encode())
    
    async def lookup_symbol(
        self,
        name: str,
        firmware_hash: str | None = None,
    ) -> SymbolInfo | None:
        """Look up symbol by name."""
        hash_key = firmware_hash or ""
        
        symbols = self._symbols_by_name.get(name, [])
        for sym in symbols:
            if sym.firmware_hash == firmware_hash or sym.firmware_hash is None:
                return sym
        
        if symbols:
            return symbols[0]
        
        return None
    
    async def reverse_lookup(
        self,
        address: int,
        firmware_hash: str | None = None,
    ) -> str | None:
        """Reverse lookup: address → symbol name."""
        hash_key = firmware_hash or ""
        
        # Try exact match first
        key = (address, hash_key)
        if key in self._symbols_by_addr:
            return self._symbols_by_addr[key]
        
        # Try with wildcard hash
        key_wildcard = (address, "")
        if key_wildcard in self._symbols_by_addr:
            return self._symbols_by_addr[key_wildcard]
        
        # Find closest symbol <= address
        best_match = None
        best_addr = 0
        
        for (addr, h), name in self._symbols_by_addr.items():
            if addr <= address and addr > best_addr:
                if h == hash_key or h == "":
                    best_addr = addr
                    best_match = name
        
        return best_match
    
    async def map_pc_to_source(
        self,
        pc: int,
        firmware_hash: str | None = None,
    ) -> SourceLocation | None:
        """Map program counter to source location."""
        hash_key = firmware_hash or ""
        
        # Find function containing this PC
        func_name = await self.reverse_lookup(pc, firmware_hash)
        
        if not func_name:
            return None
        
        symbol = await self.lookup_symbol(func_name, firmware_hash)
        if not symbol:
            return None
        
        # Search line info
        if symbol.source_file:
            key = (symbol.source_file, hash_key)
            lines = self._symbols_by_file.get(key, [])
            
            for line_entry in lines:
                parts = line_entry.split(":")
                if len(parts) == 2:
                    addr = int(parts[0])
                    line = int(parts[1])
                    
                    if addr <= pc:
                        return SourceLocation(
                            file_path=symbol.source_file,
                            line_number=line,
                            function_name=func_name,
                            address=pc,
                        )
        
        return SourceLocation(
            file_path=symbol.source_file or "",
            line_number=symbol.line_number or 0,
            function_name=func_name,
            address=pc,
        )
    
    async def get_functions_in_file(
        self,
        file_path: str,
        firmware_hash: str | None = None,
    ) -> list[str]:
        """Get all functions defined in a source file."""
        hash_key = firmware_hash or ""
        key = (file_path, hash_key)
        
        return self._symbols_by_file.get(key, [])
    
    def _get_symbol_type(self, st_type: int) -> str:
        """Map ELF symbol type to string."""
        types = {
            0: "notype",
            1: "object",
            2: "function",
            3: "section",
            4: "file",
            5: "common",
            6: "tls",
        }
        return types.get(st_type, "unknown")
    
    async def get_stats(self) -> dict[str, Any]:
        """Get index statistics."""
        return {
            "symbols_by_name": len(self._symbols_by_name),
            "symbols_by_addr": len(self._symbols_by_addr),
            "symbols_by_file": len(self._symbols_by_file),
            "total_symbols": sum(len(v) for v in self._symbols_by_name.values()),
        }


@dataclass
class SymbolIndexUpdater:
    """Automatically updates symbol index when firmware changes."""
    
    symbol_index: SymbolIndex
    cache: dict[str, int] = field(default_factory=dict)
    
    async def update_on_flash(
        self,
        elf_path: str,
        firmware_hash: str,
        provenance: dict[str, Any] | None = None,
    ) -> int:
        """Update symbol index after firmware flash."""
        count = await self.symbol_index.index_elf(elf_path, firmware_hash)
        self.cache[firmware_hash] = count
        
        return count
    
    async def get_indexed_count(self, firmware_hash: str) -> int:
        """Get number of indexed symbols for firmware."""
        return self.cache.get(firmware_hash, 0)


@dataclass
class SourceMapper:
    """Maps PC to source location.
    
    Combines with stack unwinding from Phase 6.1 snapshots
    for complete crash analysis.
    """
    
    symbol_index: SymbolIndex
    
    async def map_stack_frame(
        self,
        pc: int,
        firmware_hash: str,
    ) -> SourceLocation | None:
        """Map stack frame PC to source location."""
        return await self.symbol_index.map_pc_to_source(pc, firmware_hash)
    
    async def map_backtrace(
        self,
        pcs: list[int],
        firmware_hash: str,
    ) -> list[SourceLocation | None]:
        """Map entire backtrace to source locations."""
        locations = []
        
        for pc in pcs:
            location = await self.map_stack_frame(pc, firmware_hash)
            locations.append(location)
        
        return locations
    
    async def format_backtrace(
        self,
        pcs: list[int],
        firmware_hash: str,
        max_frames: int = 20,
    ) -> str:
        """Format backtrace as human-readable string."""
        lines = []
        locations = await self.map_backtrace(pcs[:max_frames], firmware_hash)
        
        for i, location in enumerate(locations):
            if location:
                file_name = location.file_path.split("/")[-1] if location.file_path else "???"
                func = location.function_name or "unknown"
                line = location.line_number or "?"
                addr = hex(location.address) if location.address else "???"
                
                lines.append(
                    f"#{i:2d}  {addr} in {func} ({file_name}:{line})"
                )
            else:
                lines.append(f"#{i:2d}  ???")
        
        return "\n".join(lines)
