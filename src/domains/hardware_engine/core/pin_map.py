"""Pin Map - GPIO alternate function routing model."""

from dataclasses import dataclass
from typing import Dict, List, Optional, Set


class PinMap:
    """
    GPIO pin alternate function routing model.

    Models:
    - Port/Pin naming (e.g., PA9, PB6)
    - Alternate function numbers per pin
    - Pin availability and conflicts
    - Signal-to-pin routing
    """

    def __init__(self):
        self._pins: Dict[str, "_PinState"] = {}
        self._signals: Dict[str, List[str]] = {}
        self._conflicts: List[str] = []

    def add_pin(self, name: str, port: str, number: int, **kwargs):
        self._pins[name] = _PinState(
            name=name,
            port=port,
            number=number,
            analog=kwargs.get("analog", []),
            af0=kwargs.get("af0", ""),
            af1=kwargs.get("af1", ""),
            af2=kwargs.get("af2", ""),
            af3=kwargs.get("af3", ""),
            af4=kwargs.get("af4", ""),
            af5=kwargs.get("af5", ""),
            af6=kwargs.get("af6", ""),
            af7=kwargs.get("af7", ""),
            af8=kwargs.get("af8", ""),
            af9=kwargs.get("af9", ""),
            af10=kwargs.get("af10", ""),
            af11=kwargs.get("af11", ""),
            af12=kwargs.get("af12", ""),
            af13=kwargs.get("af13", ""),
            af14=kwargs.get("af14", ""),
            af15=kwargs.get("af15", ""),
            reserved_by=kwargs.get("reserved_by", ""),
            voltage_tolerance=kwargs.get("voltage_tolerance", False),
        )

    def add_signal_pin_mapping(self, signal: str, pin: str):
        if signal not in self._signals:
            self._signals[signal] = []
        if pin not in self._signals[signal]:
            self._signals[signal].append(pin)

    def reserve_pin(self, pin: str, peripheral: str, signal: str):
        if pin in self._pins:
            self._pins[pin].reserved_by = peripheral
            self._pins[pin].reserved_signal = signal

    def release_pin(self, pin: str):
        if pin in self._pins:
            self._pins[pin].reserved_by = ""
            self._pins[pin].reserved_signal = ""

    def is_available(self, pin: str) -> bool:
        p = self._pins.get(pin)
        if not p:
            return False
        return p.reserved_by == ""

    def get_available_pins(self) -> List[str]:
        return [name for name, p in self._pins.items() if p.reserved_by == ""]

    def get_alternate_function(self, pin: str, peripheral: str) -> Optional[int]:
        """Get AF number for a pin to connect to a peripheral."""
        p = self._pins.get(pin)
        if not p:
            return None

        af_fields = [
            p.af0, p.af1, p.af2, p.af3, p.af4, p.af5, p.af6, p.af7,
            p.af8, p.af9, p.af10, p.af11, p.af12, p.af13, p.af14, p.af15,
        ]
        for i, af in enumerate(af_fields):
            if af and peripheral.upper() in af.upper():
                return i
        return None

    def find_pins_for_signal(self, signal: str) -> List[str]:
        """Find all pins that support a signal."""
        results = []
        for name, p in self._pins.items():
            af_fields = [
                p.af0, p.af1, p.af2, p.af3, p.af4, p.af5, p.af6, p.af7,
                p.af8, p.af9, p.af10, p.af11, p.af12, p.af13, p.af14, p.af15,
            ]
            for af in af_fields:
                if af and signal.upper() in af.upper():
                    if self.is_available(name):
                        results.append(name)
                    break
        return results

    def find_conflicts(self, pin: str) -> List[Dict]:
        """Find pin conflicts."""
        results = []
        p = self._pins.get(pin)
        if p and p.reserved_by:
            results.append({
                "pin": pin,
                "reserved_by": p.reserved_by,
                "signal": p.reserved_signal,
                "conflict_type": "hard_reserved",
            })
        return results

    def assign(self, pin: str, peripheral: str, signal: str) -> bool:
        """Assign a pin to a peripheral signal."""
        if not self.is_available(pin):
            self._conflicts.append(f"Pin {pin} already reserved by {self._pins[pin].reserved_by}")
            return False
        self.reserve_pin(pin, peripheral, signal)
        return True

    def get_signal_mapping(self, signal: str) -> List[str]:
        return self._signals.get(signal, [])

    def count(self) -> int:
        return len(self._pins)

    def count_available(self) -> int:
        return len(self.get_available_pins())

    def list_pins(self) -> List[str]:
        return sorted(self._pins.keys())

    def get_pin_info(self, pin: str) -> dict:
        p = self._pins.get(pin)
        if not p:
            return {}
        afs = {}
        for i in range(16):
            af_val = getattr(p, f"af{i}", "")
            if af_val:
                afs[f"AF{i}"] = af_val
        return {
            "name": p.name,
            "port": p.port,
            "number": p.number,
            "available": p.reserved_by == "",
            "reserved_by": p.reserved_by,
            "analog": p.analog,
            "alternate_functions": afs,
            "voltage_tolerance": p.voltage_tolerance,
        }

    def reset(self):
        for p in self._pins.values():
            p.reserved_by = ""
            p.reserved_signal = ""
        self._conflicts.clear()

    def to_dict(self) -> dict:
        return {
            "total_pins": self.count(),
            "available_pins": self.count_available(),
            "reservations": {
                name: {"by": p.reserved_by, "signal": p.reserved_signal}
                for name, p in self._pins.items()
                if p.reserved_by
            },
            "signal_mappings": dict(self._signals),
            "conflicts": self._conflicts,
        }


class _PinState:
    __slots__ = (
        "name", "port", "number", "analog",
        "af0", "af1", "af2", "af3", "af4", "af5", "af6", "af7",
        "af8", "af9", "af10", "af11", "af12", "af13", "af14", "af15",
        "reserved_by", "reserved_signal", "voltage_tolerance",
    )

    def __init__(
        self, name: str, port: str, number: int,
        analog=None,
        af0="", af1="", af2="", af3="", af4="", af5="", af6="", af7="",
        af8="", af9="", af10="", af11="", af12="", af13="", af14="", af15="",
        reserved_by="", reserved_signal="", voltage_tolerance=False,
    ):
        self.name = name
        self.port = port
        self.number = number
        self.analog = analog or []
        self.af0 = af0
        self.af1 = af1
        self.af2 = af2
        self.af3 = af3
        self.af4 = af4
        self.af5 = af5
        self.af6 = af6
        self.af7 = af7
        self.af8 = af8
        self.af9 = af9
        self.af10 = af10
        self.af11 = af11
        self.af12 = af12
        self.af13 = af13
        self.af14 = af14
        self.af15 = af15
        self.reserved_by = reserved_by
        self.reserved_signal = reserved_signal
        self.voltage_tolerance = voltage_tolerance
