"""Plugin loader and manager."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

from .discovery import Plugin, PluginDiscovery

logger = logging.getLogger(__name__)


class PluginLoader:
    """Load and manage plugins for AI_SUPPORT."""

    def __init__(self, workspace: Optional[Path] = None):
        """Initialize plugin loader.

        Args:
            workspace: Workspace root
        """
        self.workspace = workspace or Path.cwd()
        self.discovery = PluginDiscovery(self.workspace)
        self._loaded = False

    def load_all(self) -> List[Plugin]:
        """Load all available plugins.

        Returns:
            List of loaded plugins
        """
        if not self._loaded:
            plugins = self.discovery.discover()
            self._loaded = True
            return plugins
        return self.discovery.list_plugins()

    def reload(self) -> List[Plugin]:
        """Reload all plugins."""
        self._loaded = False
        return self.load_all()

    def get_plugin(self, name: str) -> Optional[Plugin]:
        """Get a plugin by name."""
        return self.discovery.get_plugin(name)

    def enable(self, name: str) -> bool:
        """Enable a plugin."""
        return self.discovery.enable(name)

    def disable(self, name: str) -> bool:
        """Disable a plugin."""
        return self.discovery.disable(name)
