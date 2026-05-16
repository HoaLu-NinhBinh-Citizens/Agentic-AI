"""Peripheral Graph - hardware topology model for the Hardware Semantic Engine."""

from typing import Dict, List, Optional, Set

from src.domains.hardware_engine.core.models import (
    Chip,
    Peripheral,
    Signal,
    Interrupt,
    PeripheralState,
)


class PeripheralGraph:
    """
    Graph model of chip hardware topology.

    Models the relationship between:
    - Peripherals and their resources (registers, interrupts, signals)
    - Signal routing between peripherals and pins
    - Clock tree dependencies
    - Interrupt dependencies
    """

    def __init__(self):
        self._chip: Optional[Chip] = None
        self._peripherals: Dict[str, Peripheral] = {}
        self._signals: Dict[str, List[Signal]] = {}
        self._interrupts_by_peripheral: Dict[str, List[Interrupt]] = {}
        self._interrupts_by_irq: Dict[int, Interrupt] = {}
        self._peripheral_dependencies: Dict[str, Set[str]] = {}

    def set_chip(self, chip: Chip):
        self._chip = chip

    def chip(self) -> Optional[Chip]:
        return self._chip

    def add_peripheral(self, peripheral: Peripheral):
        self._peripherals[peripheral.name] = peripheral
        for interrupt in peripheral.interrupts:
            self._interrupts_by_irq[interrupt.irq_line] = interrupt
        self._interrupts_by_peripheral[peripheral.name] = peripheral.interrupts
        for signal in peripheral.signals:
            if signal.name not in self._signals:
                self._signals[signal.name] = []
            self._signals[signal.name].append(signal)

    def get_peripheral(self, name: str) -> Optional[Peripheral]:
        return self._peripherals.get(name)

    def list_peripherals(self) -> List[str]:
        return sorted(self._peripherals.keys())

    def has_peripheral(self, name: str) -> bool:
        return name in self._peripherals

    def get_peripherals_by_protocol(self, protocol: str) -> List[Peripheral]:
        protocol = protocol.upper()
        return [
            p
            for p in self._peripherals.values()
            if p.protocol.upper() == protocol
        ]

    def get_interrupt(self, irq_line: int) -> Optional[Interrupt]:
        return self._interrupts_by_irq.get(irq_line)

    def get_interrupt_by_name(self, name: str) -> Optional[Interrupt]:
        for irq in self._interrupts_by_irq.values():
            if irq.name.upper() == name.upper():
                return irq
        return None

    def get_signals(self, signal_name: str) -> List[Signal]:
        return self._signals.get(signal_name, [])

    def get_peripheral_by_signal(self, signal_name: str) -> List[str]:
        result = []
        for p_name, signals in self._signals.items():
            for sig in signals:
                if sig.name == signal_name:
                    result.append(sig.peripheral)
        return result

    def add_dependency(self, dependent: str, depends_on: str):
        if dependent not in self._peripheral_dependencies:
            self._peripheral_dependencies[dependent] = set()
        self._peripheral_dependencies[dependent].add(depends_on)

    def get_dependencies(self, peripheral: str) -> Set[str]:
        return self._peripheral_dependencies.get(peripheral, set())

    def topological_sort(self) -> List[str]:
        """Return peripherals in dependency order."""
        visited: Set[str] = set()
        result: List[str] = []

        def visit(name: str):
            if name in visited:
                return
            visited.add(name)
            for dep in self.get_dependencies(name):
                visit(dep)
            result.append(name)

        for name in self._peripherals:
            visit(name)
        return result

    def validate_dependencies(self) -> List[str]:
        """Return list of circular dependency errors."""
        errors = []
        for name in self._peripherals:
            deps = self.get_dependencies(name)
            for dep in deps:
                if dep not in self._peripherals:
                    errors.append(f"Peripheral '{name}' depends on unknown '{dep}'")
        return errors

    def get_clock_domain(self, peripheral: str) -> Optional[str]:
        """Infer clock domain from peripheral name conventions."""
        p = self._peripherals.get(peripheral)
        if not p:
            return None
        if "USART" in peripheral or "UART" in peripheral:
            return "APB1"
        if "SPI" in peripheral:
            return "APB2"
        if "CAN" in peripheral:
            return "APB1"
        if "I2C" in peripheral:
            return "APB1"
        if "ADC" in peripheral:
            return "APB2"
        if "TIM" in peripheral:
            return "APB1" if int(peripheral[-1]) <= 2 else "APB2"
        return "APB1"

    def to_dict(self) -> dict:
        """Export graph as dictionary."""
        return {
            "chip": {
                "name": self._chip.name if self._chip else None,
                "family": self._chip.family if self._chip else None,
                "core": self._chip.core if self._chip else None,
            },
            "peripherals": {
                name: {
                    "base_address": f"0x{peri.base_address:08X}",
                    "state": peri.state.value,
                    "registers": [r.name for r in peri.registers],
                    "interrupts": [
                        {"name": i.name, "irq": i.irq_line} for i in peri.interrupts
                    ],
                    "signals": [
                        {"name": s.name, "pin": s.pin} for s in peri.signals
                    ],
                }
                for name, peri in self._peripherals.items()
            },
            "interrupts": {
                str(irq): {
                    "name": i.name,
                    "peripheral": self._find_peripheral_by_irq(irq),
                }
                for irq, i in self._interrupts_by_irq.items()
            },
            "dependencies": {
                name: sorted(deps)
                for name, deps in self._peripheral_dependencies.items()
            },
        }

    def _find_peripheral_by_irq(self, irq_line: int) -> Optional[str]:
        for name, peri in self._peripherals.items():
            for intr in peri.interrupts:
                if intr.irq_line == irq_line:
                    return name
        return None
