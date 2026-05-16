"""Workspace manager stub."""

from pathlib import Path
from typing import Any


class WorkspaceManager:
    """Manages workspace contexts."""
    
    def __init__(self):
        self._workspaces: dict[str, Path] = {}
    
    def create(self, workspace_id: str, path: str) -> None:
        """Create a new workspace."""
        self._workspaces[workspace_id] = Path(path)
    
    def get(self, workspace_id: str) -> Path | None:
        """Get workspace path."""
        return self._workspaces.get(workspace_id)
    
    def delete(self, workspace_id: str) -> None:
        """Delete a workspace."""
        if workspace_id in self._workspaces:
            del self._workspaces[workspace_id]
