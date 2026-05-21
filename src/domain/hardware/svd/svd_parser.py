"""SVD Parser - ARM CMSIS-SVD file parser.

Phase 6.3: SVD Parser
- Parse ARM CMSIS-SVD XML files
- Extract peripheral definitions
- Extract register definitions with fields
- Extract interrupt definitions
- Generate HAL query data structures
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = __import__("structlog").get_logger(__name__)


@dataclass
class SVDField:
    """Field definition from SVD."""
    
    name: str
    description: str
    offset: int
    width: int
    access: str = "read-write"
    reset_value: int | None = None
    enum_values: dict[int, str] = field(default_factory=dict)
    
    @classmethod
    def from_element(cls, element: ET.Element) -> SVDField:
        """Parse field from SVD XML element."""
        name = element.findtext("name", "")
        description = element.findtext("description", "")
        
        # Parse bit range
        bit_range = element.find("bitRange") or element.find("bitOffset") or element.find("lsb")
        if bit_range is not None:
            text = bit_range.text or ""
            if ":" in text:
                parts = text.replace("[", "").replace("]", "").split(":")
                offset = int(parts[1])
                width = int(parts[0]) - offset + 1
            else:
                offset = int(text)
                width = 1
        else:
            # Alternative: lsb + msb
            lsb_elem = element.find("lsb")
            msb_elem = element.find("msb")
            if lsb_elem is not None and msb_elem is not None:
                offset = int(lsb_elem.text or 0)
                width = int(msb_elem.text or 0) - offset + 1
            else:
                offset = 0
                width = 1
        
        access = element.findtext("access", "read-write")
        
        # Parse enum values
        enum_values = {}
        enum_elem = element.find("enumeratedValues")
        if enum_elem is not None:
            for ev in enum_elem.findall("enumeratedValue"):
                value_text = ev.findtext("value")
                enum_name = ev.findtext("name", "")
                if value_text and enum_name:
                    try:
                        value = int(value_text, 0)
                        enum_values[value] = enum_name
                    except ValueError:
                        pass
        
        return cls(
            name=name,
            description=description,
            offset=offset,
            width=width,
            access=access,
            enum_values=enum_values,
        )


@dataclass
class SVDRegister:
    """Register definition from SVD."""
    
    name: str
    address_offset: int
    description: str
    size: int = 32
    access: str = "read-write"
    reset_value: int | None = None
    fields: list[SVDField] = field(default_factory=list)
    
    @property
    def address(self) -> int:
        """Get absolute address (requires peripheral base)."""
        return self.address_offset  # Set by peripheral
    
    @classmethod
    def from_element(cls, element: ET.Element) -> SVDRegister:
        """Parse register from SVD XML element."""
        name = element.findtext("name", "")
        description = element.findtext("description", "")
        
        address_offset_str = element.findtext("addressOffset", "0")
        address_offset = int(address_offset_str, 0)
        
        size_str = element.findtext("size", "32")
        size = int(size_str)
        
        access = element.findtext("access", "read-write")
        
        # Parse reset value
        reset_value = None
        reset_elem = element.find("resetValue")
        if reset_elem is not None:
            reset_value_str = reset_elem.findtext("value")
            if reset_value_str:
                reset_value = int(reset_value_str, 0)
        
        # Parse fields
        fields = []
        fields_elem = element.find("fields")
        if fields_elem is not None:
            for field_elem in fields_elem.findall("field"):
                try:
                    fields.append(SVDField.from_element(field_elem))
                except Exception as e:
                    logger.warning("svd_parse_field_error", 
                                register=name, 
                                error=str(e))
        
        return cls(
            name=name,
            address_offset=address_offset,
            description=description,
            size=size,
            access=access,
            reset_value=reset_value,
            fields=fields,
        )


@dataclass 
class SVDInterrupt:
    """Interrupt definition from SVD."""
    
    name: str
    value: int
    description: str = ""
    
    @classmethod
    def from_element(cls, element: ET.Element) -> SVDInterrupt:
        """Parse interrupt from SVD XML element."""
        name = element.findtext("name", "")
        value_str = element.findtext("value", "0")
        value = int(value_str, 0)
        description = element.findtext("description", "")
        
        return cls(name=name, value=value, description=description)


@dataclass
class SVDPeripheral:
    """Peripheral definition from SVD."""
    
    name: str
    base_address: int
    description: str
    group_name: str | None = None
    registers: list[SVDRegister] = field(default_factory=list)
    interrupts: list[SVDInterrupt] = field(default_factory=list)
    derived_from: str | None = None
    
    def get_register(self, name: str) -> SVDRegister | None:
        """Get register by name (case insensitive)."""
        for reg in self.registers:
            if reg.name.lower() == name.lower():
                return reg
        return None
    
    @classmethod
    def from_element(cls, element: ET.Element, device: dict | None = None) -> SVDPeripheral:
        """Parse peripheral from SVD XML element."""
        name = element.findtext("name", "")
        description = element.findtext("description", "")
        base_address_str = element.findtext("baseAddress", "0")
        base_address = int(base_address_str, 0)
        group_name = element.findtext("groupName")
        derived_from = element.findtext("derivedFrom")
        
        # Parse registers
        registers = []
        registers_elem = element.find("registers")
        if registers_elem is not None:
            for reg_elem in registers_elem.findall("register"):
                try:
                    registers.append(SVDRegister.from_element(reg_elem))
                except Exception as e:
                    logger.warning("svd_parse_register_error",
                                peripheral=name,
                                error=str(e))
        
        # Parse interrupts
        interrupts = []
        for intr_elem in element.findall("interrupt"):
            try:
                interrupts.append(SVDInterrupt.from_element(intr_elem))
            except Exception:
                pass
        
        return cls(
            name=name,
            base_address=base_address,
            description=description,
            group_name=group_name,
            registers=registers,
            interrupts=interrupts,
            derived_from=derived_from,
        )


@dataclass
class SVDDevice:
    """Complete SVD device definition."""
    
    vendor: str = ""
    vendor_id: str = ""
    name: str = ""
    series: str = ""
    version: str = ""
    description: str = ""
    address_unit_bits: int = 8
    width: int = 32
    peripherals: list[SVDPeripheral] = field(default_factory=list)
    
    def get_peripheral(self, name: str) -> SVDPeripheral | None:
        """Get peripheral by name (case insensitive)."""
        for peri in self.peripherals:
            if peri.name.lower() == name.lower():
                return peri
        return None
    
    def find_peripheral_by_address(self, address: int) -> SVDPeripheral | None:
        """Find peripheral containing address."""
        for peri in self.peripherals:
            if peri.base_address <= address < peri.base_address + 0x1000:
                return peri
        return None
    
    def get_all_registers(self) -> list[tuple[str, str, int, int]]:
        """Get all registers as (peripheral, name, address, size)."""
        result = []
        for peri in self.peripherals:
            for reg in peri.registers:
                result.append((peri.name, reg.name, peri.base_address + reg.address_offset, reg.size))
        return result
    
    @classmethod
    def from_file(cls, path: str | Path) -> SVDDevice:
        """Parse SVD file."""
        tree = ET.parse(path)
        root = tree.getroot()
        return cls.from_element(root)
    
    @classmethod
    def from_string(cls, xml_string: str) -> SVDDevice:
        """Parse SVD from string."""
        root = ET.fromstring(xml_string)
        return cls.from_element(root)
    
    @classmethod
    def from_element(cls, element: ET.Element) -> SVDDevice:
        """Parse device from SVD XML element."""
        device_elem = element.find("device") or element
        
        # Device info
        vendor = device_elem.findtext("vendor", "")
        vendor_id = device_elem.findtext("vendorID", "")
        name = device_elem.findtext("name", "")
        series = device_elem.findtext("series", "")
        version = device_elem.findtext("version", "")
        description = device_elem.findtext("description", "")
        
        # Parse properties
        props = device_elem.find("properties")
        address_unit_bits = 8
        width = 32
        if props is not None:
            address_unit_bits = int(props.findtext("addressUnitBits", "8"))
            width = int(props.findtext("width", "32"))
        
        # Parse peripherals
        peripherals = []
        peripherals_elem = device_elem.find("peripherals")
        if peripherals_elem is not None:
            for peri_elem in peripherals_elem.findall("peripheral"):
                try:
                    peri = SVDPeripheral.from_element(peri_elem)
                    peripherals.append(peri)
                except Exception as e:
                    logger.warning("svd_parse_peripheral_error",
                                error=str(e))
        
        return cls(
            vendor=vendor,
            vendor_id=vendor_id,
            name=name,
            series=series,
            version=version,
            description=description,
            address_unit_bits=address_unit_bits,
            width=width,
            peripherals=peripherals,
        )


class SVDParser:
    """CMSIS-SVD parser.
    
    Features:
    - Parse SVD XML files
    - Extract peripherals, registers, fields
    - Generate HAL-compatible data structures
    - Cache parsed results
    """
    
    def __init__(self):
        self._cache: dict[str, SVDDevice] = {}
    
    def parse_file(self, path: str | Path) -> SVDDevice:
        """Parse SVD file with caching.
        
        Args:
            path: Path to SVD file
            
        Returns:
            SVDDevice with parsed definitions
        """
        path_str = str(path)
        
        if path_str in self._cache:
            return self._cache[path_str]
        
        device = SVDDevice.from_file(path)
        self._cache[path_str] = device
        
        logger.info("svd_parsed", 
                   device=device.name,
                   peripherals=len(device.peripherals))
        
        return device
    
    def parse_string(self, xml_string: str) -> SVDDevice:
        """Parse SVD from string."""
        return SVDDevice.from_string(xml_string)
    
    def clear_cache(self) -> None:
        """Clear parsed file cache."""
        self._cache.clear()
    
    def to_hal_peripherals(self, device: SVDDevice) -> dict[str, Any]:
        """Convert SVD device to HAL query format.
        
        Args:
            device: Parsed SVD device
            
        Returns:
            Dictionary suitable for HALQueryTool
        """
        from src.domain.hardware.hal.hal_query import (
            PeripheralInfo,
            RegisterInfo,
            RegisterField,
            RegisterAccess,
        )
        
        peripherals = {}
        
        for svd_peri in device.peripherals:
            # Map SVD access to RegisterAccess enum
            access_map = {
                "read-only": RegisterAccess.READ_ONLY,
                "write-only": RegisterAccess.WRITE_ONLY,
                "read-write": RegisterAccess.READ_WRITE,
            }
            
            registers = []
            for svd_reg in svd_peri.registers:
                # Map access
                reg_access = access_map.get(svd_reg.access, RegisterAccess.READ_WRITE)
                
                # Convert fields
                fields = []
                for svd_field in svd_reg.fields:
                    field_access = access_map.get(svd_field.access, reg_access)
                    fields.append(RegisterField(
                        name=svd_field.name,
                        description=svd_field.description,
                        offset=svd_field.offset,
                        width=svd_field.width,
                        access=field_access,
                        reset_value=svd_field.reset_value,
                        enum_values=svd_field.enum_values,
                    ))
                
                registers.append(RegisterInfo(
                    name=svd_reg.name,
                    address=svd_peri.base_address + svd_reg.address_offset,
                    description=svd_reg.description,
                    size=svd_reg.size,
                    access=reg_access,
                    reset_value=svd_reg.reset_value or 0,
                    fields=fields,
                ))
            
            # Convert interrupts
            interrupts = [
                {"name": i.name, "value": i.value, "description": i.description}
                for i in svd_peri.interrupts
            ]
            
            peripherals[svd_peri.name] = {
                "base_address": svd_peri.base_address,
                "description": svd_peri.description,
                "registers": registers,
                "interrupts": interrupts,
            }
        
        return peripherals
    
    def generate_register_summary(self, device: SVDDevice) -> str:
        """Generate human-readable register summary."""
        lines = [
            f"Device: {device.name}",
            f"Vendor: {device.vendor}",
            f"Description: {device.description}",
            "",
            f"Peripherals: {len(device.peripherals)}",
            "",
        ]
        
        for peri in device.peripherals:
            lines.append(f"  {peri.name} @ 0x{peri.base_address:08X}")
            for reg in peri.registers:
                lines.append(f"    {reg.name:20} @ +0x{reg.address_offset:04X} [{reg.size}b]")
                if reg.fields:
                    for field in reg.fields:
                        lines.append(f"      [{field.offset}:{field.offset + field.width - 1}] {field.name}")
        
        return "\n".join(lines)
