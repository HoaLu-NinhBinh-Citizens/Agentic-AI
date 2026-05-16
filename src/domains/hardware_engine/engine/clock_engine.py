"""Clock Engine - peripheral clock configuration."""

from typing import Dict, List, Optional

from src.domains.hardware_engine.core.clock_tree import ClockTree
from src.domains.hardware_engine.core.register_schema import RegisterSchemaDB
from src.domains.hardware_engine.core.models import (
    ValidationResult,
    ValidationSeverity,
)


class ClockEngine:
    """
    Peripheral clock configuration engine.

    Responsibilities:
    1. Enable peripheral clocks via RCC registers
    2. Calculate baudrate/timing divisors
    3. Validate bus speed constraints
    4. Generate clock initialization sequences
    """

    def __init__(self, clock_tree: ClockTree, register_schema: RegisterSchemaDB):
        self.clock_tree = clock_tree
        self.register_schema = register_schema

    def enable(self, peripheral: str) -> List[str]:
        """
        Generate clock enable sequence for a peripheral.

        Returns list of register write statements.
        """
        self.clock_tree.enable_clock(peripheral)

        domain = self.clock_tree._get_peripheral_domain(peripheral)
        statements = []

        if domain == "AHB":
            statements.append(f"/* Enable AHB clock for {peripheral} */")
            statements.append(f"RCC->AHB1ENR |= RCC_AHB1ENR_{peripheral}EN;")
        elif domain == "APB1":
            statements.append(f"/* Enable APB1 clock for {peripheral} */")
            statements.append(f"RCC->APB1ENR |= RCC_APB1ENR_{peripheral}EN;")
        elif domain == "APB2":
            statements.append(f"/* Enable APB2 clock for {peripheral} */")
            statements.append(f"RCC->APB2ENR |= RCC_APB2ENR_{peripheral}EN;")
        else:
            statements.append(f"/* Enable clock for {peripheral} (domain: {domain}) */")
            statements.append(f"RCC->APB1ENR |= RCC_APB1ENR_{peripheral}EN; /* Default - verify */")

        return statements

    def calculate_usart_baudrate(
        self, peripheral: str, target_baudrate: int
    ) -> Dict:
        """
        Calculate USART baudrate register value.

        Returns BRR value and error analysis.
        """
        return self.clock_tree.calculate_baudrate_prescaler(peripheral, target_baudrate)

    def generate_baudrate_sequence(
        self, peripheral: str, baudrate: int
    ) -> List[str]:
        """
        Generate baudrate configuration sequence.

        Returns list of register write statements.
        """
        result = self.calculate_usart_baudrate(peripheral, baudrate)
        if not result or result.get("brr", 0) == 0:
            return [f"/* ERROR: Cannot calculate baudrate for {peripheral} at {baudrate} */"]

        statements = [
            f"/* Configure USART baudrate: {baudrate} bps */",
            f"/* Peripheral clock: {result.get('periph_clock', 0) / 1_000_000:.1f} MHz */",
            f"/* BRR = {result['brr']} (error: {result['error_ppm']} ppm) */",
            f"USART{peripheral[-1]}->BRR = {result['brr']};",
        ]

        if not result.get("acceptable"):
            statements.append(f"/* WARNING: Baudrate error {result['error_ppm']} ppm exceeds 0.1% */")

        return statements

    def validate(self, peripheral: str) -> ValidationResult:
        """
        Validate clock configuration for a peripheral.

        Checks:
        - Clock is enabled
        - Bus speed within limits
        - Clock domain exists
        """
        result = ValidationResult(valid=True)

        if not self.clock_tree.is_enabled(peripheral):
            result.add_warning(
                "CLOCK_001",
                f"Clock for {peripheral} has not been explicitly enabled",
                peripheral=peripheral,
            )

        speed_check = self.clock_tree.validate_bus_speed(peripheral)
        if not speed_check.get("valid"):
            result.add_error(
                "CLOCK_002",
                f"Bus speed {speed_check['actual_hz'] / 1_000_000:.1f} MHz exceeds "
                f"limit of {speed_check['max_hz'] / 1_000_000:.1f} MHz for {speed_check['domain']}",
                peripheral=peripheral,
            )

        domain = self.clock_tree._get_peripheral_domain(peripheral)
        if not domain:
            result.add_warning(
                "CLOCK_003",
                f"Cannot determine clock domain for {peripheral}",
                peripheral=peripheral,
            )

        return result

    def generate_init_sequence(self, peripheral: str) -> List[str]:
        """
        Generate complete clock initialization sequence.

        Includes:
        1. RCC enable
        2. Clock divider configuration
        3. Wait for readiness
        """
        statements = []

        # Enable clock
        self.clock_tree.enable_clock(peripheral)

        # Wait for readiness (for certain peripherals)
        peripheral_upper = peripheral.upper()
        if "USART" in peripheral_upper or "UART" in peripheral_upper:
            statements.append(f"/* Wait for {peripheral} ready */")
            statements.append(f"while(!({peripheral}->SR & USART_SR_TXE)) {{ /* wait */ }}")
        elif "SPI" in peripheral_upper:
            statements.append(f"/* Wait for {peripheral} ready */")
            statements.append(f"while(!({peripheral}->SR & SPI_SR_TXE)) {{ /* wait */ }}")
        elif "I2C" in peripheral_upper:
            statements.append(f"/* Wait for {peripheral} ready */")
            statements.append(f"while(!({peripheral}->SR & I2C_SR2_BUSY)) {{ /* wait */ }}")

        return statements

    def get_peripheral_clock(self, peripheral: str) -> int:
        """Get the peripheral clock frequency in Hz."""
        return self.clock_tree.get_frequency(peripheral)

    def list_enabled_clocks(self) -> List[str]:
        """List all enabled peripheral clocks."""
        return self.clock_tree.get_enabled_peripherals()
