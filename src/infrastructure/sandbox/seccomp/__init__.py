"""Seccomp sandbox module."""

from typing import Any


class SeccompSandbox:
    """Seccomp-based sandbox."""
    
    async def restrict_syscalls(self, allowed: list[str]) -> None:
        """Restrict syscalls."""
        pass
    
    async def execute(self, code: str) -> Any:
        """Execute restricted code."""
        return {"output": ""}
