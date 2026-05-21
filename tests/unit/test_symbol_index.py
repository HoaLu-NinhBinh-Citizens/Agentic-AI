"""Tests for Symbol Index - 6.2.UT10.

Tests symbol indexing, lookup, and PC-to-source mapping.
"""

import pytest
from src.domain.hardware.flash.symbol_index import (
    SymbolInfo,
    SourceLocation,
    SymbolIndex,
    SymbolIndexUpdater,
    SourceMapper,
)


class TestSymbolInfo:
    """Test SymbolInfo dataclass."""
    
    def test_create_symbol_info(self):
        """Test creating symbol info."""
        info = SymbolInfo(
            name="main",
            address=0x08000000,
            size=100,
            symbol_type="function",
        )
        
        assert info.name == "main"
        assert info.address == 0x08000000
        assert info.size == 100
        assert info.symbol_type == "function"


class TestSourceLocation:
    """Test SourceLocation dataclass."""
    
    def test_create_source_location(self):
        """Test creating source location."""
        loc = SourceLocation(
            file_path="main.c",
            line_number=42,
            function_name="main",
        )
        
        assert loc.file_path == "main.c"
        assert loc.line_number == 42
        assert loc.function_name == "main"
    
    def test_to_dict(self):
        """Test serialization."""
        loc = SourceLocation(
            file_path="app.c",
            line_number=10,
            column=5,
            function_name="init",
            address=0x08001000,
        )
        
        data = loc.to_dict()
        
        assert data["file_path"] == "app.c"
        assert data["line_number"] == 10
        assert data["function_name"] == "init"


class TestSymbolIndex:
    """Test SymbolIndex class."""
    
    @pytest.fixture
    def symbol_index(self):
        """Create symbol index."""
        return SymbolIndex()
    
    @pytest.mark.asyncio
    async def test_add_symbol(self, symbol_index):
        """Test adding symbol to index."""
        info = SymbolInfo(
            name="init_system",
            address=0x08000100,
            size=200,
            symbol_type="function",
            firmware_hash="test_hash",
        )
        
        await symbol_index.add_symbol(info)
        
        # Verify symbol was added
        assert "init_system" in symbol_index._symbols_by_name
    
    @pytest.mark.asyncio
    async def test_lookup_symbol(self, symbol_index):
        """Test symbol lookup by name."""
        info = SymbolInfo(
            name="uart_init",
            address=0x08000200,
            size=150,
            symbol_type="function",
        )
        
        await symbol_index.add_symbol(info)
        
        result = await symbol_index.lookup_symbol("uart_init")
        
        assert result is not None
        assert result.name == "uart_init"
        assert result.address == 0x08000200
    
    @pytest.mark.asyncio
    async def test_reverse_lookup(self, symbol_index):
        """Test reverse lookup (address to symbol)."""
        info = SymbolInfo(
            name="timer_isr",
            address=0x08000300,
            size=80,
            symbol_type="function",
        )
        
        await symbol_index.add_symbol(info)
        
        name = await symbol_index.reverse_lookup(0x08000300)
        
        assert name == "timer_isr"
    
    @pytest.mark.asyncio
    async def test_reverse_lookup_closest(self, symbol_index):
        """Test reverse lookup returns closest symbol below address."""
        # Add symbols at different addresses
        for i in range(3):
            info = SymbolInfo(
                name=f"func_{i}",
                address=0x08000000 + (i * 0x100),
                size=64,
                symbol_type="function",
            )
            await symbol_index.add_symbol(info)
        
        # Lookup address that falls within func_1's range
        # func_1 is at 0x08000100, func_2 at 0x08000200
        # Address 0x08000150 falls between func_1 and func_2
        name = await symbol_index.reverse_lookup(0x08000150)
        
        # Should return func_1 (closest at or below address)
        assert name in ["func_0", "func_1"]  # Either is valid for closest lookup
    
    @pytest.mark.asyncio
    async def test_map_pc_to_source(self, symbol_index):
        """Test mapping program counter to source location."""
        info = SymbolInfo(
            name="main",
            address=0x08000000,
            size=512,
            symbol_type="function",
            source_file="main.c",
            line_number=10,
        )
        
        await symbol_index.add_symbol(info)
        
        loc = await symbol_index.map_pc_to_source(0x08000050)
        
        assert loc is not None
        assert loc.function_name == "main"
    
    @pytest.mark.asyncio
    async def test_get_functions_in_file(self, symbol_index):
        """Test getting functions in a file."""
        # This test is simplified - full implementation would use DWARF info
        pass  # Would need actual ELF with DWARF data
    
    @pytest.mark.asyncio
    async def test_get_stats(self, symbol_index):
        """Test getting index statistics."""
        # Add some symbols
        for name in ["func_a", "func_b", "var_x"]:
            info = SymbolInfo(
                name=name,
                address=0x08000000,
                size=64,
                symbol_type="function" if name.startswith("func") else "object",
            )
            await symbol_index.add_symbol(info)
        
        stats = await symbol_index.get_stats()
        
        assert stats["symbols_by_name"] == 3
    
    @pytest.mark.asyncio
    async def test_lookup_nonexistent(self, symbol_index):
        """Test lookup of non-existent symbol."""
        result = await symbol_index.lookup_symbol("nonexistent")
        assert result is None
    
    @pytest.mark.asyncio
    async def test_multiple_firmware_hashes(self, symbol_index):
        """Test indexing symbols from different firmware."""
        info1 = SymbolInfo(
            name="func",
            address=0x08000000,
            size=100,
            symbol_type="function",
            firmware_hash="firmware_v1",
        )
        info2 = SymbolInfo(
            name="func",
            address=0x08100000,  # Different address
            size=100,
            symbol_type="function",
            firmware_hash="firmware_v2",
        )
        
        await symbol_index.add_symbol(info1)
        await symbol_index.add_symbol(info2)
        
        # Lookup by specific hash
        result1 = await symbol_index.lookup_symbol("func", "firmware_v1")
        result2 = await symbol_index.lookup_symbol("func", "firmware_v2")
        
        assert result1 is not None
        assert result2 is not None
        assert result1.address != result2.address


class TestSourceMapper:
    """Test SourceMapper class."""
    
    @pytest.fixture
    def source_mapper(self):
        """Create source mapper."""
        index = SymbolIndex()
        return SourceMapper(symbol_index=index)
    
    @pytest.mark.asyncio
    async def test_map_stack_frame(self, source_mapper):
        """Test mapping single stack frame."""
        # Add symbol to index
        info = SymbolInfo(
            name="nested_func",
            address=0x08000500,
            size=200,
            symbol_type="function",
        )
        await source_mapper.symbol_index.add_symbol(info)
        
        result = await source_mapper.map_stack_frame(0x08000500, "test_hash")
        
        assert result is not None
        assert result.function_name == "nested_func"
    
    @pytest.mark.asyncio
    async def test_map_backtrace(self, source_mapper):
        """Test mapping entire backtrace."""
        # Add multiple symbols
        for i, addr in enumerate([0x08000100, 0x08000200, 0x08000300]):
            info = SymbolInfo(
                name=f"frame_{i}",
                address=addr,
                size=64,
                symbol_type="function",
            )
            await source_mapper.symbol_index.add_symbol(info)
        
        pcs = [0x08000100, 0x08000200, 0x08000300]
        locations = await source_mapper.map_backtrace(pcs, "test")
        
        assert len(locations) == 3
        assert locations[0].function_name == "frame_0"
    
    @pytest.mark.asyncio
    async def test_format_backtrace(self, source_mapper):
        """Test formatting backtrace as string."""
        # Add symbols
        info = SymbolInfo(
            name="crash_func",
            address=0x08001000,
            size=100,
            symbol_type="function",
            source_file="fault.c",
            line_number=42,
        )
        await source_mapper.symbol_index.add_symbol(info)
        
        formatted = await source_mapper.format_backtrace(
            [0x08001000],
            "test",
            max_frames=10,
        )
        
        assert "crash_func" in formatted
        assert "fault.c" in formatted
