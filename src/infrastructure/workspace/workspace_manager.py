"""Multiple workspace support for Agentic-AI.

Features:
- Workspace management
- Workspace switching
- Workspace state isolation
- Workspace-specific configuration
- Workspace caching
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4


@dataclass
class WorkspaceConfig:
    """Configuration for a workspace."""
    name: str
    root: Path
    description: str = ""
    auto_load: bool = True
    
    # Memory settings
    memory_enabled: bool = True
    memory_dir: Path | None = None
    
    # Tool settings
    tools_enabled: list[str] = field(default_factory=list)
    
    # LLM settings
    llm_provider: str = "openai"
    llm_model: str = "gpt-4o"
    
    # Editor settings
    vim_mode: bool = False
    tab_size: int = 4
    auto_save: bool = True


@dataclass
class WorkspaceState:
    """State of a workspace."""
    workspace_id: str
    config: WorkspaceConfig
    is_active: bool = False
    
    # Runtime state
    open_files: list[str] = field(default_factory=list)
    current_file: str | None = None
    recent_files: list[str] = field(default_factory=list)
    
    # Session data
    session_id: str | None = None
    session_data: dict = field(default_factory=dict)
    
    # Timestamps
    created_at: str = ""
    last_accessed: str = ""
    last_modified: str = ""


class WorkspaceManager:
    """Manages multiple workspaces.
    
    Each workspace has isolated state, configuration, and history.
    """
    
    def __init__(self, config_dir: Path | None = None):
        self.config_dir = config_dir or Path.home() / ".config" / "agentic-ai" / "workspaces"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        self._workspaces: dict[str, WorkspaceState] = {}
        self._active_workspace: str | None = None
        self._workspace_locks: dict[str, asyncio.Lock] = {}
        
        self._load_workspaces()
    
    def _load_workspaces(self) -> None:
        """Load workspace configurations."""
        for config_file in self.config_dir.glob("*.json"):
            try:
                data = json.loads(config_file.read_text())
                
                config = WorkspaceConfig(
                    name=data["name"],
                    root=Path(data["root"]),
                    description=data.get("description", ""),
                    auto_load=data.get("auto_load", True),
                )
                
                state = WorkspaceState(
                    workspace_id=config_file.stem,
                    config=config,
                    created_at=data.get("created_at", ""),
                    last_accessed=data.get("last_accessed", ""),
                    last_modified=data.get("last_modified", ""),
                )
                
                self._workspaces[state.workspace_id] = state
                
            except Exception:
                pass
    
    def _save_workspace(self, workspace_id: str) -> None:
        """Save workspace configuration."""
        state = self._workspaces.get(workspace_id)
        if not state:
            return
        
        data = {
            "name": state.config.name,
            "root": str(state.config.root),
            "description": state.config.description,
            "auto_load": state.config.auto_load,
            "memory_enabled": state.config.memory_enabled,
            "tools_enabled": state.config.tools_enabled,
            "llm_provider": state.config.llm_provider,
            "llm_model": state.config.llm_model,
            "vim_mode": state.config.vim_mode,
            "tab_size": state.config.tab_size,
            "auto_save": state.config.auto_save,
            "created_at": state.created_at,
            "last_accessed": state.last_accessed,
            "last_modified": state.last_modified,
        }
        
        config_file = self.config_dir / f"{workspace_id}.json"
        config_file.write_text(json.dumps(data, indent=2))
    
    def create_workspace(
        self,
        name: str,
        root: Path,
        description: str = "",
    ) -> WorkspaceState:
        """Create a new workspace."""
        import time
        
        workspace_id = str(uuid4())[:8]
        
        config = WorkspaceConfig(
            name=name,
            root=root,
            description=description,
        )
        
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        
        state = WorkspaceState(
            workspace_id=workspace_id,
            config=config,
            created_at=now,
            last_accessed=now,
        )
        
        self._workspaces[workspace_id] = state
        self._workspace_locks[workspace_id] = asyncio.Lock()
        
        self._save_workspace(workspace_id)
        
        return state
    
    def get_workspace(self, workspace_id: str) -> WorkspaceState | None:
        """Get workspace by ID."""
        return self._workspaces.get(workspace_id)
    
    def get_workspace_by_name(self, name: str) -> WorkspaceState | None:
        """Get workspace by name."""
        for state in self._workspaces.values():
            if state.config.name == name:
                return state
        return None
    
    def list_workspaces(self) -> list[WorkspaceState]:
        """List all workspaces."""
        return list(self._workspaces.values())
    
    def list_workspace_ids(self) -> list[str]:
        """List all workspace IDs."""
        return list(self._workspaces.keys())
    
    async def activate_workspace(self, workspace_id: str) -> WorkspaceState:
        """Activate a workspace."""
        import time
        
        # Deactivate current
        if self._active_workspace:
            current = self._workspaces.get(self._active_workspace)
            if current:
                current.is_active = False
                self._save_workspace(self._active_workspace)
        
        # Activate new
        state = self._workspaces.get(workspace_id)
        if not state:
            raise ValueError(f"Workspace not found: {workspace_id}")
        
        state.is_active = True
        state.last_accessed = time.strftime("%Y-%m-%d %H:%M:%S")
        
        self._active_workspace = workspace_id
        
        # Create lock if not exists
        if workspace_id not in self._workspace_locks:
            self._workspace_locks[workspace_id] = asyncio.Lock()
        
        self._save_workspace(workspace_id)
        
        return state
    
    def get_active_workspace(self) -> WorkspaceState | None:
        """Get the active workspace."""
        if self._active_workspace:
            return self._workspaces.get(self._active_workspace)
        return None
    
    async def get_workspace_lock(self, workspace_id: str) -> asyncio.Lock:
        """Get the lock for a workspace."""
        if workspace_id not in self._workspace_locks:
            self._workspace_locks[workspace_id] = asyncio.Lock()
        return self._workspace_locks[workspace_id]
    
    def update_workspace(
        self,
        workspace_id: str,
        updates: dict[str, Any],
    ) -> WorkspaceState | None:
        """Update workspace configuration."""
        import time
        
        state = self._workspaces.get(workspace_id)
        if not state:
            return None
        
        # Update config fields
        config_fields = [
            "name", "description", "auto_load", "memory_enabled",
            "tools_enabled", "llm_provider", "llm_model",
            "vim_mode", "tab_size", "auto_save",
        ]
        
        for key, value in updates.items():
            if key in config_fields:
                setattr(state.config, key, value)
        
        state.last_modified = time.strftime("%Y-%m-%d %H:%M:%S")
        
        self._save_workspace(workspace_id)
        
        return state
    
    def delete_workspace(self, workspace_id: str) -> bool:
        """Delete a workspace."""
        if workspace_id not in self._workspaces:
            return False
        
        # Remove config file
        config_file = self.config_dir / f"{workspace_id}.json"
        if config_file.exists():
            config_file.unlink()
        
        # Remove from memory
        del self._workspaces[workspace_id]
        if workspace_id in self._workspace_locks:
            del self._workspace_locks[workspace_id]
        
        # If was active, clear active
        if self._active_workspace == workspace_id:
            self._active_workspace = None
        
        return True
    
    def update_state(
        self,
        workspace_id: str,
        state_updates: dict[str, Any],
    ) -> WorkspaceState | None:
        """Update workspace runtime state."""
        state = self._workspaces.get(workspace_id)
        if not state:
            return None
        
        for key, value in state_updates.items():
            if hasattr(state, key) and key not in ("workspace_id", "config"):
                setattr(state, key, value)
        
        return state
    
    def get_workspace_context(self, workspace_id: str) -> dict[str, Any]:
        """Get full context for a workspace."""
        state = self._workspaces.get(workspace_id)
        if not state:
            return {}
        
        return {
            "workspace_id": state.workspace_id,
            "name": state.config.name,
            "root": str(state.config.root),
            "description": state.config.description,
            "is_active": state.is_active,
            "open_files": state.open_files,
            "current_file": state.current_file,
            "recent_files": state.recent_files[:10],
            "session_id": state.session_id,
            "llm": {
                "provider": state.config.llm_provider,
                "model": state.config.llm_model,
            },
            "editor": {
                "vim_mode": state.config.vim_mode,
                "tab_size": state.config.tab_size,
            },
        }


class WorkspaceContext:
    """Context manager for workspace operations."""
    
    def __init__(self, manager: WorkspaceManager, workspace_id: str):
        self.manager = manager
        self.workspace_id = workspace_id
        self._lock: asyncio.Lock | None = None
    
    async def __aenter__(self) -> WorkspaceState:
        """Enter workspace context."""
        self._lock = await self.manager.get_workspace_lock(self.workspace_id)
        await self._lock.acquire()
        return self.manager.get_workspace(self.workspace_id)
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit workspace context."""
        if self._lock:
            self._lock.release()


# Convenience functions

def get_default_workspaces_dir() -> Path:
    """Get the default workspaces directory."""
    return Path.home() / ".config" / "agentic-ai" / "workspaces"


def discover_workspaces(root: Path | None = None) -> list[Path]:
    """Discover potential workspace roots."""
    if root is None:
        root = Path.home()
    
    workspaces = []
    
    # Common workspace patterns
    patterns = [
        "**/.workspace",
        "**/.code-workspace",
        "**/workspace.json",
    ]
    
    for pattern in patterns:
        workspaces.extend(root.glob(pattern))
    
    return workspaces


def create_workspace_from_git(repo_path: Path) -> WorkspaceConfig:
    """Create workspace config from git repository."""
    git_dir = repo_path / ".git"
    
    if not git_dir.exists():
        raise ValueError(f"Not a git repository: {repo_path}")
    
    # Get repo name from remote
    name = repo_path.name
    
    # Try to get description
    description = ""
    git_config = repo_path / ".git" / "config"
    if git_config.exists():
        config_text = git_config.read_text()
        if "remote" in config_text:
            # Extract first remote URL
            import re
            match = re.search(r'url\s*=\s*(.+)', config_text)
            if match:
                description = f"Git: {match.group(1).strip()}"
    
    return WorkspaceConfig(
        name=name,
        root=repo_path,
        description=description,
    )
