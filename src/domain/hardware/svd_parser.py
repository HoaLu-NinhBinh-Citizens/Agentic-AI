"""SVD (CMSIS System View Description) Parser.

Parses XML SVD files to extract hardware information about peripherals,
registers, fields, interrupts, and DMA channels.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Optional
import re


@dataclass
class SVDField:
    """Represents a register field."""
    name: str
    bit_offset: int
    bit_width: int
    description: str = ""
    access: str = "RW"  # Read, Write, ReadWrite, WriteOnce, ReadOnly, WriteOnly
    enumerated_values: list[dict] = field(default_factory=list)
    reset_value: Optional[int] = None

    @property
    def bit_range(self) -> str:
        if self.bit_width == 1:
            return str(self.bit_offset)
        return f"{self.bit_offset}:{self.bit_offset + self.bit_width - 1}"


@dataclass
class SVDRegister:
    """Represents a peripheral register."""
    name: str
    address_offset: int
    description: str = ""
    size: int = 32  # bits
    access: str = "RW"
    reset_value: Optional[int] = None
    reset_mask: Optional[int] = None
    fields: list[SVDField] = field(default_factory=list)
    dim: int = 1  # Array dimension
    dim_increment: int = 4  # Bytes between array elements

    def get_absolute_address(self, peripheral_base: int) -> int:
        return peripheral_base + self.address_offset


@dataclass
class SVDInterrupt:
    """Represents an interrupt."""
    name: str
    value: int  # IRQ number


@dataclass
class SVDDMAChannel:
    """Represents a DMA channel/request."""
    name: str
    value: int  # Request number
    channel: Optional[int] = None


@dataclass
class SVDParseripheral:
    """Represents a peripheral from SVD."""
    name: str
    base_address: int
    description: str = ""
    group_name: Optional[str] = None
    prepended_to_group: bool = False
    header_struct_name: Optional[str] = None
    registers: list[SVDRegister] = field(default_factory=list)
    interrupts: list[SVDInterrupt] = field(default_factory=list)
    dma_requests: list[SVDDMAChannel] = field(default_factory=list)
    access: str = "RW"

    def get_register(self, name: str) -> Optional[SVDRegister]:
        for reg in self.registers:
            if reg.name == name:
                return reg
        return None

    def get_registers_by_prefix(self, prefix: str) -> list[SVDRegister]:
        return [r for r in self.registers if r.name.startswith(prefix)]


@dataclass
class SVDDevice:
    """Represents a complete device from SVD."""
    name: str
    vendor: str = ""
    vendor_id: str = ""
    series: str = ""
    version: str = ""
    description: str = ""
    license_text: str = ""
    address_block: list[dict] = field(default_factory=list)
    peripherals: list[SVDParseripheral] = field(default_factory=list)

    def get_peripheral(self, name: str) -> Optional[SVDParseripheral]:
        for periph in self.peripherals:
            if periph.name == name:
                return periph
        return None

    def get_peripherals_by_type(self, group_name: str) -> list[SVDParseripheral]:
        return [p for p in self.peripherals if p.group_name == group_name]


class SVDParser:
    """Parser for CMSIS SVD files."""

    SVD_NAMESPACES = {
        'svd': 'http://www.arm.com/SchemaDescription/schema_description'
    }

    def __init__(self, validate: bool = True):
        self.validate = validate
        self.device: Optional[SVDDevice] = None

    def parse_file(self, file_path: str) -> SVDDevice:
        """Parse an SVD file."""
        tree = ET.parse(file_path)
        root = tree.getroot()
        return self._parse_device(root)

    def parse_string(self, xml_content: str) -> SVDDevice:
        """Parse SVD from XML string."""
        root = ET.fromstring(xml_content)
        return self._parse_device(root)

    def _parse_device(self, element: ET.Element) -> SVDDevice:
        """Parse device element."""
        device = SVDDevice(
            name=self._get_text(element, 'name', 'Unknown'),
            vendor=self._get_text(element, 'vendor', ''),
            vendor_id=self._get_text(element, 'vendorID', ''),
            series=self._get_text(element, 'series', ''),
            version=self._get_text(element, 'version', ''),
            description=self._get_text(element, 'description', ''),
        )

        # Parse peripherals
        peripherals_elem = element.find('peripherals')
        if peripherals_elem is not None:
            for periph_elem in peripherals_elem.findall('peripheral'):
                peripheral = self._parse_peripheral(periph_elem)
                if peripheral:
                    device.peripherals.append(peripheral)

        return device

    def _parse_peripheral(self, element: ET.Element) -> Optional[SVDParseripheral]:
        """Parse peripheral element."""
        name = self._get_text(element, 'name')
        if not name:
            return None

        # Skip derived from
        if element.find('derivedFrom') is not None:
            return None

        base_address = int(self._get_text(element, 'baseAddress', '0'), 0)

        peripheral = SVDParseripheral(
            name=name,
            base_address=base_address,
            description=self._get_text(element, 'description', ''),
            group_name=self._get_text(element, 'groupName'),
            header_struct_name=self._get_text(element, 'headerStructName'),
            access=self._get_text(element, 'access', 'RW'),
        )

        # Parse registers
        registers_elem = element.find('registers')
        if registers_elem is not None:
            for reg_elem in registers_elem.findall('register'):
                register = self._parse_register(reg_elem)
                if register:
                    peripheral.registers.append(register)

        # Parse interrupts
        for irq_elem in element.findall('interrupt'):
            interrupt = self._parse_interrupt(irq_elem)
            if interrupt:
                peripheral.interrupts.append(interrupt)

        # Parse DMA channels
        dma_elem = element.find('dmaRequests')
        if dma_elem is not None:
            for dma_req in dma_elem.findall('dmaRequest'):
                channel = self._parse_dma_channel(dma_req)
                if channel:
                    peripheral.dma_requests.append(channel)

        return peripheral

    def _parse_register(self, element: ET.Element) -> Optional[SVDRegister]:
        """Parse register element."""
        name = self._get_text(element, 'name')
        if not name:
            return None

        # Skip derived from
        if element.find('derivedFrom') is not None:
            derived_name = element.find('derivedFrom').text
            # TODO: Look up derived register
            return None

        address_offset = int(self._get_text(element, 'addressOffset', '0'), 0)

        register = SVDRegister(
            name=name,
            address_offset=address_offset,
            description=self._get_text(element, 'description', ''),
            size=int(self._get_text(element, 'size', '32'), 0),
            access=self._get_text(element, 'access', 'RW'),
        )

        # Parse reset value
        reset_elem = element.find('resetValue')
        if reset_elem is not None:
            register.reset_value = int(reset_elem.text or '0', 0)

        reset_mask_elem = element.find('resetMask')
        if reset_mask_elem is not None:
            register.reset_mask = int(reset_mask_elem.text or '0', 0)

        # Parse dim (array registers)
        dim_elem = element.find('dim')
        if dim_elem is not None and dim_elem.text:
            register.dim = int(dim_elem.text, 0)

        dim_inc_elem = element.find('dimIncrement')
        if dim_inc_elem is not None and dim_inc_elem.text:
            register.dim_increment = int(dim_inc_elem.text, 0)

        # Parse fields
        fields_elem = element.find('fields')
        if fields_elem is not None:
            for field_elem in fields_elem.findall('field'):
                field = self._parse_field(field_elem)
                if field:
                    register.fields.append(field)

        return register

    def _parse_field(self, element: ET.Element) -> Optional[SVDField]:
        """Parse field element."""
        name = self._get_text(element, 'name')
        if not name:
            return None

        bit_offset = int(self._get_text(element, 'bitOffset', '0'), 0)
        bit_width_elem = element.find('bitWidth')
        bit_width = int(self._get_text(element, 'bitWidth', '1'), 0) if bit_width_elem is None else bit_width

        # Check for bitRange element
        bit_range_elem = element.find('bitRange')
        if bit_range_elem is not None and bit_range_elem.text:
            # Parse [upper:lower] format
            match = re.match(r'\[(\d+):(\d+)\]', bit_range_elem.text)
            if match:
                bit_offset = int(match.group(2))
                bit_width = int(match.group(1)) - int(match.group(2)) + 1

        field = SVDField(
            name=name,
            bit_offset=bit_offset,
            bit_width=bit_width,
            description=self._get_text(element, 'description', ''),
            access=self._get_text(element, 'access', 'RW'),
        )

        # Parse enumerated values
        values_elem = element.find('enumeratedValues')
        if values_elem is not None:
            for enum_elem in values_elem.findall('enumeratedValue'):
                value = {
                    'name': self._get_text(enum_elem, 'name', ''),
                    'value': int(self._get_text(enum_elem, 'value', '0'), 0),
                    'description': self._get_text(enum_elem, 'description', ''),
                }
                field.enumerated_values.append(value)

        return field

    def _parse_interrupt(self, element: ET.Element) -> Optional[SVDInterrupt]:
        """Parse interrupt element."""
        name = self._get_text(element, 'name')
        value_elem = element.find('value')
        if not name or value_elem is None:
            return None

        return SVDInterrupt(
            name=name,
            value=int(value_elem.text or '0', 0),
        )

    def _parse_dma_channel(self, element: ET.Element) -> Optional[SVDDMAChannel]:
        """Parse DMA channel element."""
        name = self._get_text(element, 'value')
        value_elem = element.find('value')
        if not name:
            return None

        return SVDDMAChannel(
            name=name,
            value=int(value_elem.text or '0', 0) if value_elem is not None else 0,
        )

    def _get_text(self, element: ET.Element, tag: str, default: str = '') -> str:
        """Get text content of a child element."""
        child = element.find(tag)
        return child.text.strip() if child is not None and child.text else default


def parse_svd(file_path: str) -> SVDDevice:
    """Convenience function to parse SVD file."""
    parser = SVDParser()
    return parser.parse_file(file_path)
