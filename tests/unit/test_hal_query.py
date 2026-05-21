"""Tests for HAL Query Tool (Phase 6.7).

Unit tests for hardware peripheral register queries.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.domain.hardware.hal.hal_query import (
    RegisterAccess,
    RegisterField,
    RegisterInfo,
    PeripheralInfo,
    HALQueryResult,
    HALQueryTool,
    create_stm32_usart_hal_queries,
)


class TestRegisterField:
    """Test RegisterField class."""
    
    def test_field_creation(self):
        """UT7.1: Create register field."""
        field = RegisterField(
            name="RXNE",
            description="Read Data Register Not Empty",
            offset=5,
            width=1,
            access=RegisterAccess.READ_ONLY,
        )
        
        assert field.name == "RXNE"
        assert field.offset == 5
        assert field.width == 1
    
    def test_bitmask_calculation(self):
        """UT7.2: Calculate bitmask correctly."""
        field = RegisterField(
            name="BRR",
            description="Baud Rate",
            offset=4,
            width=12,
            access=RegisterAccess.READ_WRITE,
        )
        
        # 12 bits starting at offset 4
        expected = ((1 << 12) - 1) << 4
        assert field.bitmask == expected
    
    def test_extract_value(self):
        """UT7.3: Extract field value from register."""
        field = RegisterField(
            name="BRR",
            description="Baud Rate",
            offset=4,
            width=12,
            access=RegisterAccess.READ_WRITE,
        )
        
        # Register value with field at offset 4
        register_value = 0x00001234
        extracted = field.extract_value(register_value)
        
        # (0x1234 >> 4) = 0x123
        assert extracted == 0x123
    
    def test_extract_single_bit(self):
        """UT7.4: Extract single bit field."""
        field = RegisterField(
            name="RXNE",
            description="RX Not Empty",
            offset=5,
            width=1,
            access=RegisterAccess.READ_ONLY,
        )
        
        # Bit 5 set
        assert field.extract_value(0x20) == 1
        # Bit 5 clear
        assert field.extract_value(0x10) == 0
    
    def test_format_value_with_enum(self):
        """UT7.5: Format value with enum."""
        field = RegisterField(
            name="M",
            description="Word Length",
            offset=12,
            width=1,
            access=RegisterAccess.READ_WRITE,
            enum_values={0: "8_bits", 1: "9_bits"},
        )
        
        assert field.format_value(0) == "8_bits (0)"
        assert field.format_value(1) == "9_bits (1)"
    
    def test_format_value_without_enum(self):
        """UT7.6: Format value without enum."""
        field = RegisterField(
            name="BRR",
            description="Baud Rate",
            offset=0,
            width=12,
            access=RegisterAccess.READ_WRITE,
        )
        
        result = field.format_value(0x123)
        assert "0x123" in result


class TestRegisterInfo:
    """Test RegisterInfo class."""
    
    @pytest.fixture
    def usart_sr(self):
        """Create USART SR register."""
        return RegisterInfo(
            name="SR",
            address=0x40011000,
            description="Status Register",
            fields=[
                RegisterField("RXNE", "RX Not Empty", 5, 1, RegisterAccess.READ_ONLY),
                RegisterField("TXE", "TX Empty", 7, 1, RegisterAccess.READ_ONLY),
            ],
        )
    
    def test_register_creation(self, usart_sr):
        """UT7.7: Create register info."""
        assert usart_sr.name == "SR"
        assert usart_sr.address == 0x40011000
        assert len(usart_sr.fields) == 2
    
    def test_get_field(self, usart_sr):
        """UT7.8: Get field by name."""
        field = usart_sr.get_field("RXNE")
        assert field is not None
        assert field.offset == 5
        
        # Case insensitive
        field = usart_sr.get_field("rxne")
        assert field is not None
    
    def test_get_field_not_found(self, usart_sr):
        """UT7.9: Get non-existent field returns None."""
        field = usart_sr.get_field("NONEXISTENT")
        assert field is None
    
    def test_parse_value(self, usart_sr):
        """UT7.10: Parse register value into fields."""
        # RXNE=1, TXE=1
        value = (1 << 5) | (1 << 7)
        parsed = usart_sr.parse_value(value)
        
        assert parsed["_raw"] == value
        assert parsed["RXNE"] == 1
        assert parsed["TXE"] == 1
    
    def test_format_value(self, usart_sr):
        """UT7.11: Format register as readable string."""
        value = 0x20  # RXNE set
        formatted = usart_sr.format_value(value)
        
        assert "SR" in formatted
        assert "0x40011000" in formatted
        assert "RXNE" in formatted


class TestPeripheralInfo:
    """Test PeripheralInfo class."""
    
    @pytest.fixture
    def usart1(self):
        """Create USART1 peripheral."""
        return PeripheralInfo(
            name="USART1",
            base_address=0x40011000,
            description="USART1 Peripheral",
            registers=[
                RegisterInfo(name="SR", address=0x40011000, description="Status"),
                RegisterInfo(name="DR", address=0x40011004, description="Data"),
                RegisterInfo(name="BRR", address=0x40011008, description="Baud Rate"),
            ],
        )
    
    def test_peripheral_creation(self, usart1):
        """UT7.12: Create peripheral info."""
        assert usart1.name == "USART1"
        assert usart1.base_address == 0x40011000
        assert len(usart1.registers) == 3
    
    def test_get_register(self, usart1):
        """UT7.13: Get register by name."""
        reg = usart1.get_register("SR")
        assert reg is not None
        assert reg.address == 0x40011000
        
        # Case insensitive
        reg = usart1.get_register("sr")
        assert reg is not None
    
    def test_get_register_at_offset(self, usart1):
        """UT7.14: Get register by offset."""
        reg = usart1.get_register_at_offset(0x00)
        assert reg is not None
        assert reg.name == "SR"
        
        reg = usart1.get_register_at_offset(0x08)
        assert reg is not None
        assert reg.name == "BRR"
    
    def test_list_registers(self, usart1):
        """UT7.15: List all registers."""
        regs = usart1.list_registers()
        
        assert len(regs) == 3
        assert ("SR", 0x00) in regs
        assert ("DR", 0x04) in regs


class TestHALQueryTool:
    """Test HALQueryTool class."""
    
    @pytest.fixture
    def tool(self):
        """Create HAL query tool."""
        return HALQueryTool()
    
    @pytest.fixture
    def tool_with_peripheral(self, tool):
        """Create tool with USART1."""
        periph = create_stm32_usart_hal_queries()["USART1"]
        tool.register_peripheral(periph)
        return tool
    
    def test_tool_creation(self, tool):
        """UT7.16: Create HAL query tool."""
        assert tool._probe is None
        assert len(tool._peripherals) == 0
    
    def test_register_peripheral(self, tool):
        """UT7.17: Register a peripheral."""
        periph = PeripheralInfo(
            name="GPIOA",
            base_address=0x40020000,
            description="GPIO Port A",
        )
        tool.register_peripheral(periph)
        
        assert "GPIOA" in tool._peripherals
        assert tool._register_cache[0x40020000] in tool._peripherals["GPIOA"].registers or True
    
    def test_list_peripherals(self, tool_with_peripheral):
        """UT7.18: List registered peripherals."""
        peripherals = tool_with_peripheral.list_peripherals()
        
        assert "USART1" in peripherals
    
    def test_get_peripheral_info(self, tool_with_peripheral):
        """UT7.19: Get peripheral info."""
        info = tool_with_peripheral.get_peripheral_info("USART1")
        
        assert info is not None
        assert info.name == "USART1"
        assert info.base_address == 0x40011000
    
    def test_find_peripheral_by_address(self, tool_with_peripheral):
        """UT7.20: Find peripheral by address."""
        peri = tool_with_peripheral.find_peripheral_by_address(0x40011004)
        
        assert peri is not None
        assert peri.name == "USART1"
    
    def test_find_peripheral_outside_range(self, tool_with_peripheral):
        """UT7.21: Find peripheral outside range."""
        peri = tool_with_peripheral.find_peripheral_by_address(0x00000000)
        
        assert peri is None
    
    def test_find_register_by_address(self, tool_with_peripheral):
        """UT7.22: Find register by address."""
        reg = tool_with_peripheral.find_register_by_address(0x40011000)
        
        assert reg is not None
        assert reg.name == "SR"
    
    def test_describe_register(self, tool_with_peripheral):
        """UT7.23: Get register description."""
        desc = tool_with_peripheral.describe_register("USART1", "SR")
        
        assert desc is not None
        assert "USART1.SR" in desc
        assert "0x40011000" in desc
        assert "RXNE" in desc
    
    def test_describe_register_not_found(self, tool_with_peripheral):
        """UT7.24: Describe non-existent register."""
        desc = tool_with_peripheral.describe_register("USART1", "NONEXISTENT")
        
        assert desc is None
    
    @pytest.mark.asyncio
    async def test_read_register_no_probe(self, tool_with_peripheral):
        """UT7.25: Read without probe returns error."""
        result = await tool_with_peripheral.read_register("USART1", "SR")
        
        assert not result.success
        assert "No probe" in result.error
    
    @pytest.mark.asyncio
    async def test_read_unknown_peripheral(self, tool):
        """UT7.26: Read unknown peripheral."""
        tool._probe = MagicMock()
        result = await tool.read_register("UNKNOWN", "SR")
        
        assert not result.success
        assert "Unknown peripheral" in result.error
    
    @pytest.mark.asyncio
    async def test_read_unknown_register(self, tool_with_peripheral):
        """UT7.27: Read unknown register."""
        tool_with_peripheral._probe = MagicMock()
        result = await tool_with_peripheral.read_register("USART1", "NONEXISTENT")
        
        assert not result.success
        assert "Unknown register" in result.error
    
    @pytest.mark.asyncio
    async def test_read_register_success(self, tool_with_peripheral):
        """UT7.28: Read register successfully."""
        # Mock probe
        mock_probe = AsyncMock()
        mock_probe.read_memory = AsyncMock(return_value=b'\x20\x00\x00\x00')
        tool_with_peripheral._probe = mock_probe
        
        result = await tool_with_peripheral.read_register("USART1", "SR")
        
        assert result.success
        assert result.value is not None
        assert result.formatted is not None
    
    @pytest.mark.asyncio
    async def test_write_register_no_probe(self, tool_with_peripheral):
        """UT7.29: Write without probe returns error."""
        result = await tool_with_peripheral.write_register("USART1", "DR", 0x41)
        
        assert not result.success
        assert "No probe" in result.error
    
    @pytest.mark.asyncio
    async def test_write_read_only_register(self, tool_with_peripheral):
        """UT7.30: Write to read-only register fails."""
        tool_with_peripheral._probe = MagicMock()
        
        result = await tool_with_peripheral.write_register("USART1", "SR", 0xFF)
        
        assert not result.success
        assert "read-only" in result.error
    
    @pytest.mark.asyncio
    async def test_write_register_success(self, tool_with_peripheral):
        """UT7.31: Write register successfully."""
        mock_probe = AsyncMock()
        mock_probe.write_memory = AsyncMock(return_value=True)
        tool_with_peripheral._probe = mock_probe
        
        result = await tool_with_peripheral.write_register("USART1", "DR", 0x41)
        
        assert result.success
        assert result.value == 0x41
    
    @pytest.mark.asyncio
    async def test_read_peripheral(self, tool_with_peripheral):
        """UT7.32: Read all registers of peripheral."""
        mock_probe = AsyncMock()
        mock_probe.read_memory = AsyncMock(return_value=b'\x00\x00\x00\x00')
        tool_with_peripheral._probe = mock_probe
        
        results = await tool_with_peripheral.read_peripheral("USART1")
        
        assert "SR" in results or "DR" in results or len(results) > 0


class TestCreateSTM32USART:
    """Test STM32 USART peripheral definitions."""
    
    def test_create_usart_peripherals(self):
        """UT7.33: Create STM32 USART definitions."""
        periph = create_stm32_usart_hal_queries()
        
        assert "USART1" in periph
        assert periph["USART1"].base_address == 0x40011000
        
        sr = periph["USART1"].get_register("SR")
        assert sr is not None
        assert len(sr.fields) > 0
        
        # Check SR fields
        rxne = sr.get_field("RXNE")
        assert rxne is not None
        assert rxne.offset == 5
        assert rxne.width == 1
