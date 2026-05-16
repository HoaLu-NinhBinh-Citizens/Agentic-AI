"""Plugin registry module."""

from typing import Any


class PluginRegistry:
    """Registry for plugins."""
    
    def __init__(self):
        self._plugins: dict[str, Any] = {}
    
    def register(self, name: str, plugin: Any) -> None:
        """Register a plugin."""
        self._plugins[name] = plugin
    
    def get(self, name: str) -> Any | None:
        """Get a plugin."""
        return self._plugins.get(name)
