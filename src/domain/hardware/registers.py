"""Registers domain module."""


class Register:
    """Represents a hardware register."""
    
    def __init__(self, name: str, address: int, size: int = 32):
        self.name = name
        self.address = address
        self.size = size
        self.bitfields: list[dict] = []
