"""Sandbox factory module."""

from typing import Any


class SandboxFactory:
    """Factory for creating sandboxes."""
    
    async def create(self, sandbox_type: str) -> Any:
        """Create sandbox."""
        if sandbox_type == "docker":
            from .docker import DockerSandbox
            return DockerSandbox()
        return None
