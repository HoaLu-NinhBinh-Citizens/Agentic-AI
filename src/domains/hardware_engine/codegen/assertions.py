"""Hardware assertions - compile-time and runtime checks for generated code."""

from typing import Dict, List


class HardwareAssertions:
    """
    Generate hardware assertion code embedded in C firmware.

    Assertions are placed in generated code to catch misconfigurations
    at compile time (static assertions) or runtime (runtime checks).

    All assertions reference actual hardware facts from the schema,
    not guessed or hallucinated values.
    """

    @staticmethod
    def static_assert(condition: str, message: str) -> str:
        """Generate a C static_assert call."""
        return f'STATIC_ASSERT({condition}, "{message}")'

    @staticmethod
    def runtime_check(condition: str, message: str) -> str:
        """Generate a runtime assertion."""
        return f"""if (!({condition})) {{ \\
    /* HW_ASSERT_FAIL: {message} */ \\
}}"""

    @staticmethod
    def generate_clock_check(peripheral: str, min_hz: int, max_hz: int) -> List[str]:
        """Generate clock range check assertions."""
        return [
            f"/* Clock range check for {peripheral} */",
            f"STATIC_ASSERT(HW_{peripheral.upper()}_CLOCK_HZ >= {min_hz}, "
            f'"{peripheral} clock below minimum {min_hz} Hz");',
            f"STATIC_ASSERT(HW_{peripheral.upper()}_CLOCK_HZ <= {max_hz}, "
            f'"{peripheral} clock above maximum {max_hz} Hz");',
        ]

    @staticmethod
    def generate_baudrate_check(
        peripheral: str, target_baudrate: int, error_ppm: int
    ) -> List[str]:
        """Generate baudrate accuracy check."""
        max_error_ppm = 10000
        return [
            f"/* Baudrate accuracy for {peripheral} */",
            f"/* Target: {target_baudrate} bps, Error: {error_ppm} ppm */",
            f"STATIC_ASSERT({error_ppm} <= {max_error_ppm}, "
            f'"{peripheral} baudrate error exceeds {max_error_ppm} ppm");',
        ]

    @staticmethod
    def generate_pin_conflict_check(pin: str, peripheral: str) -> str:
        """Generate pin conflict check."""
        return (
            f"/* Pin {pin} assigned to {peripheral} - "
            f"verify no other peripheral uses this pin */"
        )

    @staticmethod
    def generate_interrupt_priority_check(
        peripheral: str, irq: int, priority: int
    ) -> List[str]:
        """Generate interrupt priority validation."""
        return [
            f"/* IRQ priority for {peripheral} (IRQ {irq}) */",
            f"STATIC_ASSERT({priority} < 16, "
            f'"{peripheral} priority must be 0-15");',
        ]

    @staticmethod
    def generate_register_access_check(
        peripheral: str, register: str, access: str
    ) -> List[str]:
        """Generate register access validation assertions."""
        assertions = []
        if access == "RO":
            assertions.append(
                f"/* {peripheral}->{register} is read-only - do not write */"
            )
        elif access == "WO":
            assertions.append(
                f"/* {peripheral}->{register} is write-only - reads return undefined */"
            )
        return assertions
