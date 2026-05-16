"""Workspace ownership module."""

from typing import Any


class WorkspaceOwnership:
    """Manages workspace file ownership."""
    
    def __init__(self):
        self._ownership: dict[str, str] = {}
    
    def set_owner(self, path: str, owner: str) -> None:
        """Set file owner."""
        self._ownership[path] = owner
    
    def get_owner(self, path: str) -> str | None:
        """Get file owner."""
        return self._ownership.get(path)
