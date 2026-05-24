"""Plugin system for Agentic-AI.

Provides:
- Plugin discovery and loading
- Plugin lifecycle management
- Extension API
- Hot reloading
- Security sandboxing
"""

from __future__ import annotations

import asyncio
import importlib
import importlib.util
import json
import sys
import traceback
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable


class PluginError(Exception):
    """Plugin error."""
    pass


class PluginState(Enum):
    """Plugin lifecycle states."""
    DISCOVERED = "discovered"
    LOADING = "loading"
    LOADED = "loaded"
    INITIALIZING = "initializing"
    ACTIVE = "active"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"
    UNLOADED = "unloaded"


@dataclass
class PluginMetadata:
    """Plugin metadata from manifest."""
    name: str
    version: str
    description: str = ""
    author: str = ""
    license: str = ""
    home_page: str = ""
    
    # Requirements
    python_version: str = ">=3.10"
    dependencies: list[str] = field(default_factory=list)
    
    # Lifecycle hooks
    entry_point: str = ""  # Module or function to call
    on_load: str = ""  # Called when plugin loads
    on_unload: str = ""  # Called when plugin unloads
    on_activate: str = ""  # Called when activated
    on_deactivate: str = ""  # Called when deactivated
    
    # Permissions
    permissions: list[str] = field(default_factory=list)
    
    # UI
    icon: str = ""
    category: str = "general"


@dataclass
class PluginInfo:
    """Loaded plugin information."""
    metadata: PluginMetadata
    path: Path
    state: PluginState = PluginState.DISCOVERED
    
    # Runtime
    module: Any = None
    instance: Any = None
    errors: list[str] = field(default_factory=list)
    
    # Resources
    allocated_memory: int = 0
    cpu_time: float = 0.0


class PluginInterface:
    """Interface that plugins must implement."""
    
    def __init__(self, plugin_info: PluginInfo):
        self.info = plugin_info
        self._resources: dict = {}
    
    # Required methods
    
    def on_load(self) -> None:
        """Called when plugin is loaded."""
        pass
    
    def on_unload(self) -> None:
        """Called when plugin is unloaded."""
        pass
    
    def on_activate(self) -> None:
        """Called when plugin is activated."""
        pass
    
    def on_deactivate(self) -> None:
        """Called when plugin is deactivated."""
        pass
    
    # Optional methods
    
    def get_tools(self) -> list[dict]:
        """Return list of tools this plugin provides."""
        return []
    
    def get_prompts(self) -> list[dict]:
        """Return list of prompts this plugin provides."""
        return []
    
    def get_resources(self) -> list[dict]:
        """Return list of resources this plugin provides."""
        return []
    
    def get_handlers(self) -> dict[str, Callable]:
        """Return event handlers."""
        return {}
    
    # Resource management
    
    def allocate_resource(self, name: str, resource: Any) -> None:
        """Allocate a named resource."""
        self._resources[name] = resource
    
    def get_resource(self, name: str) -> Any | None:
        """Get a named resource."""
        return self._resources.get(name)
    
    def release_resource(self, name: str) -> None:
        """Release a named resource."""
        if name in self._resources:
            del self._resources[name]


class PluginSandbox:
    """Security sandbox for plugins."""
    
    def __init__(self, plugin_path: Path):
        self.plugin_path = plugin_path
        self._allowed_modules: set[str] = {
            "asyncio",
            "pathlib",
            "typing",
            "json",
            "datetime",
            "enum",
            "dataclasses",
            "collections",
            "contextlib",
        }
        self._blocked_modules: set[str] = {
            "os",
            "sys",
            "subprocess",
            "socket",
            "urllib",
            "requests",
        }
    
    def is_module_allowed(self, module_name: str) -> bool:
        """Check if module is allowed."""
        # Block dangerous modules
        for blocked in self._blocked_modules:
            if module_name.startswith(blocked):
                return False
        
        # Allow whitelisted
        for allowed in self._allowed_modules:
            if module_name.startswith(allowed):
                return True
        
        return False
    
    def set_allowed_modules(self, modules: list[str]) -> None:
        """Set allowed modules."""
        self._allowed_modules.update(modules)
    
    def set_blocked_modules(self, modules: list[str]) -> None:
        """Set blocked modules."""
        self._blocked_modules.update(modules)


class PluginManager:
    """Manages plugin lifecycle."""
    
    def __init__(self, plugin_dir: Path | None = None):
        self.plugin_dir = plugin_dir or self._get_default_plugin_dir()
        self.plugin_dir.mkdir(parents=True, exist_ok=True)
        
        self._plugins: dict[str, PluginInfo] = {}
        self._sandboxes: dict[str, PluginSandbox] = {}
        self._hooks: dict[str, list[Callable]] = {}
        self._event_handlers: dict[str, list[tuple[str, Callable]]] = {}
    
    def _get_default_plugin_dir(self) -> Path:
        """Get default plugin directory."""
        return Path.home() / ".config" / "agentic-ai" / "plugins"
    
    async def discover(self) -> list[PluginInfo]:
        """Discover plugins in plugin directory."""
        discovered = []
        
        # Find plugin directories
        for item in self.plugin_dir.iterdir():
            if not item.is_dir():
                continue
            
            manifest_path = item / "manifest.json"
            if not manifest_path.exists():
                continue
            
            try:
                metadata = self._load_manifest(manifest_path)
                info = PluginInfo(
                    metadata=metadata,
                    path=item,
                    state=PluginState.DISCOVERED,
                )
                discovered.append(info)
                self._plugins[metadata.name] = info
                
            except Exception as e:
                print(f"Failed to load manifest {manifest_path}: {e}")
        
        return discovered
    
    def _load_manifest(self, manifest_path: Path) -> PluginMetadata:
        """Load plugin manifest."""
        data = json.loads(manifest_path.read_text())
        
        return PluginMetadata(
            name=data["name"],
            version=data["version"],
            description=data.get("description", ""),
            author=data.get("author", ""),
            license=data.get("license", ""),
            home_page=data.get("home_page", ""),
            python_version=data.get("python_version", ">=3.10"),
            dependencies=data.get("dependencies", []),
            entry_point=data.get("entry_point", ""),
            on_load=data.get("on_load", ""),
            on_unload=data.get("on_unload", ""),
            on_activate=data.get("on_activate", ""),
            on_deactivate=data.get("on_deactivate", ""),
            permissions=data.get("permissions", []),
            icon=data.get("icon", ""),
            category=data.get("category", "general"),
        )
    
    async def load_plugin(self, name: str) -> PluginInfo:
        """Load a plugin."""
        if name not in self._plugins:
            raise PluginError(f"Plugin not discovered: {name}")
        
        info = self._plugins[name]
        
        if info.state != PluginState.DISCOVERED:
            return info
        
        info.state = PluginState.LOADING
        
        try:
            # Check dependencies
            await self._check_dependencies(info.metadata.dependencies)
            
            # Create sandbox
            sandbox = PluginSandbox(info.path)
            self._sandboxes[name] = sandbox
            
            # Load module
            if info.metadata.entry_point:
                # Load from entry point
                module_path = info.path / info.metadata.entry_point
                if module_path.exists():
                    info.module = self._load_module(name, module_path)
                elif "." in info.metadata.entry_point:
                    # Import from installed package
                    info.module = importlib.import_module(info.metadata.entry_point)
            
            info.state = PluginState.LOADED
            
        except Exception as e:
            info.state = PluginState.ERROR
            info.errors.append(str(e))
            raise PluginError(f"Failed to load plugin {name}: {e}")
        
        return info
    
    def _load_module(self, name: str, path: Path) -> Any:
        """Load a Python module from path."""
        spec = importlib.util.spec_from_file_location(name, path)
        if not spec or not spec.loader:
            raise PluginError(f"Cannot load module from {path}")
        
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        
        return module
    
    async def _check_dependencies(self, dependencies: list[str]) -> None:
        """Check if dependencies are available."""
        for dep in dependencies:
            # Simple check - would need packaging for real check
            try:
                dep_name = dep.split(">=")[0].split("<=")[0].split("==")[0].split("!=")[0].strip()
                importlib.import_module(dep_name)
            except ImportError:
                raise PluginError(f"Missing dependency: {dep}")
    
    async def activate_plugin(self, name: str) -> PluginInfo:
        """Activate a loaded plugin."""
        if name not in self._plugins:
            raise PluginError(f"Plugin not found: {name}")
        
        info = self._plugins[name]
        
        if info.state != PluginState.LOADED:
            if info.state == PluginState.DISCOVERED:
                await self.load_plugin(name)
            else:
                raise PluginError(f"Cannot activate plugin in state: {info.state}")
        
        info.state = PluginState.INITIALIZING
        
        try:
            # Create instance
            if info.module:
                plugin_class = getattr(info.module, "Plugin", None)
                if plugin_class and issubclass(plugin_class, PluginInterface):
                    info.instance = plugin_class(info)
                else:
                    # Use default
                    info.instance = PluginInterface(info)
            
            # Call on_load
            if info.instance and info.metadata.on_load:
                handler = getattr(info.instance, info.metadata.on_load, None)
                if handler:
                    await self._call_handler(handler)
            
            # Call on_activate
            if info.instance and info.metadata.on_activate:
                handler = getattr(info.instance, info.metadata.on_activate, None)
                if handler:
                    await self._call_handler(handler)
            
            # Register hooks
            if info.instance:
                handlers = info.instance.get_handlers()
                for event, handler in handlers.items():
                    self.register_hook(event, handler)
            
            info.state = PluginState.ACTIVE
            
        except Exception as e:
            info.state = PluginState.ERROR
            info.errors.append(str(e))
            raise PluginError(f"Failed to activate plugin {name}: {e}")
        
        return info
    
    async def deactivate_plugin(self, name: str) -> None:
        """Deactivate a plugin."""
        if name not in self._plugins:
            return
        
        info = self._plugins[name]
        
        if info.state != PluginState.ACTIVE:
            return
        
        info.state = PluginState.STOPPING
        
        try:
            # Call on_deactivate
            if info.instance and info.metadata.on_deactivate:
                handler = getattr(info.instance, info.metadata.on_deactivate, None)
                if handler:
                    await self._call_handler(handler)
            
            # Call on_unload
            if info.instance and info.metadata.on_unload:
                handler = getattr(info.instance, info.metadata.on_unload, None)
                if handler:
                    await self._call_handler(handler)
            
            # Unregister hooks
            self._unregister_hooks(name)
            
            # Release resources
            if info.instance:
                for resource in list(info.instance._resources.values()):
                    if hasattr(resource, "close"):
                        try:
                            resource.close()
                        except:
                            pass
            
            info.state = PluginState.STOPPED
            
        except Exception as e:
            info.state = PluginState.ERROR
            info.errors.append(str(e))
    
    async def unload_plugin(self, name: str) -> None:
        """Unload a plugin completely."""
        await self.deactivate_plugin(name)
        
        if name in self._plugins:
            info = self._plugins[name]
            
            # Remove module
            if info.metadata.name in sys.modules:
                del sys.modules[info.metadata.name]
            
            info.state = PluginState.UNLOADED
    
    async def _call_handler(self, handler: Callable) -> Any:
        """Call a handler, handling async/sync."""
        if asyncio.iscoroutinefunction(handler):
            return await handler()
        return handler()
    
    # Hook system
    
    def register_hook(self, event: str, handler: Callable) -> None:
        """Register a hook handler."""
        if event not in self._hooks:
            self._hooks[event] = []
        self._hooks[event].append(handler)
    
    def unregister_hook(self, event: str, handler: Callable) -> None:
        """Unregister a hook handler."""
        if event in self._hooks:
            self._hooks[event] = [h for h in self._hooks[event] if h != handler]
    
    def _unregister_hooks(self, plugin_name: str) -> None:
        """Unregister all hooks for a plugin."""
        # This would need plugin tracking in hooks
        pass
    
    async def emit_hook(self, event: str, *args, **kwargs) -> list[Any]:
        """Emit an event to all registered hooks."""
        if event not in self._hooks:
            return []
        
        results = []
        for handler in self._hooks[event]:
            try:
                result = await self._call_handler(handler)
                results.append(result)
            except Exception as e:
                print(f"Hook error for {event}: {e}")
        
        return results
    
    # Plugin queries
    
    def get_plugin(self, name: str) -> PluginInfo | None:
        """Get plugin by name."""
        return self._plugins.get(name)
    
    def list_plugins(self, state: PluginState | None = None) -> list[PluginInfo]:
        """List plugins, optionally filtered by state."""
        plugins = list(self._plugins.values())
        if state:
            plugins = [p for p in plugins if p.state == state]
        return plugins
    
    def get_active_plugins(self) -> list[PluginInfo]:
        """Get all active plugins."""
        return self.list_plugins(PluginState.ACTIVE)
    
    # Tools from plugins
    
    def get_all_tools(self) -> list[dict]:
        """Get tools from all active plugins."""
        tools = []
        for info in self.get_active_plugins():
            if info.instance:
                try:
                    tools.extend(info.instance.get_tools())
                except:
                    pass
        return tools
    
    def get_all_prompts(self) -> list[dict]:
        """Get prompts from all active plugins."""
        prompts = []
        for info in self.get_active_plugins():
            if info.instance:
                try:
                    prompts.extend(info.instance.get_prompts())
                except:
                    pass
        return prompts
    
    def get_all_resources(self) -> list[dict]:
        """Get resources from all active plugins."""
        resources = []
        for info in self.get_active_plugins():
            if info.instance:
                try:
                    resources.extend(info.instance.get_resources())
                except:
                    pass
        return resources


# Plugin utilities

def create_plugin_scaffold(name: str, path: Path) -> None:
    """Create a plugin scaffold."""
    plugin_dir = path / name
    plugin_dir.mkdir(parents=True, exist_ok=True)
    
    # Create manifest
    manifest = {
        "name": name,
        "version": "0.1.0",
        "description": "My awesome plugin",
        "author": "Your Name",
        "license": "MIT",
        "entry_point": "plugin.py",
        "dependencies": [],
        "permissions": [],
    }
    
    (plugin_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    
    # Create plugin.py
    plugin_code = '''"""Plugin for Agentic-AI."""

from src.infrastructure.plugins import PluginInterface, PluginInfo


class Plugin(PluginInterface):
    """Main plugin class."""
    
    def on_load(self) -> None:
        """Called when plugin loads."""
        print("Plugin loaded!")
    
    def on_activate(self) -> None:
        """Called when plugin activates."""
        print("Plugin activated!")
    
    def get_tools(self) -> list[dict]:
        """Return tools this plugin provides."""
        return [
            {
                "name": "my_tool",
                "description": "A tool provided by this plugin",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "arg1": {"type": "string"},
                    },
                },
            },
        ]
'''
    
    (plugin_dir / "plugin.py").write_text(plugin_code)
    
    # Create README
    readme = f"# {name}\n\nMy awesome plugin for Agentic-AI.\n\n## Installation\n\nPlace in `~/.config/agentic-ai/plugins/`\n\n## Usage\n\nSee plugin documentation.\n"
    
    (plugin_dir / "README.md").write_text(readme)


# Built-in plugins

class LoggingPlugin(PluginInterface):
    """Built-in logging plugin."""
    
    def get_tools(self) -> list[dict]:
        return [
            {
                "name": "log",
                "description": "Log a message",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "message": {"type": "string"},
                        "level": {"type": "string", "enum": ["debug", "info", "warning", "error"]},
                    },
                    "required": ["message"],
                },
            },
        ]
    
    async def execute_tool(self, name: str, args: dict) -> dict:
        """Execute a tool."""
        import logging
        
        level = getattr(logging, args.get("level", "info").upper())
        message = args["message"]
        
        logging.log(level, f"[Plugin] {message}")
        
        return {"success": True, "logged": message}
