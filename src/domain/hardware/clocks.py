"""Clocks domain module."""


class Clock:
    """Represents a clock domain."""
    
    def __init__(self, name: str, frequency: int):
        self.name = name
        self.frequency = frequency
        self.enabled = False
