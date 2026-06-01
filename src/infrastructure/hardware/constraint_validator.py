"""Hardware Constraint Validator.

Validates hardware configurations against chip capabilities,
clock constraints, interrupt priorities, and GPIO settings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Severity(Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class ValidationIssue:
    """Represents a validation issue."""
    severity: Severity
    rule: str
    message: str
    location: Optional[str] = None
    suggestion: Optional[str] = None


@dataclass
class ValidationResult:
    """Result of hardware validation."""
    valid: bool
    issues: list[ValidationIssue]
    warnings: list[ValidationIssue]
    info: list[ValidationIssue]

    @classmethod
    def from_issues(cls, issues: list[ValidationIssue]) -> ValidationResult:
        errors = [i for i in issues if i.severity == Severity.ERROR]
        warnings = [i for i in issues if i.severity == Severity.WARNING]
        info = [i for i in issues if i.severity == Severity.INFO]
        return cls(
            valid=len(errors) == 0,
            issues=errors,
            warnings=warnings,
            info=info,
        )


class HardwareConstraintValidator:
    """Validates hardware configurations."""

    # STM32F4 clock limits
    STM32F4_LIMITS = {
        "sysclk_max": 168_000_000,
        "ahb_max": 168_000_000,
        "apb1_max": 42_000_000,
        "apb2_max": 84_000_000,
        "adc_max": 36_000_000,
    }

    # STM32F4 peripheral clock enables
    RCC_REGS = {
        "GPIOA": "RCC_AHB1ENR",
        "GPIOB": "RCC_AHB1ENR",
        "GPIOC": "RCC_AHB1ENR",
        "GPIOD": "RCC_AHB1ENR",
        "USART1": "RCC_APB2ENR",
        "USART2": "RCC_APB1ENR",
        "SPI1": "RCC_APB2ENR",
        "SPI2": "RCC_APB1ENR",
        "I2C1": "RCC_APB1ENR",
        "ADC1": "RCC_APB2ENR",
        "CAN1": "RCC_APB1ENR",
        "TIM1": "RCC_APB2ENR",
        "TIM2": "RCC_APB1ENR",
        "DMA1": "RCC_AHB1ENR",
    }

    def __init__(self, chip_family: str = "STM32F4"):
        self.chip_family = chip_family
        self.limits = self.STM32F4_LIMITS

    def validate_clock_config(
        self,
        sysclk: int,
        ahb_prescaler: int = 1,
        apb1_prescaler: int = 1,
        apb2_prescaler: int = 1,
    ) -> ValidationResult:
        """Validate clock configuration."""
        issues = []

        # Calculate frequencies
        ahb_freq = sysclk / ahb_prescaler
        apb1_freq = ahb_freq / apb1_prescaler
        apb2_freq = ahb_freq / apb2_prescaler

        # Check SYSCLK
        if sysclk > self.limits["sysclk_max"]:
            issues.append(ValidationIssue(
                severity=Severity.ERROR,
                rule="CLOCK001",
                message=f"SYSCLK {sysclk/1e6:.0f} MHz exceeds maximum {self.limits['sysclk_max']/1e6:.0f} MHz",
                suggestion="Reduce PLL multiplier or use lower HSI/HSE frequency",
            ))

        # Check AHB
        if ahb_freq > self.limits["ahb_max"]:
            issues.append(ValidationIssue(
                severity=Severity.ERROR,
                rule="CLOCK002",
                message=f"AHB frequency {ahb_freq/1e6:.0f} MHz exceeds maximum {self.limits['ahb_max']/1e6:.0f} MHz",
                suggestion="Increase AHB prescaler (HPRE)",
            ))

        # Check APB1 (max 42 MHz for STM32F4)
        if apb1_freq > self.limits["apb1_max"]:
            issues.append(ValidationIssue(
                severity=Severity.ERROR,
                rule="CLOCK003",
                message=f"APB1 frequency {apb1_freq/1e6:.0f} MHz exceeds maximum {self.limits['apb1_max']/1e6:.0f} MHz",
                suggestion="Increase APB1 prescaler (PPRE1). Note: APB1 timers run at 2x if PCLK1 >= 42MHz",
            ))

        # Check APB2
        if apb2_freq > self.limits["apb2_max"]:
            issues.append(ValidationIssue(
                severity=Severity.ERROR,
                rule="CLOCK004",
                message=f"APB2 frequency {apb2_freq/1e6:.0f} MHz exceeds maximum {self.limits['apb2_max']/1e6:.0f} MHz",
                suggestion="Increase APB2 prescaler (PPRE2)",
            ))

        # Warnings
        if apb1_freq == self.limits["apb1_max"]:
            issues.append(ValidationIssue(
                severity=Severity.WARNING,
                rule="CLOCK005",
                message="APB1 at maximum frequency. USART, SPI, I2C peripherals will run at normal speed.",
                suggestion="APB1 timer peripherals run at 2x (84 MHz) when PCLK1 = 42 MHz",
            ))

        return ValidationResult.from_issues(issues)

    def validate_gpio_config(
        self,
        port: str,
        pin: int,
        mode: str,
        alt_function: Optional[int] = None,
        pull: str = "none",
        speed: str = "low",
        output_type: str = "pushpull",
    ) -> ValidationResult:
        """Validate GPIO configuration."""
        issues = []

        # Check port/pin validity
        if port not in ["A", "B", "C", "D", "E", "F", "G", "H"]:
            issues.append(ValidationIssue(
                severity=Severity.ERROR,
                rule="GPIO001",
                message=f"Invalid GPIO port: {port}",
                suggestion="Use ports A-H only",
            ))

        if pin < 0 or pin > 15:
            issues.append(ValidationIssue(
                severity=Severity.ERROR,
                rule="GPIO002",
                message=f"Invalid pin number: {pin}",
                suggestion="GPIO pins are 0-15",
            ))

        # Check mode
        valid_modes = ["input", "output", "alternate", "analog"]
        if mode not in valid_modes:
            issues.append(ValidationIssue(
                severity=Severity.ERROR,
                rule="GPIO003",
                message=f"Invalid GPIO mode: {mode}",
                suggestion=f"Use one of: {', '.join(valid_modes)}",
            ))

        # Check alternate function
        if mode == "alternate" and (alt_function is None or alt_function < 0 or alt_function > 15):
            issues.append(ValidationIssue(
                severity=Severity.ERROR,
                rule="GPIO004",
                message="Alternate function mode requires valid AF number (0-15)",
                suggestion="Set alt_function to the correct AF number for the peripheral",
            ))

        # Check pull configuration
        valid_pulls = ["none", "up", "down"]
        if pull not in valid_pulls:
            issues.append(ValidationIssue(
                severity=Severity.WARNING,
                rule="GPIO005",
                message=f"Unusual pull configuration: {pull}",
                suggestion=f"Use pull-up, pull-down, or none for digital modes",
            ))

        # Check output speed for high-speed pins
        if mode == "output" or mode == "alternate":
            if speed == "low":
                # Check for high-speed peripherals
                high_speed_peripherals = ["USART", "SPI", "I2C"]
                issues.append(ValidationIssue(
                    severity=Severity.INFO,
                    rule="GPIO006",
                    message="Low speed mode set for output/alternate function pin",
                    suggestion="Consider medium/high speed for USART, SPI, I2C pins for signal integrity",
                ))

        return ValidationResult.from_issues(issues)

    def validate_interrupt_priority(
        self,
        irq_name: str,
        priority: int,
        chip_family: str = "STM32F4",
    ) -> ValidationResult:
        """Validate interrupt priority configuration."""
        issues = []

        # Determine priority bits based on chip
        if "F0" in chip_family or "L0" in chip_family or "G0" in chip_family:
            max_priority = 2  # 2 bits = 4 levels
        elif "F1" in chip_family or "F2" in chip_family:
            max_priority = 4  # 4 bits = 16 levels
        else:
            max_priority = 4  # Default for most STM32

        # Check priority validity
        if priority < 0 or priority >= (2 ** max_priority):
            issues.append(ValidationIssue(
                severity=Severity.ERROR,
                rule="IRQ001",
                message=f"Priority {priority} out of range (0-{2**max_priority - 1}) for {chip_family}",
                suggestion=f"Priority must be 0-{2**max_priority - 1}",
            ))

        # Check for invalid priorities on hard faults
        if irq_name in ["HardFault", "MemManage", "BusFault", "UsageFault"]:
            if priority != 0:
                issues.append(ValidationIssue(
                    severity=Severity.ERROR,
                    rule="IRQ002",
                    message=f"{irq_name} must have priority 0 (highest)",
                    suggestion="Set priority to 0 for fault handlers",
                ))

        # Check for priority inversion risks
        critical_irqs = ["HardFault", "NMI", "SysTick"]
        if irq_name not in critical_irqs and priority == 0:
            issues.append(ValidationIssue(
                severity=Severity.WARNING,
                rule="IRQ003",
                message=f"{irq_name} has maximum priority (0), same as faults",
                suggestion="Reserve priority 0 for fault handlers. Use priority 1+ for application interrupts.",
            ))

        # Check subpriority grouping
        if priority < 16:
            issues.append(ValidationIssue(
                severity=Severity.INFO,
                rule="IRQ004",
                message=f"{irq_name} priority {priority} may cause preemption issues",
                suggestion="Consider using subpriority bits if you need nested interrupts",
            ))

        return ValidationResult.from_issues(issues)

    def validate_dma_config(
        self,
        channel: int,
        peripheral: str,
        direction: str,
        memory_increment: bool = False,
        peripheral_increment: bool = False,
        circular_mode: bool = False,
    ) -> ValidationResult:
        """Validate DMA configuration."""
        issues = []

        # Check channel validity (STM32F4 has channels 1-8 for DMA1)
        if channel < 1 or channel > 8:
            issues.append(ValidationIssue(
                severity=Severity.ERROR,
                rule="DMA001",
                message=f"Invalid DMA channel: {channel}",
                suggestion="DMA1 channels are 1-8, DMA2 channels are 1-8",
            ))

        # Check direction
        valid_directions = ["peripheral_to_memory", "memory_to_peripheral", "memory_to_memory"]
        if direction not in valid_directions:
            issues.append(ValidationIssue(
                severity=Severity.ERROR,
                rule="DMA002",
                message=f"Invalid DMA direction: {direction}",
                suggestion=f"Use: {', '.join(valid_directions)}",
            ))

        # Memory-to-memory requires channel 5 or 6 (DMA1) or 3 (DMA2)
        if direction == "memory_to_memory":
            if channel not in [5, 6]:
                issues.append(ValidationIssue(
                    severity=Severity.ERROR,
                    rule="DMA003",
                    message="Memory-to-memory DMA only on channels 5, 6 (DMA1)",
                    suggestion="Use channel 5 or 6 for memory-to-memory transfers",
                ))

        # Check for circular mode with both increments
        if circular_mode and memory_increment and peripheral_increment:
            issues.append(ValidationIssue(
                severity=Severity.WARNING,
                rule="DMA004",
                message="Circular mode with both memory and peripheral increment may cause issues",
                suggestion="Ensure your buffer size matches the peripheral data width",
            ))

        return ValidationResult.from_issues(issues)

    def validate_peripheral_init(
        self,
        peripheral: str,
        enabled: bool = True,
        clock_enabled: bool = False,
    ) -> ValidationResult:
        """Validate peripheral initialization sequence."""
        issues = []

        # Check if clock is enabled before peripheral
        if enabled and not clock_enabled:
            issues.append(ValidationIssue(
                severity=Severity.ERROR,
                rule="INIT001",
                message=f"Peripheral {peripheral} enabled without clock",
                suggestion=f"Enable clock in RCC_{self._get_rcc_reg_name(peripheral)} first",
            ))

        # Check for known peripherals
        known_peripherals = [
            "GPIOA", "GPIOB", "GPIOC", "GPIOD", "GPIOE", "GPIOF", "GPIOG", "GPIOH",
            "USART1", "USART2", "USART3", "UART4", "UART5",
            "SPI1", "SPI2", "SPI3",
            "I2C1", "I2C2", "I2C3",
            "ADC1", "ADC2", "ADC3",
            "TIM1", "TIM2", "TIM3", "TIM4", "TIM5",
            "CAN1", "CAN2",
            "DMA1", "DMA2",
        ]

        if peripheral not in known_peripherals:
            issues.append(ValidationIssue(
                severity=Severity.INFO,
                rule="INIT002",
                message=f"Unknown peripheral: {peripheral}",
                suggestion="Verify peripheral name and ensure it's available on this chip",
            ))

        return ValidationResult.from_issues(issues)

    def validate_uart_config(
        self,
        baudrate: int,
        apb_freq: int,
        oversampling: int = 16,
    ) -> ValidationResult:
        """Validate UART/USART configuration."""
        issues = []

        # Check baudrate limits
        if baudrate < 300 or baudrate > 10_000_000:
            issues.append(ValidationIssue(
                severity=Severity.WARNING,
                rule="UART001",
                message=f"Unusual baudrate: {baudrate}",
                suggestion="Verify baudrate is within valid range for your application",
            ))

        # Check oversampling
        if oversampling not in [8, 16]:
            issues.append(ValidationIssue(
                severity=Severity.ERROR,
                rule="UART002",
                message=f"Invalid oversampling: {oversampling}",
                suggestion="Use oversampling 8 or 16",
            ))

        # Calculate error
        divisor = apb_freq / (8 if oversampling == 8 else 16)
        actual_baudrate = divisor / round(divisor / baudrate)
        error_percent = abs(actual_baudrate - baudrate) / baudrate * 100

        if error_percent > 2.5:
            issues.append(ValidationIssue(
                severity=Severity.ERROR,
                rule="UART003",
                message=f"Baudrate error {error_percent:.2f}% exceeds 2.5% maximum",
                suggestion="Adjust APB frequency or use different baudrate",
            ))
        elif error_percent > 1:
            issues.append(ValidationIssue(
                severity=Severity.WARNING,
                rule="UART004",
                message=f"Baudrate error {error_percent:.2f}% is acceptable but could be improved",
                suggestion="Consider using different APB frequency for better accuracy",
            ))

        return ValidationResult.from_issues(issues)

    def validate_adc_config(
        self,
        prescaler: int,
        sampling_time: int,
        resolution: int,
        adc_freq: int,
    ) -> ValidationResult:
        """Validate ADC configuration."""
        issues = []

        # Check ADC frequency limits
        if adc_freq > self.limits["adc_max"]:
            issues.append(ValidationIssue(
                severity=Severity.ERROR,
                rule="ADC001",
                message=f"ADC frequency {adc_freq/1e6:.0f} MHz exceeds maximum {self.limits['adc_max']/1e6:.0f} MHz",
                suggestion="Increase ADC prescaler",
            ))

        # Check resolution
        if resolution not in [6, 8, 10, 12]:
            issues.append(ValidationIssue(
                severity=Severity.ERROR,
                rule="ADC002",
                message=f"Invalid ADC resolution: {resolution}",
                suggestion="Use resolution 6, 8, 10, or 12 bits",
            ))

        # Check sampling time
        if sampling_time < 3 or sampling_time > 480:
            issues.append(ValidationIssue(
                severity=Severity.WARNING,
                rule="ADC003",
                message=f"ADC sampling time {sampling_time} cycles is unusual",
                suggestion="Typical values: 3, 15, 28, 56, 84, 112, 144, 480 cycles",
            ))

        return ValidationResult.from_issues(issues)

    def _get_rcc_reg_name(self, peripheral: str) -> str:
        """Get RCC register suffix for a peripheral."""
        if peripheral.startswith("GPIO"):
            return "AHB1ENR"
        elif "APB2" in self._get_peripheral_clock_domain(peripheral):
            return "APB2ENR"
        elif "APB1" in self._get_peripheral_clock_domain(peripheral):
            return "APB1ENR"
        elif peripheral.startswith("DMA"):
            return "AHB1ENR"
        return "APB1ENR"  # Default

    def _get_peripheral_clock_domain(self, peripheral: str) -> str:
        """Get clock domain for a peripheral."""
        apb2_peripherals = ["USART1", "SPI1", "SPI2", "I2C1", "ADC1", "TIM1", "TIM8", "TIM9", "TIM10", "TIM11"]
        if peripheral in apb2_peripherals:
            return "APB2"
        return "APB1"
