"""Tests for SVD Parser (Phase 6.3).

Unit tests for ARM CMSIS-SVD parsing.
"""

import pytest
from src.domain.hardware.svd.svd_parser import (
    SVDField,
    SVDRegister,
    SVDInterrupt,
    SVDPeripheral,
    SVDDevice,
    SVDParser,
)


class TestSVDField:
    """Test SVDField class."""
    
    def test_field_creation(self):
        """UT3.1: Create SVD field."""
        field = SVDField(
            name="RXNE",
            description="Read Data Register Not Empty",
            offset=5,
            width=1,
        )
        
        assert field.name == "RXNE"
        assert field.offset == 5
        assert field.width == 1
    
    def test_field_with_enum(self):
        """UT3.2: Create field with enum values."""
        field = SVDField(
            name="M",
            description="Word Length",
            offset=12,
            width=1,
            enum_values={0: "8_bits", 1: "9_bits"},
        )
        
        assert len(field.enum_values) == 2
        assert field.enum_values[0] == "8_bits"


class TestSVDRegister:
    """Test SVDRegister class."""
    
    def test_register_creation(self):
        """UT3.3: Create SVD register."""
        reg = SVDRegister(
            name="SR",
            address_offset=0x00,
            description="Status Register",
        )
        
        assert reg.name == "SR"
        assert reg.address_offset == 0x00
    
    def test_register_with_fields(self):
        """UT3.4: Create register with fields."""
        reg = SVDRegister(
            name="CR1",
            address_offset=0x0C,
            description="Control Register 1",
            fields=[
                SVDField(name="UE", description="USART Enable", offset=13, width=1),
            ],
        )
        
        assert len(reg.fields) == 1
        assert reg.fields[0].name == "UE"


class TestSVDInterrupt:
    """Test SVDInterrupt class."""
    
    def test_interrupt_creation(self):
        """UT3.5: Create SVD interrupt."""
        intr = SVDInterrupt(
            name="USART1_IRQn",
            value=37,
            description="USART1 global interrupt",
        )
        
        assert intr.name == "USART1_IRQn"
        assert intr.value == 37


class TestSVDPeripheral:
    """Test SVDPeripheral class."""
    
    @pytest.fixture
    def usart1(self):
        """Create USART1 peripheral."""
        return SVDPeripheral(
            name="USART1",
            base_address=0x40011000,
            description="USART1",
            registers=[
                SVDRegister(name="SR", address_offset=0x00, description="Status"),
                SVDRegister(name="DR", address_offset=0x04, description="Data"),
            ],
            interrupts=[
                SVDInterrupt(name="USART1_IRQn", value=37),
            ],
        )
    
    def test_peripheral_creation(self, usart1):
        """UT3.6: Create SVD peripheral."""
        assert usart1.name == "USART1"
        assert usart1.base_address == 0x40011000
        assert len(usart1.registers) == 2
        assert len(usart1.interrupts) == 1
    
    def test_get_register(self, usart1):
        """UT3.7: Get register by name."""
        reg = usart1.get_register("SR")
        assert reg is not None
        assert reg.name == "SR"
        
        # Case insensitive
        reg = usart1.get_register("sr")
        assert reg is not None


class TestSVDDevice:
    """Test SVDDevice class."""
    
    @pytest.fixture
    def stm32_device(self):
        """Create STM32 device."""
        return SVDDevice(
            vendor="STMicroelectronics",
            name="STM32F407",
            description="STM32F407VG",
            peripherals=[
                SVDPeripheral(
                    name="USART1",
                    base_address=0x40011000,
                    description="USART1",
                    registers=[
                        SVDRegister(name="SR", address_offset=0x00, description="Status"),
                    ],
                ),
                SVDPeripheral(
                    name="GPIOA",
                    base_address=0x40020000,
                    description="GPIO Port A",
                    registers=[
                        SVDRegister(name="MODER", address_offset=0x00, description="Mode"),
                    ],
                ),
            ],
        )
    
    def test_device_creation(self, stm32_device):
        """UT3.8: Create SVD device."""
        assert stm32_device.vendor == "STMicroelectronics"
        assert stm32_device.name == "STM32F407"
        assert len(stm32_device.peripherals) == 2
    
    def test_get_peripheral(self, stm32_device):
        """UT3.9: Get peripheral by name."""
        peri = stm32_device.get_peripheral("USART1")
        assert peri is not None
        assert peri.name == "USART1"
    
    def test_find_peripheral_by_address(self, stm32_device):
        """UT3.10: Find peripheral by address."""
        peri = stm32_device.find_peripheral_by_address(0x40011000)
        assert peri is not None
        assert peri.name == "USART1"
    
    def test_find_peripheral_outside_range(self, stm32_device):
        """UT3.11: Find peripheral outside range."""
        peri = stm32_device.find_peripheral_by_address(0x20000000)
        assert peri is None
    
    def test_get_all_registers(self, stm32_device):
        """UT3.12: Get all registers."""
        regs = stm32_device.get_all_registers()
        
        assert len(regs) == 2
        # (peripheral, name, address, size)
        assert regs[0] == ("USART1", "SR", 0x40011000, 32)


class TestSVDParser:
    """Test SVDParser class."""
    
    @pytest.fixture
    def parser(self):
        """Create SVD parser."""
        return SVDParser()
    
    @pytest.fixture
    def sample_svd(self):
        """Sample SVD XML content."""
        return """<?xml version="1.0" encoding="utf-8"?>
        <device schemaVersion="1.3">
          <vendor>STMicroelectronics</vendor>
          <name>STM32F407</name>
          <description>STM32F407VG</description>
          <peripherals>
            <peripheral>
              <name>USART1</name>
              <baseAddress>0x40011000</baseAddress>
              <description>USART1</description>
              <registers>
                <register>
                  <name>SR</name>
                  <description>Status Register</description>
                  <addressOffset>0x00</addressOffset>
                  <fields>
                    <field>
                      <name>RXNE</name>
                      <description>Read Data Register Not Empty</description>
                      <bitRange>[5:5]</bitRange>
                    </field>
                  </fields>
                </register>
              </registers>
              <interrupt>
                <name>USART1_IRQn</name>
                <value>37</value>
              </interrupt>
            </peripheral>
          </peripherals>
        </device>
        """
    
    def test_parse_string(self, parser, sample_svd):
        """UT3.13: Parse SVD from string."""
        device = parser.parse_string(sample_svd)
        
        assert device.name == "STM32F407"
        assert device.vendor == "STMicroelectronics"
        assert len(device.peripherals) == 1
        
        peri = device.get_peripheral("USART1")
        assert peri is not None
        assert peri.base_address == 0x40011000
        
        sr = peri.get_register("SR")
        assert sr is not None
        
        assert len(peri.interrupts) == 1
        assert peri.interrupts[0].name == "USART1_IRQn"
    
    def test_parse_bit_range_format(self, parser):
        """UT3.14: Parse bitRange format."""
        xml = """<?xml version="1.0" encoding="utf-8"?>
        <device schemaVersion="1.3">
          <name>TEST</name>
          <peripherals>
            <peripheral>
              <name>TEST</name>
              <baseAddress>0x40000000</baseAddress>
              <registers>
                <register>
                  <name>REG</name>
                  <addressOffset>0x00</addressOffset>
                  <fields>
                    <field>
                      <name>FIELD1</name>
                      <bitRange>[7:0]</bitRange>
                    </field>
                    <field>
                      <name>FIELD2</name>
                      <bitRange>[15:8]</bitRange>
                    </field>
                  </fields>
                </register>
              </registers>
            </peripheral>
          </peripherals>
        </device>
        """
        
        device = parser.parse_string(xml)
        reg = device.peripherals[0].registers[0]
        
        assert reg.fields[0].offset == 0
        assert reg.fields[0].width == 8
        assert reg.fields[1].offset == 8
        assert reg.fields[1].width == 8
    
    def test_parse_enum_values(self, parser):
        """UT3.15: Parse enumerated values."""
        xml = """<?xml version="1.0" encoding="utf-8"?>
        <device schemaVersion="1.3">
          <name>TEST</name>
          <peripherals>
            <peripheral>
              <name>TEST</name>
              <baseAddress>0x40000000</baseAddress>
              <registers>
                <register>
                  <name>REG</name>
                  <addressOffset>0x00</addressOffset>
                  <fields>
                    <field>
                      <name>MODE</name>
                      <bitRange>[1:0]</bitRange>
                      <enumeratedValues>
                        <enumeratedValue>
                          <name>MODE0</name>
                          <value>0</value>
                        </enumeratedValue>
                        <enumeratedValue>
                          <name>MODE1</name>
                          <value>1</value>
                        </enumeratedValue>
                      </enumeratedValues>
                    </field>
                  </fields>
                </register>
              </registers>
            </peripheral>
          </peripherals>
        </device>
        """
        
        device = parser.parse_string(xml)
        field = device.peripherals[0].registers[0].fields[0]
        
        assert field.enum_values[0] == "MODE0"
        assert field.enum_values[1] == "MODE1"
    
    def test_cache_clearing(self, parser, sample_svd):
        """UT3.16: Parser cache clearing."""
        # Parse twice
        parser.parse_string(sample_svd)
        parser.parse_string(sample_svd)
        
        assert len(parser._cache) == 0  # No file path, no cache
        
        parser.clear_cache()  # Should not raise
    
    def test_generate_register_summary(self, parser, stm32_device):
        """UT3.17: Generate register summary."""
        summary = parser.generate_register_summary(stm32_device)
        
        assert "STM32F407" in summary
        assert "USART1" in summary
        assert "0x40011000" in summary
        assert "0x40020000" in summary


class TestSVDParserHALIntegration:
    """Test SVD to HAL conversion."""
    
    @pytest.fixture
    def parser(self):
        """Create SVD parser."""
        return SVDParser()
    
    @pytest.fixture
    def sample_device(self, parser):
        """Create sample device for HAL conversion."""
        xml = """<?xml version="1.0" encoding="utf-8"?>
        <device schemaVersion="1.3">
          <name>TEST</name>
          <peripherals>
            <peripheral>
              <name>GPIOA</name>
              <baseAddress>0x40020000</baseAddress>
              <description>GPIO Port A</description>
              <registers>
                <register>
                  <name>MODER</name>
                  <description>Port Mode Register</description>
                  <addressOffset>0x00</addressOffset>
                  <size>32</size>
                  <access>read-write</access>
                </register>
              </registers>
            </peripheral>
          </peripherals>
        </device>
        """
        return parser.parse_string(xml)
    
    def test_to_hal_peripherals(self, parser, sample_device):
        """UT3.18: Convert to HAL format."""
        hal = parser.to_hal_peripherals(sample_device)
        
        assert "GPIOA" in hal
        assert hal["GPIOA"]["base_address"] == 0x40020000
        assert len(hal["GPIOA"]["registers"]) == 1
