"""SVD parser domain module."""

from typing import Any


class SVDParser:
    """Parse SVD files for MCU description."""
    
    def parse(self, svd_path: str) -> dict[str, Any]:
        """Parse SVD file."""
        return {"peripherals": [], "registers": []}
