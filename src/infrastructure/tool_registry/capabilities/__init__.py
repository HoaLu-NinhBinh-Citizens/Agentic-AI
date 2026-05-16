"""Tool capabilities module."""

from typing import Any


class ToolCapabilities:
    """Describes tool capabilities."""
    
    def __init__(self, name: str):
        self.name = name
        self.supports_streaming = False
        self.supports_batch = False
        self.max_concurrency = 1
