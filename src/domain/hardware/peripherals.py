"""Peripherals domain module."""


class Peripheral:
    """Represents a hardware peripheral."""
    
    def __init__(self, name: str, base_address: int):
        self.name = name
        self.base_address = base_address
        self.registers: list[dict] = []
