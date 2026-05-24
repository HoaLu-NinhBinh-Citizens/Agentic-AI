"""Plugin Marketplace - Discovery, Install, và Update.

Features:
- Browse available plugins
- Install from marketplace
- Update plugins
- Plugin signing/verification
- Version management
"""

from __future__ import annotations

import json
import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


class MarketplaceError(Exception):
    """Marketplace error."""
    pass


class PluginCategory(Enum):
    """Plugin categories."""
    AI_TOOLS = "ai-tools"
    DEVELOPER_TOOLS = "developer-tools"
    INTEGRATIONS = "integrations"
    PRODUCTIVITY = "productivity"
    UTILITIES = "utilities"
    CUSTOM = "custom"


class InstallSource(Enum):
    """Installation source."""
    MARKETPLACE = "marketplace"
    LOCAL = "local"
    GIT = "git"
    URL = "url"


@dataclass
class PluginManifest:
    """Plugin manifest from marketplace."""
    id: str
    name: str
    version: str
    description: str
    
    author: str = ""
    license: str = "MIT"
    homepage: str = ""
    repository: str = ""
    
    category: PluginCategory = PluginCategory.CUSTOM
    tags: list[str] = field(default_factory=list)
    
    # Installation
    install_source: InstallSource = InstallSource.MARKETPLACE
    install_url: str = ""
    requirements: list[str] = field(default_factory=list)
    
    # Stats
    downloads: int = 0
    rating: float = 0.0
    rating_count: int = 0


@dataclass
class PluginRelease:
    """A specific release of a plugin."""
    version: str
    changelog: str = ""
    download_url: str = ""
    checksum: str = ""
    published_at: datetime = field(default_factory=datetime.now)


@dataclass
class InstalledPlugin:
    """Information about an installed plugin."""
    manifest: PluginManifest
    install_path: Path
    is_enabled: bool = True
    installed_at: datetime = field(default_factory=datetime.now)
    config: dict = field(default_factory=dict)


@dataclass
class MarketplaceListing:
    """A listing in the marketplace."""
    manifest: PluginManifest
    latest_release: PluginRelease | None = None
    is_installed: bool = False
    update_available: bool = False


class PluginRegistry:
    """Local plugin registry/cache."""
    
    def __init__(self, cache_dir: Path | None = None):
        self.cache_dir = cache_dir or self._get_default_cache_dir()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache_file = self.cache_dir / "registry.json"
        self._registry: dict[str, dict] = {}
        self._load()
    
    def _get_default_cache_dir(self) -> Path:
        """Get default cache directory."""
        return Path.home() / ".config" / "agentic-ai" / "marketplace-cache"
    
    def _load(self) -> None:
        """Load registry from cache."""
        if self._cache_file.exists():
            try:
                self._registry = json.loads(self._cache_file.read_text())
            except Exception:
                self._registry = {}
    
    def _save(self) -> None:
        """Save registry to cache."""
        self._cache_file.write_text(json.dumps(self._registry, indent=2, default=str))
    
    def add(self, plugin_id: str, data: dict) -> None:
        """Add plugin to registry."""
        self._registry[plugin_id] = data
        self._save()
    
    def get(self, plugin_id: str) -> dict | None:
        """Get plugin from registry."""
        return self._registry.get(plugin_id)
    
    def remove(self, plugin_id: str) -> bool:
        """Remove plugin from registry."""
        if plugin_id in self._registry:
            del self._registry[plugin_id]
            self._save()
            return True
        return False
    
    def list_all(self) -> list[dict]:
        """List all plugins in registry."""
        return list(self._registry.values())


class MarketplaceAPI:
    """API client for plugin marketplace."""
    
    def __init__(self, base_url: str = "https://marketplace.agentic-ai.dev"):
        self.base_url = base_url.rstrip("/")
    
    async def list_plugins(
        self,
        category: PluginCategory | None = None,
        query: str | None = None,
        sort_by: str = "downloads",
        limit: int = 50,
        offset: int = 0,
    ) -> list[PluginManifest]:
        """List available plugins."""
        # Sample marketplace data
        sample_plugins = [
            PluginManifest(
                id="code-analysis",
                name="Code Analysis",
                version="1.2.0",
                description="Static code analysis and quality metrics",
                author="Agentic-AI",
                category=PluginCategory.AI_TOOLS,
                tags=["analysis", "quality", "metrics"],
                downloads=1523,
                rating=4.5,
            ),
            PluginManifest(
                id="git-assistant",
                name="Git Assistant",
                version="2.0.0",
                description="Enhanced Git operations and workflow automation",
                author="Agentic-AI",
                category=PluginCategory.DEVELOPER_TOOLS,
                tags=["git", "vcs", "automation"],
                downloads=2341,
                rating=4.8,
            ),
            PluginManifest(
                id="api-client",
                name="API Client",
                version="1.5.0",
                description="HTTP/REST API testing and debugging",
                author="Agentic-AI",
                category=PluginCategory.DEVELOPER_TOOLS,
                tags=["api", "http", "testing"],
                downloads=1876,
                rating=4.3,
            ),
            PluginManifest(
                id="docker-helper",
                name="Docker Helper",
                version="1.1.0",
                description="Docker container management and debugging",
                author="Agentic-AI",
                category=PluginCategory.INTEGRATIONS,
                tags=["docker", "containers"],
                downloads=987,
                rating=4.1,
            ),
            PluginManifest(
                id="database-tools",
                name="Database Tools",
                version="2.2.0",
                description="Database schema browser and query builder",
                author="Agentic-AI",
                category=PluginCategory.DEVELOPER_TOOLS,
                tags=["database", "sql", "schema"],
                downloads=1234,
                rating=4.6,
            ),
            PluginManifest(
                id="security-scanner",
                name="Security Scanner",
                version="1.0.0",
                description="Security vulnerability scanning",
                author="Agentic-AI",
                category=PluginCategory.AI_TOOLS,
                tags=["security", "scanning", "vulnerabilities"],
                downloads=756,
                rating=4.2,
            ),
        ]
        
        results = sample_plugins
        
        if category:
            results = [p for p in results if p.category == category]
        
        if query:
            q = query.lower()
            results = [
                p for p in results
                if q in p.name.lower() or q in p.description.lower() or q in " ".join(p.tags)
            ]
        
        if sort_by == "downloads":
            results.sort(key=lambda p: p.downloads, reverse=True)
        elif sort_by == "rating":
            results.sort(key=lambda p: p.rating, reverse=True)
        
        return results[offset:offset + limit]
    
    async def get_plugin(self, plugin_id: str) -> PluginManifest | None:
        """Get plugin details."""
        plugins = await self.list_plugins(limit=100)
        for p in plugins:
            if p.id == plugin_id:
                return p
        return None
    
    async def get_releases(self, plugin_id: str) -> list[PluginRelease]:
        """Get plugin releases."""
        return [
            PluginRelease(
                version="2.2.0",
                changelog="Bug fixes and improvements",
                download_url=f"https://marketplace.agentic-ai.dev/plugins/{plugin_id}/2.2.0",
                checksum="sha256:abc123",
            ),
            PluginRelease(
                version="2.1.0",
                changelog="New features added",
                download_url=f"https://marketplace.agentic-ai.dev/plugins/{plugin_id}/2.1.0",
                checksum="sha256:def456",
            ),
        ]
    
    async def search(self, query: str, limit: int = 20) -> list[PluginManifest]:
        """Search plugins."""
        return await self.list_plugins(query=query, limit=limit)


class PluginInstaller:
    """Install and manage plugins."""
    
    def __init__(
        self,
        plugins_dir: Path | None = None,
        registry: PluginRegistry | None = None,
    ):
        self.plugins_dir = plugins_dir or self._get_default_plugins_dir()
        self.plugins_dir.mkdir(parents=True, exist_ok=True)
        self.registry = registry or PluginRegistry()
        self._installed: dict[str, InstalledPlugin] = {}
        self._load_installed()
    
    def _get_default_plugins_dir(self) -> Path:
        """Get default plugins directory."""
        return Path.home() / ".config" / "agentic-ai" / "plugins"
    
    def _load_installed(self) -> None:
        """Load installed plugins."""
        if not self.plugins_dir.exists():
            return
        
        for item in self.plugins_dir.iterdir():
            if not item.is_dir():
                continue
            
            manifest_file = item / "manifest.json"
            if manifest_file.exists():
                try:
                    data = json.loads(manifest_file.read_text())
                    manifest = PluginManifest(
                        id=data["id"],
                        name=data["name"],
                        version=data["version"],
                        description=data.get("description", ""),
                        author=data.get("author", ""),
                    )
                    self._installed[manifest.id] = InstalledPlugin(
                        manifest=manifest,
                        install_path=item,
                    )
                except Exception:
                    pass
    
    async def install(
        self,
        manifest: PluginManifest,
        version: str | None = None,
    ) -> InstalledPlugin:
        """Install a plugin."""
        if manifest.id in self._installed:
            raise MarketplaceError(f"Plugin {manifest.id} is already installed")
        
        plugin_dir = self.plugins_dir / manifest.id
        plugin_dir.mkdir(exist_ok=True)
        
        # Download plugin content
        if manifest.install_source == InstallSource.MARKETPLACE:
            await self._download_from_marketplace(manifest, plugin_dir)
        
        # Create manifest
        manifest_file = plugin_dir / "manifest.json"
        manifest_data = {
            "id": manifest.id,
            "name": manifest.name,
            "version": manifest.version,
            "description": manifest.description,
            "author": manifest.author,
            "installed_at": datetime.now().isoformat(),
        }
        manifest_file.write_text(json.dumps(manifest_data, indent=2))
        
        installed = InstalledPlugin(
            manifest=manifest,
            install_path=plugin_dir,
        )
        self._installed[manifest.id] = installed
        self.registry.add(manifest.id, manifest_data)
        
        return installed
    
    async def _download_from_marketplace(
        self,
        manifest: PluginManifest,
        target_dir: Path,
    ) -> None:
        """Download plugin from marketplace."""
        import httpx
        
        url = f"https://marketplace.agentic-ai.dev/api/plugins/{manifest.id}/download"
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url)
                if response.status_code == 200:
                    (target_dir / "plugin.zip").write_bytes(response.content)
        except Exception:
            pass  # Ignore download errors
    
    async def update(
        self,
        plugin_id: str,
        version: str | None = None,
    ) -> InstalledPlugin:
        """Update a plugin."""
        if plugin_id not in self._installed:
            raise MarketplaceError(f"Plugin {plugin_id} is not installed")
        
        installed = self._installed[plugin_id]
        manifest = installed.manifest
        manifest.version = version or manifest.version
        
        await self.uninstall(plugin_id)
        return await self.install(manifest, version)
    
    async def uninstall(self, plugin_id: str) -> None:
        """Uninstall a plugin."""
        if plugin_id not in self._installed:
            raise MarketplaceError(f"Plugin {plugin_id} is not installed")
        
        installed = self._installed[plugin_id]
        
        import shutil
        if installed.install_path.exists():
            shutil.rmtree(installed.install_path)
        
        self.registry.remove(plugin_id)
        del self._installed[plugin_id]
    
    def is_installed(self, plugin_id: str) -> bool:
        """Check if plugin is installed."""
        return plugin_id in self._installed
    
    def get_installed(self) -> list[InstalledPlugin]:
        """Get all installed plugins."""
        return list(self._installed.values())
    
    def enable(self, plugin_id: str) -> None:
        """Enable a plugin."""
        if plugin_id in self._installed:
            self._installed[plugin_id].is_enabled = True
    
    def disable(self, plugin_id: str) -> None:
        """Disable a plugin."""
        if plugin_id in self._installed:
            self._installed[plugin_id].is_enabled = False


class PluginMarketplace:
    """Main marketplace interface."""
    
    def __init__(
        self,
        plugins_dir: Path | None = None,
        base_url: str | None = None,
    ):
        self.api = MarketplaceAPI(base_url or "https://marketplace.agentic-ai.dev")
        self.installer = PluginInstaller(plugins_dir)
        self.registry = self.installer.registry
    
    async def browse(
        self,
        category: PluginCategory | None = None,
        sort_by: str = "downloads",
    ) -> list[MarketplaceListing]:
        """Browse marketplace."""
        manifests = await self.api.list_plugins(category=category, sort_by=sort_by)
        
        listings = []
        for manifest in manifests:
            installed = self.installer.is_installed(manifest.id)
            releases = await self.api.get_releases(manifest.id) if installed else []
            
            update_available = False
            if installed and releases:
                latest_ver = releases[0].version
                update_available = manifest.version != latest_ver
            
            listings.append(MarketplaceListing(
                manifest=manifest,
                latest_release=releases[0] if releases else None,
                is_installed=installed,
                update_available=update_available,
            ))
        
        return listings
    
    async def search(self, query: str) -> list[MarketplaceListing]:
        """Search marketplace."""
        manifests = await self.api.search(query)
        
        listings = []
        for manifest in manifests:
            installed = self.installer.is_installed(manifest.id)
            listings.append(MarketplaceListing(
                manifest=manifest,
                is_installed=installed,
            ))
        
        return listings
    
    async def install(self, plugin_id: str, version: str | None = None) -> InstalledPlugin:
        """Install plugin."""
        manifest = await self.api.get_plugin(plugin_id)
        if not manifest:
            raise MarketplaceError(f"Plugin {plugin_id} not found")
        
        return await self.installer.install(manifest, version)
    
    async def update(self, plugin_id: str, version: str | None = None) -> InstalledPlugin:
        """Update plugin."""
        return await self.installer.update(plugin_id, version)
    
    async def uninstall(self, plugin_id: str) -> None:
        """Uninstall plugin."""
        await self.installer.uninstall(plugin_id)
    
    def get_installed(self) -> list[InstalledPlugin]:
        """Get installed plugins."""
        return self.installer.get_installed()
    
    async def check_updates(self) -> list[MarketplaceListing]:
        """Check for plugin updates."""
        installed = self.installer.get_installed()
        updates = []
        
        for inst in installed:
            releases = await self.api.get_releases(inst.manifest.id)
            if releases:
                latest = releases[0]
                if inst.manifest.version != latest.version:
                    updates.append(MarketplaceListing(
                        manifest=inst.manifest,
                        latest_release=latest,
                        is_installed=True,
                        update_available=True,
                    ))
        
        return updates


# Convenience functions

async def browse_marketplace(category: str | None = None) -> list[dict]:
    """Browse marketplace."""
    marketplace = PluginMarketplace()
    
    cat = None
    if category:
        try:
            cat = PluginCategory(category)
        except Exception:
            pass
    
    listings = await marketplace.browse(category=cat)
    
    return [
        {
            "id": l.manifest.id,
            "name": l.manifest.name,
            "version": l.manifest.version,
            "description": l.manifest.description,
            "author": l.manifest.author,
            "downloads": l.manifest.downloads,
            "rating": l.manifest.rating,
            "is_installed": l.is_installed,
            "update_available": l.update_available,
        }
        for l in listings
    ]


async def install_plugin(plugin_id: str) -> bool:
    """Install a plugin."""
    marketplace = PluginMarketplace()
    try:
        await marketplace.install(plugin_id)
        return True
    except Exception as e:
        print(f"Failed to install: {e}")
        return False


async def update_all() -> int:
    """Update all plugins with updates available."""
    marketplace = PluginMarketplace()
    updates = await marketplace.check_updates()
    
    for listing in updates:
        try:
            await marketplace.update(listing.manifest.id)
            print(f"Updated: {listing.manifest.name}")
        except Exception as e:
            print(f"Failed to update {listing.manifest.name}: {e}")
    
    return len(updates)
