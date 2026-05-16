"""GPTVisor sandbox module."""

from typing import Any


class GVisorSandbox:
    """gVisor-based sandbox."""
    
    async def start(self) -> str:
        """Start sandbox."""
        return "gvisor_container"
    
    async def execute(self, code: str) -> Any:
        """Execute code."""
        return {"output": ""}
