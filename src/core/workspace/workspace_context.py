"""Workspace context stub."""

from pathlib import Path
from dataclasses import dataclass, field
from typing import Any


@dataclass
class WorkspaceContext:
    """Context for a workspace."""
    
    workspace_id: str
    root: Path
    files: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def add_file(self, path: str) -> None:
        """Add file to workspace."""
        self.files.append(path)
