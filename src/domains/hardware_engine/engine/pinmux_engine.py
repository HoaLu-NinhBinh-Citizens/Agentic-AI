"""PinMux Engine - GPIO alternate function routing engine."""

from typing import Dict, List, Optional, Tuple

from src.domains.hardware_engine.core.pin_map import PinMap
from src.domains.hardware_engine.core.peripheral_graph import PeripheralGraph
from src.domains.hardware_engine.core.models import (
    PinAssignment,
    AllocationResult,
    AllocationContext,
    ResourceAllocation,
    HardwareConstraint,
    ValidationSeverity,
)


class PinMuxEngine:
    """
    GPIO alternate function routing engine.

    Responsibilities:
    1. Find available pins for a peripheral's signals
    2. Route signals to pins with correct AF numbers
    3. Detect pin conflicts
    4. Generate GPIO configuration sequences
    """

    # Standard signal names for each peripheral type
    SIGNAL_MAP: Dict[str, List[str]] = {
        "USART": ["TX", "RX", "RTS", "CTS"],
        "UART": ["TX", "RX", "RTS", "CTS"],
        "SPI": ["MOSI", "MISO", "SCK", "NSS"],
        "I2C": ["SDA", "SCL"],
        "CAN": ["TX", "RX"],
        "TIM": ["CH1", "CH2", "CH3", "CH4", "ETR"],
        "ADC": ["IN0", "IN1", "IN2", "IN3", "IN4", "IN5"],
        "PWM": ["CH1", "CH2", "CH3", "CH4"],
    }

    def __init__(self, pin_map: PinMap, peripheral_graph: PeripheralGraph):
        self.pin_map = pin_map
        self.peripheral_graph = peripheral_graph

    def find_pins_for_peripheral(
        self, peripheral: str, signals: Optional[List[str]] = None
    ) -> Dict[str, List[str]]:
        """
        Find available pins for each signal of a peripheral.

        Returns dict mapping signal name -> available pin names.
        """
        results = {}
        signal_list = signals or self.SIGNAL_MAP.get(peripheral.upper().split("USART")[0].split("UART")[0].split("SPI")[0].split("I2C")[0].split("CAN")[0].split("TIM")[0], [])

        # Try to extract peripheral type
        ptype = peripheral.upper()
        for stype, sigs in self.SIGNAL_MAP.items():
            if stype in ptype:
                signal_list = sigs
                break

        for signal in signal_list:
            pins = self.pin_map.find_pins_for_signal(signal)
            results[signal] = pins

        return results

    def allocate_pins(
        self, peripheral: str, assignments: Dict[str, str]
    ) -> Tuple[List[PinAssignment], List[str]]:
        """
        Allocate pins for signal assignments.

        Args:
            peripheral: Peripheral name (e.g., "USART2")
            assignments: Dict mapping signal -> pin (e.g., {"TX": "PA2", "RX": "PA3"})

        Returns: (list of PinAssignments, list of errors)
        """
        pin_assignments = []
        errors = []

        for signal, pin in assignments.items():
            af = self.pin_map.get_alternate_function(pin, peripheral)
            if af is None:
                errors.append(
                    f"Pin {pin} does not support alternate function for {peripheral} ({signal})"
                )
                continue

            if not self.pin_map.is_available(pin):
                conflict = self.pin_map.find_conflicts(pin)
                errors.append(
                    f"Pin {pin} is already reserved by {conflict[0]['reserved_by'] if conflict else 'unknown'}"
                )
                continue

            direction = self._infer_direction(signal)
            pa = PinAssignment(
                signal=signal,
                pin=pin,
                alternate_function=af,
                direction=direction,
            )
            pin_assignments.append(pa)
            self.pin_map.reserve_pin(pin, peripheral, signal)

        return pin_assignments, errors

    def generate_gpio_sequence(
        self, assignment: PinAssignment
    ) -> List[str]:
        """
        Generate GPIO initialization sequence for one pin.

        Returns list of register write statements.
        """
        pin = assignment.pin
        af = assignment.alternate_function

        port = pin[0]
        pin_num = int(pin[1:])

        # Register address calculation (simplified for STM32F4)
        # GPIOx_MODER: 4 bits per pin (2 bits used)
        moder_bit = pin_num * 2
        # GPIOx_OTYPER: 1 bit per pin
        # GPIOx_OSPEEDR: 2 bits per pin
        # GPIOx_PUPDR: 2 bits per pin
        # GPIOx_AFRL/AFRH: 4 bits per pin (AF selection)

        if pin_num < 8:
            aflr_reg = f"GPIO{port}->AFRL"
        else:
            aflr_reg = f"GPIO{port}->AFRH"

        afr_shift = (pin_num % 8) * 4

        statements = [
            f"/* Configure {pin} as AF{af} for peripheral */",
            f"MODER_{port}{pin_num}_AF = 2;     /* Alternate function mode */",
            f"OTYPER_{port}{pin_num}_PUSHPULL; /* Push-pull (default) */",
            f"OSPEEDR_{port}{pin_num}_FAST;    /* High speed */",
            f"PUPDR_{port}{pin_num}_NONE;      /* No pull-up/down */",
            f"{aflr_reg} = ({aflr_reg} & ~(0xF << {afr_shift})) | ({af} << {afr_shift});",
        ]
        return statements

    def _infer_direction(self, signal: str) -> str:
        signal = signal.upper()
        if signal in {"TX", "MOSI", "SCK", "NSS", "SCL"}:
            return "output"
        if signal in {"RX", "MISO"}:
            return "input"
        if signal in {"CH1", "CH2", "CH3", "CH4", "ETR"}:
            return "alternate"
        return "input"

    def validate_pin_assignment(
        self, peripheral: str, pin: str, signal: str
    ) -> Tuple[bool, str]:
        """Validate that a pin can connect to a peripheral signal."""
        if not self.pin_map._pins.get(pin):
            return False, f"Pin {pin} not found in pin map"

        af = self.pin_map.get_alternate_function(pin, peripheral)
        if af is None:
            return False, f"Pin {pin} does not support {peripheral} alternate function"

        if not self.pin_map.is_available(pin):
            conflicts = self.pin_map.find_conflicts(pin)
            if conflicts:
                return False, f"Pin {pin} reserved by {conflicts[0]['reserved_by']}"
            return False, f"Pin {pin} is not available"

        return True, ""

    def auto_allocate(
        self, peripheral: str, mode: str = "default"
    ) -> Tuple[List[PinAssignment], List[str]]:
        """
        Automatically allocate pins for a peripheral based on default mappings.

        Uses predefined pin assignments for common peripherals.
        """
        defaults = self._default_assignments(peripheral)
        return self.allocate_pins(peripheral, defaults)

    def _default_assignments(self, peripheral: str) -> Dict[str, str]:
        """Get default pin assignments for common peripherals."""
        defaults = {
            "USART1": {"TX": "PA9", "RX": "PA10"},
            "USART2": {"TX": "PA2", "RX": "PA3"},
            "USART3": {"TX": "PB10", "RX": "PB11"},
            "SPI1": {"MOSI": "PA7", "MISO": "PA6", "SCK": "PA5"},
            "SPI2": {"MOSI": "PB15", "MISO": "PB14", "SCK": "PB13"},
            "I2C1": {"SDA": "PB7", "SCL": "PB6"},
            "I2C2": {"SDA": "PB11", "SCL": "PB10"},
            "CAN1": {"TX": "PA12", "RX": "PA11"},
            "CAN2": {"TX": "PB13", "RX": "PB12"},
        }
        return defaults.get(peripheral, {})
