"""Versioning transformers module."""

from typing import Any


class Transformer:
    """Base schema transformer."""
    
    async def transform(self, data: Any) -> Any:
        """Transform data."""
        return data
