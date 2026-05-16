"""gRPC IDL module."""

from typing import Any


class GRPCService:
    """gRPC service stub."""
    
    def __init__(self):
        self._handlers: dict[str, Any] = {}
