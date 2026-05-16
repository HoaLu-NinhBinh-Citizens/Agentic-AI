"""Workspace filesystem module."""

from pathlib import Path
from typing import Any


class WorkspaceFS:
    """Workspace filesystem operations."""
    
    def __init__(self, root: str):
        self._root = Path(root)
    
    async def read(self, path: str) -> str:
        """Read file."""
        return (self._root / path).read_text()
    
    async def write(self, path: str, content: str) -> None:
        """Write file."""
        file_path = self._root / path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)
