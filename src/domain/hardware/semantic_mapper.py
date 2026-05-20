"""Semantic Hardware Layer - normalizing peripherals across vendors.

Phase 6.1: Maps vendor-specific peripheral names (USART1, UART0, SERCOM2)
to semantic categories (SerialPeripheral) for vendor-agnostic reasoning.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# ============================================================================
# Semantic Categories
# ============================================================================


class SemanticCategory(Enum):
    """Semantic categories for hardware peripherals.

    These categories normalize peripheral names across vendors.
    """

    # Communication
    SERIAL_PERIPHERAL = "SerialPeripheral"
    SPI_PERIPHERAL = "SPIPeripheral"
    I2C_PERIPHERAL = "I2CPeripheral"
    CAN_PERIPHERAL = "CANPeripheral"
    ETHERNET_PERIPHERAL = "EthernetPeripheral"
    USB_PERIPHERAL = "USBPeripheral"

    # Timers
    TIMER_PERIPHERAL = "TimerPeripheral"
    PWM_PERIPHERAL = "PWMPeripheral"
    RTC_PERIPHERAL = "RTCPeripheral"

    # Analog
    ADC_PERIPHERAL = "ADCPeripheral"
    DAC_PERIPHERAL = "DACPeripheral"
    COMPARATOR_PERIPHERAL = "ComparatorPeripheral"

    # GPIO
    GPIO_PORT = "GPIOPort"
    GPIO_PIN = "GPIOPin"

    # Memory
    FLASH_CONTROLLER = "FlashController"
    DMA_CONTROLLER = "DMAController"
    EXTERNAL_MEMORY = "ExternalMemory"

    # Security
    CRYPTO_PERIPHERAL = "CryptoPeripheral"
    RNG_PERIPHERAL = "RNGPeripheral"

    # Debug
    DEBUG_PERIPHERAL = "DebugPeripheral"
    TRACE_PERIPHERAL = "TracePeripheral"

    # Power
    POWER_CONTROLLER = "PowerController"
    VOLTAGE_REGULATOR = "VoltageRegulator"

    # Audio
    I2S_PERIPHERAL = "I2SPeripheral"

    # Radio
    RADIO_PERIPHERAL = "RadioPeripheral"
    WIFI_PERIPHERAL = "WiFiPeripheral"
    BLUETOOTH_PERIPHERAL = "BluetoothPeripheral"

    # Computing
    COMPUTE_PERIPHERAL = "ComputePeripheral"


class FunctionalRole(Enum):
    """Functional role of a peripheral pin or signal."""

    # Serial
    TX = "TX"  # Transmit
    RX = "RX"  # Receive
    RTS = "RTS"  # Request to Send
    CTS = "CTS"  # Clear to Send

    # SPI
    MOSI = "MOSI"  # Master Out Slave In
    MISO = "MISO"  # Master In Slave Out
    SCK = "SCK"  # Serial Clock
    SS = "SS"  # Slave Select

    # I2C
    SDA = "SDA"  # Serial Data
    SCL = "SCL"  # Serial Clock

    # GPIO
    INPUT = "INPUT"
    OUTPUT = "OUTPUT"
    ALTERNATE = "ALTERNATE"
    ANALOG = "ANALOG"

    # Timer
    PWM = "PWM"
    CAPTURE = "CAPTURE"
    COMPARE = "COMPARE"

    # Clock
    CLOCK_INPUT = "CLOCK_INPUT"
    CLOCK_OUTPUT = "CLOCK_OUTPUT"

    # Power
    ENABLE = "ENABLE"
    SENSE = "SENSE"

    # Debug
    SWDIO = "SWDIO"
    SWCLK = "SWCLK"
    SWO = "SWO"
    TRACECK = "TRACECK"
    TRACED0 = "TRACED0"


# ============================================================================
# Peripheral Mapping
# ============================================================================


@dataclass
class PeripheralAlias:
    """Alias mapping for a peripheral."""

    vendor_name: str
    semantic_name: str
    category: SemanticCategory
    instance: int
    base_address: int = 0

    def __post_init__(self) -> None:
        """Validate mapping."""
        if not self.vendor_name:
            raise ValueError("vendor_name is required")
        if not self.semantic_name:
            raise ValueError("semantic_name is required")


# ============================================================================
# Semantic Hardware Layer
# ============================================================================


class SemanticHardwareMapper:
    """Maps vendor-specific peripherals to semantic categories.

    This enables vendor-agnostic reasoning about hardware.

    Example:
        mapper = SemanticHardwareMapper()
        mapper.add_alias("USART1", "Serial0", SemanticCategory.SERIAL_PERIPHERAL, 0)

        # Query
        serial_peripherals = mapper.get_by_category(SemanticCategory.SERIAL_PERIPHERAL)
        # Returns: [PeripheralAlias(vendor_name="USART1", ...), ...]
    """

    def __init__(self) -> None:
        """Initialize mapper."""
        self._aliases: dict[str, PeripheralAlias] = {}
        self._by_category: dict[SemanticCategory, list[PeripheralAlias]] = {}
        self._by_semantic_name: dict[str, PeripheralAlias] = {}
        self._vendor_prefix_map: dict[str, SemanticCategory] = {}

        # Load default mappings
        self._load_default_mappings()

    def _load_default_mappings(self) -> None:
        """Load default peripheral mappings."""
        # STM32 mappings
        self._add_default_mapping("USART", "Serial", SemanticCategory.SERIAL_PERIPHERAL)
        self._add_default_mapping("UART", "Serial", SemanticCategory.SERIAL_PERIPHERAL)
        self._add_default_mapping("LPUART", "Serial", SemanticCategory.SERIAL_PERIPHERAL)
        self._add_default_mapping("SPI", "Spi", SemanticCategory.SPI_PERIPHERAL)
        self._add_default_mapping("I2C", "I2C", SemanticCategory.I2C_PERIPHERAL)
        self._add_default_mapping("CAN", "Can", SemanticCategory.CAN_PERIPHERAL)
        self._add_default_mapping("ETH", "Eth", SemanticCategory.ETHERNET_PERIPHERAL)
        self._add_default_mapping("USB", "Usb", SemanticCategory.USB_PERIPHERAL)
        self._add_default_mapping("TIM", "Timer", SemanticCategory.TIMER_PERIPHERAL)
        self._add_default_mapping("LPTIM", "Timer", SemanticCategory.TIMER_PERIPHERAL)
        self._add_default_mapping("RTC", "Rtc", SemanticCategory.RTC_PERIPHERAL)
        self._add_default_mapping("ADC", "Adc", SemanticCategory.ADC_PERIPHERAL)
        self._add_default_mapping("DAC", "Dac", SemanticCategory.DAC_PERIPHERAL)
        self._add_default_mapping("COMP", "Comp", SemanticCategory.COMPARATOR_PERIPHERAL)
        self._add_default_mapping("GPIO", "Gpio", SemanticCategory.GPIO_PORT)
        self._add_default_mapping("DMA", "Dma", SemanticCategory.DMA_CONTROLLER)
        self._add_default_mapping("FLASH", "Flash", SemanticCategory.FLASH_CONTROLLER)
        self._add_default_mapping("RNG", "Rng", SemanticCategory.RNG_PERIPHERAL)
        self._add_default_mapping("CRYP", "Crypto", SemanticCategory.CRYPTO_PERIPHERAL)

        # Espressif mappings
        self._add_default_mapping("UART", "Serial", SemanticCategory.SERIAL_PERIPHERAL)
        self._add_default_mapping("SPI", "Spi", SemanticCategory.SPI_PERIPHERAL)
        self._add_default_mapping("I2C", "I2C", SemanticCategory.I2C_PERIPHERAL)
        self._add_default_mapping("LEDC", "Pwm", SemanticCategory.PWM_PERIPHERAL)
        self._add_default_mapping("GPIO", "Gpio", SemanticCategory.GPIO_PORT)
        self._add_default_mapping("DMA", "Dma", SemanticCategory.DMA_CONTROLLER)

        # NXP mappings
        self._add_default_mapping("LPUART", "Serial", SemanticCategory.SERIAL_PERIPHERAL)
        self._add_default_mapping("SPI", "Spi", SemanticCategory.SPI_PERIPHERAL)
        self._add_default_mapping("I2C", "I2C", SemanticCategory.I2C_PERIPHERAL)
        self._add_default_mapping("FlexCAN", "Can", SemanticCategory.CAN_PERIPHERAL)
        self._add_default_mapping("USB", "Usb", SemanticCategory.USB_PERIPHERAL)
        self._add_default_mapping("GPIO", "Gpio", SemanticCategory.GPIO_PORT)

        # RISC-V (SiFive) mappings
        self._add_default_mapping("UART", "Serial", SemanticCategory.SERIAL_PERIPHERAL)
        self._add_default_mapping("SPI", "Spi", SemanticCategory.SPI_PERIPHERAL)
        self._add_default_mapping("I2C", "I2C", SemanticCategory.I2C_PERIPHERAL)

        # SERCOM (Microchip/Atmel) mappings
        self._add_default_mapping("SERCOM", "Serial", SemanticCategory.SERIAL_PERIPHERAL)

        # LPC (NXP) mappings
        self._add_default_mapping("USART", "Serial", SemanticCategory.SERIAL_PERIPHERAL)

        # MSP430 (TI) mappings
        self._add_default_mapping("USCI", "Serial", SemanticCategory.SERIAL_PERIPHERAL)
        self._add_default_mapping("eUSCI", "Serial", SemanticCategory.SERIAL_PERIPHERAL)

    def _add_default_mapping(
        self,
        prefix: str,
        semantic_prefix: str,
        category: SemanticCategory,
    ) -> None:
        """Add default mapping for peripheral prefix."""
        self._vendor_prefix_map[prefix.upper()] = (semantic_prefix, category)

    def add_alias(
        self,
        vendor_name: str,
        semantic_name: str,
        category: SemanticCategory,
        instance: int = 0,
        base_address: int = 0,
    ) -> PeripheralAlias:
        """Add a peripheral alias mapping.

        Args:
            vendor_name: Vendor-specific name (e.g., "USART1", "SERCOM2")
            semantic_name: Semantic name (e.g., "Serial0")
            category: Semantic category
            instance: Instance number
            base_address: Hardware base address

        Returns:
            Created PeripheralAlias
        """
        alias = PeripheralAlias(
            vendor_name=vendor_name,
            semantic_name=semantic_name,
            category=category,
            instance=instance,
            base_address=base_address,
        )

        # Store in multiple indices
        self._aliases[vendor_name.upper()] = alias
        self._by_semantic_name[semantic_name] = alias

        if category not in self._by_category:
            self._by_category[category] = []
        self._by_category[category].append(alias)

        logger.debug(f"Added alias: {vendor_name} → {semantic_name} ({category.value})")
        return alias

    def get_alias(self, vendor_name: str) -> PeripheralAlias | None:
        """Get alias for vendor-specific name.

        Args:
            vendor_name: Vendor-specific peripheral name

        Returns:
            PeripheralAlias or None
        """
        return self._aliases.get(vendor_name.upper())

    def get_semantic_name(self, vendor_name: str) -> str | None:
        """Get semantic name for vendor-specific name.

        Args:
            vendor_name: Vendor-specific peripheral name

        Returns:
            Semantic name or None
        """
        alias = self.get_alias(vendor_name)
        return alias.semantic_name if alias else None

    def get_category(self, vendor_name: str) -> SemanticCategory | None:
        """Get semantic category for vendor-specific name.

        Args:
            vendor_name: Vendor-specific peripheral name

        Returns:
            SemanticCategory or None
        """
        alias = self.get_alias(vendor_name)
        return alias.category if alias else None

    def get_by_category(self, category: SemanticCategory) -> list[PeripheralAlias]:
        """Get all peripherals in a category.

        Args:
            category: Semantic category

        Returns:
            List of peripheral aliases
        """
        return self._by_category.get(category, [])

    def get_by_semantic_name(self, semantic_name: str) -> PeripheralAlias | None:
        """Get alias by semantic name.

        Args:
            semantic_name: Semantic peripheral name

        Returns:
            PeripheralAlias or None
        """
        return self._by_semantic_name.get(semantic_name)

    def get_peripherals_by_category(
        self,
        category_name: str,
    ) -> list[PeripheralAlias]:
        """Get peripherals by category name.

        Args:
            category_name: Category name (e.g., "SerialPeripheral")

        Returns:
            List of peripheral aliases
        """
        try:
            category = SemanticCategory(category_name)
            return self.get_by_category(category)
        except ValueError:
            return []

    def normalize_name(self, vendor_name: str) -> str:
        """Normalize vendor name to standard format.

        Args:
            vendor_name: Vendor-specific name

        Returns:
            Normalized name
        """
        alias = self.get_alias(vendor_name)
        if alias:
            return alias.semantic_name

        # Try to infer from prefix
        upper = vendor_name.upper()
        for prefix, (semantic, _) in self._vendor_prefix_map.items():
            if upper.startswith(prefix):
                # Extract instance number
                instance = ""
                for c in vendor_name[len(prefix):]:
                    if c.isdigit():
                        instance += c
                return f"{semantic}{instance}" if instance else semantic

        return vendor_name

    def get_all_categories(self) -> list[SemanticCategory]:
        """Get all registered categories."""
        return list(self._by_category.keys())

    def get_categories_for_peripheral(self, vendor_name: str) -> list[SemanticCategory]:
        """Get categories a peripheral belongs to (for multi-role peripherals).

        Args:
            vendor_name: Vendor-specific name

        Returns:
            List of categories
        """
        alias = self.get_alias(vendor_name)
        if alias:
            return [alias.category]
        return []

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "aliases": {k: {"semantic_name": v.semantic_name, "category": v.category.value} for k, v in self._aliases.items()},
            "categories": {c.value: len(p) for c, p in self._by_category.items()},
        }


# ============================================================================
# Global Instance
# ============================================================================


_default_mapper: SemanticHardwareMapper | None = None


def get_default_mapper() -> SemanticHardwareMapper:
    """Get the default semantic mapper instance."""
    global _default_mapper
    if _default_mapper is None:
        _default_mapper = SemanticHardwareMapper()
    return _default_mapper
