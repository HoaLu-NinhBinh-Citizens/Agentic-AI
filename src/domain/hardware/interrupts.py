"""Interrupts domain module."""


class Interrupt:
    """Represents a hardware interrupt."""
    
    def __init__(self, name: str, number: int, priority: int = 0):
        self.name = name
        self.number = number
        self.priority = priority
