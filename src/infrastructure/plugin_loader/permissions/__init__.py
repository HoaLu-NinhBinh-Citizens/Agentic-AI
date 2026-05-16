"""Plugin permissions module."""

from typing import Any


class PluginPermissions:
    """Manages plugin permissions."""
    
    def __init__(self):
        self._permissions: dict[str, list[str]] = {}
    
    def grant(self, plugin: str, permission: str) -> None:
        """Grant permission to plugin."""
        if plugin not in self._permissions:
            self._permissions[plugin] = []
        self._permissions[plugin].append(permission)
    
    def has_permission(self, plugin: str, permission: str) -> bool:
        """Check if plugin has permission."""
        return permission in self._permissions.get(plugin, [])
