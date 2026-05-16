"""Hardware validation rules - deterministic correctness rules for hardware."""

from typing import Dict, List


class HardwareRules:
    """
    Deterministic hardware validation rules.

    Each rule returns (pass, message) tuples.
    Organized by category: pin, clock, interrupt, register, bus.
    """

    # ─── Pin Rules ───────────────────────────────────────────────────

    @staticmethod
    def pin_not_reserved(pin: str, reserved_by: str) -> tuple[bool, str]:
        if reserved_by:
            return False, f"Pin {pin} is already reserved by '{reserved_by}'"
        return True, ""

    @staticmethod
    def pin_supports_signal(pin_af: int, signal: str, peripheral: str) -> tuple[bool, str]:
        if pin_af is None:
            return False, f"Pin does not support {peripheral} alternate function"
        return True, ""

    @staticmethod
    def pin_voltage_tolerance(pin_tolerant: bool, voltage: float) -> tuple[bool, str]:
        if not pin_tolerant and voltage > 3.3:
            return False, f"Pin is not 5V-tolerant but requested voltage is {voltage}V"
        return True, ""

    @staticmethod
    def pin_current_limit(current_ma: float, required_ma: float) -> tuple[bool, str]:
        if current_ma > 0 and required_ma > current_ma:
            return False, f"Pin current {required_ma}mA exceeds limit {current_ma}mA"
        return True, ""

    @staticmethod
    def no_duplicate_pin_assignments(assignments: List[Dict]) -> tuple[bool, str]:
        pins_used = {}
        for a in assignments:
            pin = a.get("pin")
            if pin in pins_used:
                return False, f"Pin {pin} assigned to both {a.get('signal')} and {pins_used[pin]}"
            pins_used[pin] = a.get("signal")
        return True, ""

    # ─── Clock Rules ─────────────────────────────────────────────────

    @staticmethod
    def clock_domain_valid(domain: str, valid_domains: List[str]) -> tuple[bool, str]:
        if domain not in valid_domains:
            return False, f"Clock domain '{domain}' not recognized"
        return True, ""

    @staticmethod
    def apb1_speed_limit(frequency_hz: int, limit_hz: int = 42_000_000) -> tuple[bool, str]:
        if frequency_hz > limit_hz:
            return False, f"APB1 frequency {frequency_hz / 1_000_000:.1f} MHz exceeds {limit_hz / 1_000_000:.1f} MHz limit"
        return True, ""

    @staticmethod
    def apb2_speed_limit(frequency_hz: int, limit_hz: int = 84_000_000) -> tuple[bool, str]:
        if frequency_hz > limit_hz:
            return False, f"APB2 frequency {frequency_hz / 1_000_000:.1f} MHz exceeds {limit_hz / 1_000_000:.1f} MHz limit"
        return True, ""

    @staticmethod
    def clock_enabled(peripheral: str, enabled: bool) -> tuple[bool, str]:
        if not enabled:
            return False, f"Clock for {peripheral} must be enabled before configuration"
        return True, ""

    @staticmethod
    def baudrate_error_acceptable(error_ppm: int, max_ppm: int = 10000) -> tuple[bool, str]:
        if error_ppm > max_ppm:
            return False, f"Baudrate error {error_ppm} ppm exceeds acceptable {max_ppm} ppm"
        return True, ""

    @staticmethod
    def pll_configured(configured: bool) -> tuple[bool, str]:
        if not configured:
            return False, "PLL must be configured before enabling peripheral clocks"
        return True, ""

    # ─── Interrupt Rules ─────────────────────────────────────────────

    @staticmethod
    def irq_available(irq: int, allocated_irqs: List[int]) -> tuple[bool, str]:
        if irq in allocated_irqs:
            return False, f"IRQ {irq} is already allocated"
        return True, ""

    @staticmethod
    def priority_valid(priority: int, max_levels: int = 16) -> tuple[bool, str]:
        if priority < 0 or priority >= max_levels:
            return False, f"Priority {priority} out of range (0-{max_levels - 1})"
        return True, ""

    @staticmethod
    def no_priority_conflict(
        priority: int,
        allocated: List[Dict],
    ) -> tuple[bool, str]:
        for alloc in allocated:
            if alloc.get("priority") == priority:
                return False, (
                    f"Priority {priority} conflict with "
                    f"{alloc.get('peripheral')} at IRQ {alloc.get('irq')}"
                )
        return True, ""

    @staticmethod
    def handler_name_valid(name: str) -> tuple[bool, str]:
        if not name or not name.strip():
            return False, "Handler name cannot be empty"
        if not name.endswith("_IRQHandler"):
            return False, "Handler name should end with '_IRQHandler'"
        return True, ""

    # ─── Register Rules ─────────────────────────────────────────────

    @staticmethod
    def register_access_compatible(
        access: str, operation: str
    ) -> tuple[bool, str]:
        if access == "RO" and operation == "write":
            return False, f"Cannot write to read-only register"
        if access == "WO" and operation == "read":
            return False, f"Cannot read from write-only register"
        return True, ""

    @staticmethod
    def bitfield_width_valid(offset: int, width: int) -> tuple[bool, str]:
        if offset < 0 or offset > 31:
            return False, f"Bitfield offset {offset} out of range (0-31)"
        if width < 1 or width > 32:
            return False, f"Bitfield width {width} out of range (1-32)"
        if offset + width > 32:
            return False, f"Bitfield (offset={offset}, width={width}) exceeds 32-bit register"
        return True, ""

    @staticmethod
    def register_offset_aligned(offset: int, width_bytes: int = 4) -> tuple[bool, str]:
        if offset % width_bytes != 0:
            return False, f"Register offset 0x{offset:X} is not {width_bytes}-byte aligned"
        return True, ""

    # ─── Bus / Protocol Rules ────────────────────────────────────────

    @staticmethod
    def spi_clock_speed(max_hz: int, target_hz: int) -> tuple[bool, str]:
        if target_hz > max_hz:
            return False, f"SPI clock {target_hz / 1_000_000:.1f} MHz exceeds peripheral max {max_hz / 1_000_000:.1f} MHz"
        return True, ""

    @staticmethod
    def i2c_address_valid(address: int) -> tuple[bool, str]:
        if address < 0 or address > 127:
            return False, f"I2C address {address} out of valid 7-bit range (0-127)"
        return True, ""

    @staticmethod
    def can_baudrate_valid(baudrate: int) -> tuple[bool, str]:
        standard_baudrates = {125000, 250000, 500000, 800000, 1000000}
        if baudrate not in standard_baudrates:
            return False, f"CAN baudrate {baudrate} is non-standard (recommended: {standard_baudrates})"
        return True, ""

    @staticmethod
    def adc_channel_valid(channel: int, max_channels: int = 16) -> tuple[bool, str]:
        if channel < 0 or channel >= max_channels:
            return False, f"ADC channel {channel} out of range (0-{max_channels - 1})"
        return True, ""

    # ─── System Rules ────────────────────────────────────────────────

    @staticmethod
    def peripheral_not_used(peripheral: str, used_peripherals: List[str]) -> tuple[bool, str]:
        if peripheral in used_peripherals:
            return False, f"Peripheral {peripheral} is already in use"
        return True, ""

    @staticmethod
    def memory_region_valid(address: int, size: int, valid_regions: Dict) -> tuple[bool, str]:
        for region_name, region in valid_regions.items():
            start = region.get("start", 0)
            end = region.get("end", 0)
            if start <= address < end and address + size <= end:
                return True, ""
        return False, f"Address 0x{address:08X} is not in a valid memory region"

    @staticmethod
    def no_flash_write_while_xor(flash_locked: bool) -> tuple[bool, str]:
        if flash_locked:
            return False, "Flash is locked - cannot write"
        return True, ""

    # ─── Rule Collections ─────────────────────────────────────────────

    @classmethod
    def all_pin_rules(cls) -> List:
        return [
            cls.pin_not_reserved,
            cls.pin_supports_signal,
            cls.pin_voltage_tolerance,
            cls.pin_current_limit,
            cls.no_duplicate_pin_assignments,
        ]

    @classmethod
    def all_clock_rules(cls) -> List:
        return [
            cls.clock_domain_valid,
            cls.apb1_speed_limit,
            cls.apb2_speed_limit,
            cls.clock_enabled,
            cls.baudrate_error_acceptable,
        ]

    @classmethod
    def all_interrupt_rules(cls) -> List:
        return [
            cls.irq_available,
            cls.priority_valid,
            cls.no_priority_conflict,
            cls.handler_name_valid,
        ]

    @classmethod
    def all_register_rules(cls) -> List:
        return [
            cls.register_access_compatible,
            cls.bitfield_width_valid,
            cls.register_offset_aligned,
        ]
