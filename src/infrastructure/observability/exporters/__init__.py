"""Exporters module."""

from typing import Any


class Exporter:
    """Base exporter class."""
    
    def export(self, data: Any) -> None:
        """Export data."""
        pass
