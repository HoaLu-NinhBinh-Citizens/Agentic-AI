"""Docker sandbox module."""

from typing import Any


class DockerSandbox:
    """Docker-based sandbox."""
    
    def __init__(self):
        self._container_id: str | None = None
    
    async def start(self, image: str) -> str:
        """Start sandbox."""
        self._container_id = "stub_container"
        return self._container_id
    
    async def execute(self, command: str) -> dict[str, Any]:
        """Execute in sandbox."""
        return {"output": "", "exit_code": 0}
    
    async def stop(self) -> None:
        """Stop sandbox."""
        self._container_id = None
