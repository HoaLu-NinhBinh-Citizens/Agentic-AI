"""HAL Query Tool - Query peripheral information from hardware registers.

Phase 6.7: HAL Query Tool
- Query peripheral registers and fields
- Get register descriptions from SVD
- Display formatted register values
- Read/write registers with validation
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = __import__("structlog").get_logger(__name__)


class RegisterAccess(Enum):
    READ_ONLY = "read-only"
    WRITE_ONLY = "write-only"
    READ_WRITE = "read-write"
    READ_WRITE_1_CLEAR = "read-write-1-to-clear"
    READ_WRITE_0_CLEAR = "read-write-0-to-clear"


@dataclass
class RegisterField:
    """Single field within a register."""
    
    name: str
    description: str
    offset: int  # Bit offset
    width: int  # Number of bits
    access: RegisterAccess
    reset_value: int = 0
    enum_values: dict[int, str] = field(default_factory=dict)
    
    @property
    def bitmask(self) -> int:
        """Get bitmask for this field."""
        return ((1 << self.width) - 1) << self.offset
    
    def extract_value(self, register_value: int) -> int:
        """Extract field value from register value."""
        return (register_value >> self.offset) & ((1 << self.width) - 1)
    
    def format_value(self, value: int) -> str:
        """Format field value, possibly as enum."""
        if value in self.enum_values:
            return f"{self.enum_values[value]} ({value})"
        return f"0x{value:0{self.width // 4 + 1}x} ({value})"


@dataclass
class RegisterInfo:
    """Information about a hardware register."""
    
    name: str
    address: int
    description: str
    size: int = 32  # bits
    access: RegisterAccess = RegisterAccess.READ_WRITE
    reset_value: int = 0
    fields: list[RegisterField] = field(default_factory=list)
    
    def get_field(self, name: str) -> RegisterField | None:
        """Get field by name."""
        for field in self.fields:
            if field.name.lower() == name.lower():
                return field
        return None
    
    def parse_value(self, value: int) -> dict[str, Any]:
        """Parse register value into field values."""
        result = {
            "_raw": value,
            "_raw_hex": f"0x{value:08X}",
        }
        for field in self.fields:
            field_value = field.extract_value(value)
            result[field.name] = field_value
            result[f"{field.name}_formatted"] = field.format_value(field_value)
        return result
    
    def format_value(self, value: int) -> str:
        """Format register value as readable string."""
        lines = [f"{self.name} @ 0x{self.address:08X} = 0x{value:08X}"]
        
        if self.fields:
            lines.append("Fields:")
            for field in self.fields:
                field_value = field.extract_value(value)
                formatted = field.format_value(field_value)
                lines.append(f"  [{field.offset}:{field.offset + field.width - 1}] {field.name} = {formatted}")
        else:
            lines.append(f"  Raw value: {value}")
        
        return "\n".join(lines)


@dataclass
class PeripheralInfo:
    """Information about a hardware peripheral."""
    
    name: str
    base_address: int
    description: str
    size: int = 0x1000
    registers: list[RegisterInfo] = field(default_factory=list)
    interrupts: list[dict] = field(default_factory=list)
    
    def get_register(self, name: str) -> RegisterInfo | None:
        """Get register by name."""
        for reg in self.registers:
            if reg.name.lower() == name.lower():
                return reg
        return None
    
    def get_register_at_offset(self, offset: int) -> RegisterInfo | None:
        """Get register by address offset."""
        for reg in self.registers:
            if reg.address == self.base_address + offset:
                return reg
        return None
    
    def list_registers(self) -> list[tuple[str, int]]:
        """List all registers as (name, offset) pairs."""
        return [(r.name, r.address - self.base_address) for r in self.registers]


@dataclass
class HALQueryResult:
    """Result of a HAL query."""
    
    success: bool
    peripheral: str | None = None
    register: str | None = None
    value: int | None = None
    formatted: str | None = None
    parsed_fields: dict[str, Any] | None = None
    error: str | None = None
    timestamp: float = field(default_factory=lambda: __import__("time").time())


class HALQueryTool:
    """Tool for querying hardware registers via HAL/registers.
    
    Features:
    - Query register values
    - Parse register fields from SVD
    - Format output for readability
    - Read/write with validation
    """
    
    def __init__(
        self,
        probe: Any = None,  # HardwareProbeInterface
        svd_parser: Any = None,  # SVD parser if available
    ):
        self._probe = probe
        self._svd_parser = svd_parser
        self._peripherals: dict[str, PeripheralInfo] = {}
        self._register_cache: dict[int, RegisterInfo] = {}
    
    def register_peripheral(self, peripheral: PeripheralInfo) -> None:
        """Register a peripheral for querying."""
        self._peripherals[peripheral.name] = peripheral
        for reg in peripheral.registers:
            self._register_cache[reg.address] = reg
    
    def register_peripherals_from_svd(self, svd_path: str) -> None:
        """Load peripherals from SVD file."""
        if self._svd_parser:
            peripherals = self._svd_parser.parse_file(svd_path)
            for peripheral in peripherals:
                self.register_peripheral(peripheral)
    
    async def read_register(self, peripheral: str, register: str) -> HALQueryResult:
        """Read a register value.
        
        Args:
            peripheral: Peripheral name (e.g., "USART1", "GPIOA")
            register: Register name (e.g., "SR", "CR1")
            
        Returns:
            HALQueryResult with value and formatted output
        """
        if not self._probe:
            return HALQueryResult(
                success=False,
                peripheral=peripheral,
                register=register,
                error="No probe connected",
            )
        
        try:
            # Find peripheral info
            peri_info = self._peripherals.get(peripheral)
            if not peri_info:
                return HALQueryResult(
                    success=False,
                    peripheral=peripheral,
                    register=register,
                    error=f"Unknown peripheral: {peripheral}",
                )
            
            # Find register info
            reg_info = peri_info.get_register(register)
            if not reg_info:
                return HALQueryResult(
                    success=False,
                    peripheral=peripheral,
                    register=register,
                    error=f"Unknown register: {register}",
                )
            
            # Read from hardware
            value = await self._probe.read_memory(reg_info.address, 4)
            if len(value) == 4:
                value = struct.unpack("<I", value)[0]
            else:
                return HALQueryResult(
                    success=False,
                    peripheral=peripheral,
                    register=register,
                    error=f"Invalid read size: {len(value)}",
                )
            
            # Format output
            formatted = reg_info.format_value(value)
            parsed = reg_info.parse_value(value)
            
            return HALQueryResult(
                success=True,
                peripheral=peripheral,
                register=register,
                value=value,
                formatted=formatted,
                parsed_fields=parsed,
            )
            
        except Exception as e:
            logger.error("hal_read_error", 
                       peripheral=peripheral, 
                       register=register, 
                       error=str(e))
            return HALQueryResult(
                success=False,
                peripheral=peripheral,
                register=register,
                error=str(e),
            )
    
    async def write_register(
        self, 
        peripheral: str, 
        register: str, 
        value: int,
        mask: int | None = None,
    ) -> HALQueryResult:
        """Write a register value.
        
        Args:
            peripheral: Peripheral name
            register: Register name
            value: Value to write
            mask: Optional bitmask for partial write
            
        Returns:
            HALQueryResult with write status
        """
        if not self._probe:
            return HALQueryResult(
                success=False,
                peripheral=peripheral,
                register=register,
                error="No probe connected",
            )
        
        try:
            peri_info = self._peripherals.get(peripheral)
            if not peri_info:
                return HALQueryResult(
                    success=False,
                    peripheral=peripheral,
                    register=register,
                    error=f"Unknown peripheral: {peripheral}",
                )
            
            reg_info = peri_info.get_register(register)
            if not reg_info:
                return HALQueryResult(
                    success=False,
                    peripheral=peripheral,
                    register=register,
                    error=f"Unknown register: {register}",
                )
            
            # Check write access
            if reg_info.access == RegisterAccess.READ_ONLY:
                return HALQueryResult(
                    success=False,
                    peripheral=peripheral,
                    register=register,
                    error="Register is read-only",
                )
            
            # Apply mask if provided
            if mask is not None:
                # Read-modify-write
                current = await self._probe.read_memory(reg_info.address, 4)
                current_value = struct.unpack("<I", current)[0]
                value = (current_value & ~mask) | (value & mask)
            
            # Write to hardware
            data = struct.pack("<I", value)
            success = await self._probe.write_memory(reg_info.address, data)
            
            return HALQueryResult(
                success=success,
                peripheral=peripheral,
                register=register,
                value=value,
                formatted=f"Wrote 0x{value:08X} to {peripheral}.{register}",
            )
            
        except Exception as e:
            logger.error("hal_write_error", 
                       peripheral=peripheral, 
                       register=register, 
                       error=str(e))
            return HALQueryResult(
                success=False,
                peripheral=peripheral,
                register=register,
                error=str(e),
            )
    
    async def read_peripheral(self, peripheral: str) -> dict[str, Any]:
        """Read all registers of a peripheral.
        
        Args:
            peripheral: Peripheral name
            
        Returns:
            Dictionary of register values
        """
        if not self._probe:
            return {"error": "No probe connected"}
        
        peri_info = self._peripherals.get(peripheral)
        if not peri_info:
            return {"error": f"Unknown peripheral: {peripheral}"}
        
        results = {}
        for reg in peri_info.registers:
            try:
                data = await self._probe.read_memory(reg.address, 4)
                if len(data) == 4:
                    value = struct.unpack("<I", data)[0]
                    results[reg.name] = {
                        "address": f"0x{reg.address:08X}",
                        "value": value,
                        "value_hex": f"0x{value:08X}",
                        "description": reg.description,
                    }
            except Exception as e:
                results[reg.name] = {"error": str(e)}
        
        return results
    
    def get_peripheral_info(self, peripheral: str) -> PeripheralInfo | None:
        """Get peripheral information."""
        return self._peripherals.get(peripheral)
    
    def list_peripherals(self) -> list[str]:
        """List all registered peripherals."""
        return list(self._peripherals.keys())
    
    def describe_register(self, peripheral: str, register: str) -> str | None:
        """Get human-readable description of a register."""
        peri_info = self._peripherals.get(peripheral)
        if not peri_info:
            return None
        
        reg_info = peri_info.get_register(register)
        if not reg_info:
            return None
        
        lines = [
            f"Register: {peripheral}.{register}",
            f"Address: 0x{reg_info.address:08X}",
            f"Description: {reg_info.description}",
            f"Access: {reg_info.access.value}",
            f"Reset Value: 0x{reg_info.reset_value:08X}",
            "",
            "Fields:",
        ]
        
        for field in reg_info.fields:
            enum_str = ""
            if field.enum_values:
                enum_str = " | ".join(
                    f"{name}={val}" for val, name in field.enum_values.items()
                )
                enum_str = f" ({enum_str})"
            
            lines.append(
                f"  [{field.offset}:{field.offset + field.width - 1}] "
                f"{field.name} ({field.width} bits){enum_str}"
            )
        
        return "\n".join(lines)
    
    def find_peripheral_by_address(self, address: int) -> PeripheralInfo | None:
        """Find peripheral containing address."""
        for peri in self._peripherals.values():
            if peri.base_address <= address < peri.base_address + peri.size:
                return peri
        return None
    
    def find_register_by_address(self, address: int) -> RegisterInfo | None:
        """Find register at exact address."""
        return self._register_cache.get(address)


# =============================================================================
# Common STM32 HAL Queries
# =============================================================================

def create_stm32_usart_hal_queries() -> dict[str, PeripheralInfo]:
    """Create common STM32 USART peripheral definitions."""
    
    # USART Status Register
    sr_fields = [
        RegisterField("PE", "Parity Error", 0, 1, RegisterAccess.READ_ONLY),
        RegisterField("FE", "Framing Error", 1, 1, RegisterAccess.READ_ONLY),
        RegisterField("NF", "Noise Flag", 2, 1, RegisterAccess.READ_ONLY),
        RegisterField("ORE", "Overrun Error", 3, 1, RegisterAccess.READ_ONLY),
        RegisterField("IDLE", "IDLE Line Detected", 4, 1, RegisterAccess.READ_ONLY),
        RegisterField("RXNE", "Read Data Register Not Empty", 5, 1, RegisterAccess.READ_ONLY),
        RegisterField("TC", "Transmission Complete", 6, 1, RegisterAccess.READ_ONLY),
        RegisterField("TXE", "Transmit Data Register Empty", 7, 1, RegisterAccess.READ_ONLY),
        RegisterField("LBD", "LIN Break Detection Flag", 8, 1, RegisterAccess.READ_ONLY),
        RegisterField("CTS", "CTS Flag", 9, 1, RegisterAccess.READ_ONLY),
    ]
    
    # USART Control Register 1
    cr1_fields = [
        RegisterField("SBK", "Send Break", 0, 1, RegisterAccess.READ_WRITE),
        RegisterField("RWU", "Receiver Wakeup", 1, 1, RegisterAccess.READ_WRITE),
        RegisterField("RE", "Receiver Enable", 2, 1, RegisterAccess.READ_WRITE),
        RegisterField("TE", "Transmitter Enable", 3, 1, RegisterAccess.READ_WRITE),
        RegisterField("IDLEIE", "IDLE Interrupt Enable", 4, 1, RegisterAccess.READ_WRITE),
        RegisterField("RXNEIE", "RXNE Interrupt Enable", 5, 1, RegisterAccess.READ_WRITE),
        RegisterField("TCIE", "Transmission Complete Interrupt Enable", 6, 1, RegisterAccess.READ_WRITE),
        RegisterField("TXEIE", "TXE Interrupt Enable", 7, 1, RegisterAccess.READ_WRITE),
        RegisterField("PEIE", "PE Interrupt Enable", 8, 1, RegisterAccess.READ_WRITE),
        RegisterField("PS", "Parity Selection", 9, 1, RegisterAccess.READ_WRITE),
        RegisterField("PCE", "Parity Control Enable", 10, 1, RegisterAccess.READ_WRITE),
        RegisterField("WAKE", "Wakeup Method", 11, 1, RegisterAccess.READ_WRITE),
        RegisterField("M", "Word Length", 12, 1, RegisterAccess.READ_WRITE),
        RegisterField("UE", "USART Enable", 13, 1, RegisterAccess.READ_WRITE),
    ]
    
    usart1 = PeripheralInfo(
        name="USART1",
        base_address=0x40011000,
        description="Universal Synchronous/Asynchronous Receiver Transmitter",
        size=0x400,
        registers=[
            RegisterInfo(
                name="SR",
                address=0x40011000,
                description="Status Register",
                fields=sr_fields,
            ),
            RegisterInfo(
                name="DR",
                address=0x40011004,
                description="Data Register",
                access=RegisterAccess.READ_WRITE,
            ),
            RegisterInfo(
                name="BRR",
                address=0x40011008,
                description="Baud Rate Register",
            ),
            RegisterInfo(
                name="CR1",
                address=0x4001100C,
                description="Control Register 1",
                fields=cr1_fields,
            ),
        ],
    )
    
    return {"USART1": usart1}
