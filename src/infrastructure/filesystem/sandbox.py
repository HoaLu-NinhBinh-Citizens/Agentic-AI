"""Sandbox filesystem module."""

from typing import Any


class SandboxFS:
    """Sandbox filesystem abstraction."""
    
    async def read(self, path: str) -> str:
        """Read from sandbox."""
        return ""
    
    async def write(self, path: str, content: str) -> None:
        """Write to sandbox."""
        pass
