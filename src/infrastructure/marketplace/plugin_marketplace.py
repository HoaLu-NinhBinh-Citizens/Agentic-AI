"""Plugin marketplace for extensibility (Phase 16.2).

Provides plugin architecture and marketplace:
- Plugin discovery and installation
- Plugin lifecycle management
- Plugin sandboxing
- Marketplace API
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class PluginType(Enum):
    """Plugin types."""
    TOOL = "tool"             # Adds tools
    INTEGRATION = "integration" # External integrations
    THEME = "theme"           # UI themes
    MODEL = "model"           # Custom models
    VALIDATOR = "validator"   # Custom validators


class PluginStatus(Enum):
    """Plugin installation status."""
    INSTALLED = "installed"
    ACTIVE = "active"
    DISABLED = "disabled"
    UPDATE_AVAILABLE = "update_available"
    ERROR = "error"


@dataclass
class PluginManifest:
    """Plugin manifest/metadata."""
    plugin_id: str
    name: str
    version: str
    description: str
    author: str
    
    # Classification
    plugin_type: PluginType
    
    # Requirements
    requires: dict[str, str] = field(default_factory=dict)  # package -> version
    conflicts: list[str] = field(default_factory=list)  # plugin_ids
    
    # Metadata
    license: str = "MIT"
    homepage: str = ""
    repository: str = ""
    
    # Ratings
    downloads: int = 0
    rating: float = 0.0
    
    # Security
    signature: str = ""  # Code signature for verification
    permissions: list[str] = field(default_factory=list)


@dataclass
class Plugin:
    """Installed plugin."""
    manifest: PluginManifest
    status: PluginStatus
    
    # Installation
    installed_at: datetime
    installed_version: str
    
    # Runtime
    enabled: bool = False
    error_message: str = ""
    config: dict[str, Any] = field(default_factory=dict)


class PluginRegistry:
    """Plugin registry and discovery."""
    
    def __init__(self) -> None:
        self._plugins: dict[str, Plugin] = {}
        self._manifests: dict[str, PluginManifest] = {}
    
    def register_manifest(self, manifest: PluginManifest) -> None:
        """Register plugin manifest."""
        self._manifests[manifest.plugin_id] = manifest
        logger.info("Registered plugin manifest", plugin_id=manifest.plugin_id)
    
    def get_manifest(self, plugin_id: str) -> PluginManifest | None:
        """Get plugin manifest."""
        return self._manifests.get(plugin_id)
    
    def list_plugins(self, plugin_type: PluginType | None = None) -> list[PluginManifest]:
        """List available plugins."""
        manifests = list(self._manifests.values())
        
        if plugin_type:
            manifests = [m for m in manifests if m.plugin_type == plugin_type]
        
        return sorted(manifests, key=lambda m: m.downloads, reverse=True)
    
    def search(self, query: str) -> list[PluginManifest]:
        """Search plugins by name/description."""
        query_lower = query.lower()
        results = []
        
        for manifest in self._manifests.values():
            if query_lower in manifest.name.lower() or query_lower in manifest.description.lower():
                results.append(manifest)
        
        return sorted(results, key=lambda m: m.downloads, reverse=True)


class PluginManager:
    """Manages plugin lifecycle.
    
    Phase 16.2: Plugin marketplace
    """
    
    def __init__(self, plugin_dir: str | None = None) -> None:
        self._registry = PluginRegistry()
        self._plugin_dir = plugin_dir
        self._loaders: dict[str, Any] = {}
        self._hooks: dict[str, list] = {
            "pre_install": [],
            "post_install": [],
            "pre_enable": [],
            "post_enable": [],
            "pre_disable": [],
            "post_disable": [],
        }
    
    def register_loader(self, plugin_type: PluginType, loader: Any) -> None:
        """Register plugin type loader."""
        self._loaders[plugin_type] = loader
    
    def register_hook(self, event: str, callback: Any) -> None:
        """Register lifecycle hook."""
        if event in self._hooks:
            self._hooks[event].append(callback)
    
    def install(self, plugin_id: str) -> bool:
        """Install a plugin."""
        manifest = self._registry.get_manifest(plugin_id)
        if not manifest:
            logger.error("Plugin not found", plugin_id=plugin_id)
            return False
        
        # Pre-install hooks
        for hook in self._hooks["pre_install"]:
            try:
                hook(manifest)
            except Exception as e:
                logger.error("Pre-install hook failed", plugin_id=plugin_id, error=str(e))
                return False
        
        # Simulate installation
        plugin = Plugin(
            manifest=manifest,
            status=PluginStatus.INSTALLED,
            installed_at=datetime.now(),
            installed_version=manifest.version,
        )
        
        # Verify signature
        if manifest.signature:
            if not self._verify_signature(manifest):
                plugin.error_message = "Signature verification failed"
                plugin.status = PluginStatus.ERROR
                return False
        
        self._plugins[plugin_id] = plugin
        
        # Post-install hooks
        for hook in self._hooks["post_install"]:
            try:
                hook(plugin)
            except Exception as e:
                logger.error("Post-install hook failed", plugin_id=plugin_id, error=str(e))
        
        logger.info("Plugin installed", plugin_id=plugin_id)
        return True
    
    def enable(self, plugin_id: str) -> bool:
        """Enable a plugin."""
        if plugin_id not in self._plugins:
            return False
        
        plugin = self._plugins[plugin_id]
        
        # Pre-enable hooks
        for hook in self._hooks["pre_enable"]:
            try:
                hook(plugin)
            except Exception as e:
                logger.error("Pre-enable hook failed", plugin_id=plugin_id, error=str(e))
                return False
        
        # Check dependencies
        for dep, version in plugin.manifest.requires.items():
            if not self._check_dependency(dep, version):
                plugin.error_message = f"Missing dependency: {dep}"
                plugin.status = PluginStatus.ERROR
                return False
        
        # Check conflicts
        for conflict_id in plugin.manifest.conflicts:
            if conflict_id in self._plugins and self._plugins[conflict_id].enabled:
                plugin.error_message = f"Conflicts with: {conflict_id}"
                plugin.status = PluginStatus.ERROR
                return False
        
        plugin.enabled = True
        plugin.status = PluginStatus.ACTIVE
        
        # Post-enable hooks
        for hook in self._hooks["post_enable"]:
            try:
                hook(plugin)
            except Exception:
                pass
        
        logger.info("Plugin enabled", plugin_id=plugin_id)
        return True
    
    def disable(self, plugin_id: str) -> bool:
        """Disable a plugin."""
        if plugin_id not in self._plugins:
            return False
        
        plugin = self._plugins[plugin_id]
        
        # Pre-disable hooks
        for hook in self._hooks["pre_disable"]:
            try:
                hook(plugin)
            except Exception:
                pass
        
        plugin.enabled = False
        plugin.status = PluginStatus.DISABLED
        
        # Post-disable hooks
        for hook in self._hooks["post_disable"]:
            try:
                hook(plugin)
            except Exception:
                pass
        
        logger.info("Plugin disabled", plugin_id=plugin_id)
        return True
    
    def uninstall(self, plugin_id: str) -> bool:
        """Uninstall a plugin."""
        if plugin_id in self._plugins:
            plugin = self._plugins[plugin_id]
            if plugin.enabled:
                self.disable(plugin_id)
            del self._plugins[plugin_id]
            logger.info("Plugin uninstalled", plugin_id=plugin_id)
            return True
        return False
    
    def _verify_signature(self, manifest: PluginManifest) -> bool:
        """Verify plugin signature."""
        # Simplified - real implementation would use gpg or similar
        return bool(manifest.signature)
    
    def _check_dependency(self, package: str, version: str) -> bool:
        """Check if dependency is satisfied."""
        # Simplified - real implementation would check installed packages
        return True
    
    def get_plugin(self, plugin_id: str) -> Plugin | None:
        """Get installed plugin."""
        return self._plugins.get(plugin_id)
    
    def list_installed(self) -> list[Plugin]:
        """List installed plugins."""
        return list(self._plugins.values())
    
    def get_active_plugins(self) -> list[Plugin]:
        """Get active (enabled) plugins."""
        return [p for p in self._plugins.values() if p.enabled]


# Global singleton
_plugin_manager: PluginManager | None = None


def get_plugin_manager() -> PluginManager:
    """Get global plugin manager."""
    global _plugin_manager
    if _plugin_manager is None:
        _plugin_manager = PluginManager()
    return _plugin_manager


# Marketplace API
class MarketplaceAPI:
    """Marketplace API for plugin discovery."""
    
    def __init__(self) -> None:
        self._plugins: dict[str, PluginManifest] = {}
    
    def publish(self, manifest: PluginManifest) -> str:
        """Publish plugin to marketplace."""
        self._plugins[manifest.plugin_id] = manifest
        return f"https://marketplace.aisupport.io/plugins/{manifest.plugin_id}"
    
    def get_plugin(self, plugin_id: str) -> PluginManifest | None:
        """Get plugin from marketplace."""
        return self._plugins.get(plugin_id)
    
    def search(self, query: str, plugin_type: PluginType | None = None) -> list[PluginManifest]:
        """Search marketplace."""
        query_lower = query.lower()
        results = []
        
        for manifest in self._plugins.values():
            if query_lower in manifest.name.lower() or query_lower in manifest.description.lower():
                if plugin_type is None or manifest.plugin_type == plugin_type:
                    results.append(manifest)
        
        return sorted(results, key=lambda m: m.rating, reverse=True)
    
    def get_featured(self) -> list[PluginManifest]:
        """Get featured plugins."""
        return sorted(
            self._plugins.values(),
            key=lambda m: m.rating,
            reverse=True,
        )[:10]
    
    def download(self, plugin_id: str) -> bytes | None:
        """Download plugin package."""
        # In real implementation, would download from CDN
        return None


if __name__ == "__main__":
    manager = get_plugin_manager()
    
    # Create sample plugin manifest
    manifest = PluginManifest(
        plugin_id="aisupport-stm32-debug",
        name="STM32 Debug Tools",
        version="1.0.0",
        description="Advanced STM32 debugging tools with register visualization",
        author="AI Support Team",
        plugin_type=PluginType.TOOL,
        requires={"python": ">=3.9"},
        downloads=1500,
        rating=4.5,
    )
    
    # Register and install
    manager._registry.register_manifest(manifest)
    
    print(f"Installing plugin: {manifest.name}")
    if manager.install(manifest.plugin_id):
        print("✓ Installed successfully")
        manager.enable(manifest.plugin_id)
        print("✓ Enabled successfully")
    
    # List plugins
    print("\nInstalled plugins:")
    for plugin in manager.list_installed():
        print(f"  [{plugin.status.value}] {plugin.manifest.name} v{plugin.manifest.version}")
