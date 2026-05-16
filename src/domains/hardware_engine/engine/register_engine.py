"""Register Engine - peripheral register initialization sequences."""

from typing import Dict, List, Optional

from src.domains.hardware_engine.core.register_schema import RegisterSchemaDB
from src.domains.hardware_engine.core.models import (
    RegisterWrite,
    ValidationResult,
    ValidationSeverity,
)


class RegisterEngine:
    """
    Register access and initialization engine.

    Responsibilities:
    1. Build deterministic initialization sequences
    2. Validate register access patterns
    3. Generate register write sequences
    4. Extract bitfield manipulation
    """

    def __init__(self, register_schema: RegisterSchemaDB):
        self.register_schema = register_schema

    def build_sequence(
        self, peripheral: str, operation: str
    ) -> List[RegisterWrite]:
        """
        Build deterministic register initialization sequence.

        Args:
            peripheral: Peripheral name (e.g., "USART2")
            operation: "init", "deinit", "enable", "disable"

        Returns:
            List of RegisterWrite operations
        """
        if operation == "init":
            return self._build_init_sequence(peripheral)
        elif operation == "deinit":
            return self._build_deinit_sequence(peripheral)
        elif operation == "enable":
            return self._build_enable_sequence(peripheral)
        elif operation == "disable":
            return self._build_disable_sequence(peripheral)
        return []

    def _build_init_sequence(self, peripheral: str) -> List[RegisterWrite]:
        """Build peripheral initialization sequence."""
        ops = []
        ptype = peripheral.upper()

        if "USART" in ptype or "UART" in ptype:
            ops.extend(self._usart_init(peripheral))
        elif "SPI" in ptype:
            ops.extend(self._spi_init(peripheral))
        elif "I2C" in ptype:
            ops.extend(self._i2c_init(peripheral))
        elif "CAN" in ptype:
            ops.extend(self._can_init(peripheral))
        elif "ADC" in ptype:
            ops.extend(self._adc_init(peripheral))
        elif "TIM" in ptype:
            ops.extend(self._tim_init(peripheral))
        elif "GPIO" in ptype:
            ops.extend(self._gpio_init(peripheral))

        return ops

    def _usart_init(self, peripheral: str) -> List[RegisterWrite]:
        ops = [
            RegisterWrite(
                peripheral=peripheral,
                register="SR",
                field_name="",
                value=0,
                operation="write",
                description="Clear status register",
            ),
            RegisterWrite(
                peripheral=peripheral,
                register="CR1",
                field_name="UE",
                value=0,
                operation="clear_bit",
                description="Disable USART during configuration",
            ),
            RegisterWrite(
                peripheral=peripheral,
                register="CR1",
                field_name="TE",
                value=1,
                operation="set_bit",
                description="Enable transmitter",
            ),
            RegisterWrite(
                peripheral=peripheral,
                register="CR1",
                field_name="RE",
                value=1,
                operation="set_bit",
                description="Enable receiver",
            ),
            RegisterWrite(
                peripheral=peripheral,
                register="CR1",
                field_name="UE",
                value=1,
                operation="set_bit",
                description="Enable USART",
            ),
        ]
        return ops

    def _spi_init(self, peripheral: str) -> List[RegisterWrite]:
        ops = [
            RegisterWrite(
                peripheral=peripheral,
                register="CR1",
                field_name="SPE",
                value=0,
                operation="clear_bit",
                description="Disable SPI during configuration",
            ),
            RegisterWrite(
                peripheral=peripheral,
                register="CR1",
                field_name="MSTR",
                value=1,
                operation="set_bit",
                description="Master mode",
            ),
            RegisterWrite(
                peripheral=peripheral,
                register="CR1",
                field_name="BR",
                value=0,
                operation="write_bits",
                description="Baud rate = f_PCLK / 2",
            ),
            RegisterWrite(
                peripheral=peripheral,
                register="CR2",
                field_name="SSM",
                value=1,
                operation="set_bit",
                description="Software slave management",
            ),
            RegisterWrite(
                peripheral=peripheral,
                register="CR1",
                field_name="SPE",
                value=1,
                operation="set_bit",
                description="Enable SPI",
            ),
        ]
        return ops

    def _i2c_init(self, peripheral: str) -> List[RegisterWrite]:
        ops = [
            RegisterWrite(
                peripheral=peripheral,
                register="CR1",
                field_name="PE",
                value=0,
                operation="clear_bit",
                description="Disable I2C during configuration",
            ),
            RegisterWrite(
                peripheral=peripheral,
                register="CR1",
                field_name="SWRST",
                value=1,
                operation="set_bit",
                description="Reset I2C peripheral",
            ),
            RegisterWrite(
                peripheral=peripheral,
                register="CR1",
                field_name="SWRST",
                value=0,
                operation="clear_bit",
                description="Clear reset",
            ),
            RegisterWrite(
                peripheral=peripheral,
                register="CR1",
                field_name="PE",
                value=1,
                operation="set_bit",
                description="Enable I2C",
            ),
        ]
        return ops

    def _can_init(self, peripheral: str) -> List[RegisterWrite]:
        ops = [
            RegisterWrite(
                peripheral=peripheral,
                register="MCR",
                field_name="INRQ",
                value=1,
                operation="set_bit",
                description="Enter initialization mode",
            ),
            RegisterWrite(
                peripheral=peripheral,
                register="MCR",
                field_name="DFF",
                value=0,
                operation="clear_bit",
                description="11-bit standard identifier",
            ),
            RegisterWrite(
                peripheral=peripheral,
                register="MCR",
                field_name="TTCM",
                value=0,
                operation="clear_bit",
                description="Time triggered mode disabled",
            ),
            RegisterWrite(
                peripheral=peripheral,
                register="MCR",
                field_name="ABOM",
                value=0,
                operation="clear_bit",
                description="Automatic bus-off management disabled",
            ),
            RegisterWrite(
                peripheral=peripheral,
                register="MCR",
                field_name="NART",
                value=0,
                operation="clear_bit",
                description="Automatic retransmission enabled",
            ),
            RegisterWrite(
                peripheral=peripheral,
                register="MCR",
                field_name="RFLM",
                value=0,
                operation="clear_bit",
                description="FIFO locked mode disabled",
            ),
            RegisterWrite(
                peripheral=peripheral,
                register="MCR",
                field_name="TXFP",
                value=0,
                operation="clear_bit",
                description="Priority by message identifier",
            ),
            RegisterWrite(
                peripheral=peripheral,
                register="MCR",
                field_name="INRQ",
                value=0,
                operation="clear_bit",
                description="Exit initialization mode, enter normal mode",
            ),
        ]
        return ops

    def _adc_init(self, peripheral: str) -> List[RegisterWrite]:
        ops = [
            RegisterWrite(
                peripheral=peripheral,
                register="SR",
                field_name="",
                value=0,
                operation="write",
                description="Clear status flags before configuration",
            ),
            RegisterWrite(
                peripheral=peripheral,
                register="CR2",
                field_name="ADON",
                value=0,
                operation="clear_bit",
                description="Disable ADC during configuration",
            ),
            RegisterWrite(
                peripheral=peripheral,
                register="SMPR",
                field_name="SMP",
                value=3,  # 15 cycles sampling time (adjust as needed)
                operation="write_bits",
                description="Set sampling time for all channels (SMPR default 3 = 15 cycles)",
            ),
            RegisterWrite(
                peripheral=peripheral,
                register="CR1",
                field_name="SCAN",
                value=1,
                operation="set_bit",
                description="Enable scan mode for multi-channel conversion",
            ),
            RegisterWrite(
                peripheral=peripheral,
                register="CR2",
                field_name="DMA",
                value=1,
                operation="set_bit",
                description="Enable DMA mode for continuous conversion",
            ),
            RegisterWrite(
                peripheral=peripheral,
                register="CR2",
                field_name="DDS",
                value=1,
                operation="set_bit",
                description="Enable DMA circular mode (continuous conversion)",
            ),
            RegisterWrite(
                peripheral=peripheral,
                register="CR2",
                field_name="ADON",
                value=1,
                operation="set_bit",
                description="Enable ADC",
            ),
        ]
        return ops

    def _tim_init(self, peripheral: str) -> List[RegisterWrite]:
        ops = [
            RegisterWrite(
                peripheral=peripheral,
                register="CR1",
                field_name="CEN",
                value=0,
                operation="clear_bit",
                description="Disable timer during configuration",
            ),
            RegisterWrite(
                peripheral=peripheral,
                register="PSC",
                field_name="PSC",
                value=0,
                operation="write",
                description="Prescaler = 1",
            ),
            RegisterWrite(
                peripheral=peripheral,
                register="ARR",
                field_name="ARR",
                value=0xFFFF,
                operation="write",
                description="Auto-reload = max",
            ),
            RegisterWrite(
                peripheral=peripheral,
                register="EGR",
                field_name="UG",
                value=1,
                operation="set_bit",
                description="Generate update event",
            ),
        ]
        return ops

    def _gpio_init(self, peripheral: str) -> List[RegisterWrite]:
        """Build GPIO initialization sequence.

        Configures the four key GPIO registers:
        - MODER: pin mode (input/output/analog/alternate)
        - OTYPER: output type (push-pull/open-drain)
        - OSPEEDR: output speed (low/medium/fast/high)
        - PUPDR: pull-up/pull-down resistor
        """
        ops = [
            RegisterWrite(
                peripheral=peripheral,
                register="MODER",
                field_name="MODE",
                value=0x55555555,
                operation="write_bits",
                description="Set all pins to output mode (default, caller should override per-pin)",
            ),
            RegisterWrite(
                peripheral=peripheral,
                register="OTYPER",
                field_name="OT",
                value=0,
                operation="write_bits",
                description="Push-pull output type for all pins",
            ),
            RegisterWrite(
                peripheral=peripheral,
                register="OSPEEDR",
                field_name="OSPEED",
                value=0xFFFFFFFF,
                operation="write_bits",
                description="High speed for all pins (2-bit per pin, 0x3 = high)",
            ),
            RegisterWrite(
                peripheral=peripheral,
                register="PUPDR",
                field_name="PUPD",
                value=0,
                operation="write_bits",
                description="No pull-up/pull-down (floating)",
            ),
        ]
        return ops

    def _build_deinit_sequence(self, peripheral: str) -> List[RegisterWrite]:
        return [
            RegisterWrite(
                peripheral=peripheral,
                register="CR1",
                field_name="UE",
                value=0,
                operation="clear_bit",
                description=f"Disable {peripheral}",
            ),
        ]

    def _build_enable_sequence(self, peripheral: str) -> List[RegisterWrite]:
        return [
            RegisterWrite(
                peripheral=peripheral,
                register="CR1",
                field_name="UE",
                value=1,
                operation="set_bit",
                description=f"Enable {peripheral}",
            ),
        ]

    def _build_disable_sequence(self, peripheral: str) -> List[RegisterWrite]:
        return [
            RegisterWrite(
                peripheral=peripheral,
                register="CR1",
                field_name="UE",
                value=0,
                operation="clear_bit",
                description=f"Disable {peripheral}",
            ),
        ]

    def validate_access(
        self, peripheral: str, register: str, operation: str
    ) -> ValidationResult:
        """Validate register access (read/write)."""
        result = ValidationResult(valid=True)
        access = self.register_schema.get_access(peripheral, register)

        if access == "RO" and operation == "write":
            result.add_error(
                "REG_001",
                f"Register {peripheral}->{register} is read-only",
                location=f"{peripheral}->{register}",
                peripheral=peripheral,
            )
        elif access == "WO" and operation == "read":
            result.add_warning(
                "REG_002",
                f"Register {peripheral}->{register} is write-only",
                location=f"{peripheral}->{register}",
                peripheral=peripheral,
            )

        return result

    def to_c_sequence(self, ops: List[RegisterWrite]) -> List[str]:
        """Convert RegisterWrite operations to C code."""
        lines = []
        for op in ops:
            p = op.peripheral
            r = op.register
            if op.operation == "write":
                lines.append(f"    {p}->{r} = 0x{op.value:08X}; /* {op.description} */")
            elif op.operation == "set_bit":
                lines.append(f"    {p}->{r} |= {r}_{op.field_name}; /* {op.description} */")
            elif op.operation == "clear_bit":
                lines.append(f"    {p}->{r} &= ~{r}_{op.field_name}; /* {op.description} */")
            elif op.operation == "write_bits":
                lines.append(f"    {p}->{r} = {op.value}; /* {op.description} */")
            else:
                lines.append(f"    /* {op.description}: {p}->{r} op={op.operation} */")
        return lines
