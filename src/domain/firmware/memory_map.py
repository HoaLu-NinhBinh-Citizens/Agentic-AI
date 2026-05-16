"""Memory map domain module."""


class MemoryMap:
    """Represents firmware memory layout."""
    
    def __init__(self):
        self.regions: dict[str, tuple[int, int]] = {}
    
    def add_region(self, name: str, start: int, size: int) -> None:
        """Add a memory region."""
        self.regions[name] = (start, size)
