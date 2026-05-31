"""Plugin discovery and management system for AI_SUPPORT."""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Type

logger = logging.getLogger(__name__)


@dataclass
class PluginManifest:
    """Plugin manifest containing metadata."""
    name: str
    version: str
    description: str
    author: str
    main: str
    entry_point: str
    dependencies: List[str] = field(default_factory=list)
    permissions: List[str] = field(default_factory=list)
    min_ai_support_version: str = "1.0.0"
    hooks: List[str] = field(default_factory=list)


@dataclass
class Plugin:
    """A loaded plugin instance."""
    manifest: PluginManifest
    module: Any
    path: Path
    enabled: bool = True
    loaded_at: Optional[str] = None
    checksum: Optional[str] = None


class PluginHook:
    """Base class for plugin hooks."""

    @staticmethod
    def on_review_start(context: Dict) -> Dict:
        """Called before review starts."""
        return context

    @staticmethod
    def on_review_complete(results: Dict) -> Dict:
        """Called after review completes."""
        return results

    @staticmethod
    def on_finding_found(finding: Dict) -> Optional[Dict]:
        """Called when a finding is detected. Return None to skip."""
        return finding

    @staticmethod
    def on_fix_applied(fix: Dict) -> Dict:
        """Called when a fix is applied."""
        return fix


class PluginDiscovery:
    """Discover and load plugins from directories.

    Plugins are discovered from:
    1. .ai_support/plugins/ (user plugins)
    2. Built-in plugins/
    """

    PLUGIN_DIRS = [
        Path.home() / ".ai_support" / "plugins",
        Path(".ai_support") / "plugins",
        Path("plugins"),
    ]

    def __init__(self, workspace: Optional[Path] = None):
        """Initialize plugin discovery.

        Args:
            workspace: Workspace root for finding plugins
        """
        self.workspace = workspace or Path.cwd()
        self._plugins: Dict[str, Plugin] = {}
        self._hooks: Dict[str, List[Callable]] = {
            'on_review_start': [],
            'on_review_complete': [],
            'on_finding_found': [],
            'on_fix_applied': [],
        }

    def discover(self) -> List[Plugin]:
        """Discover all available plugins.

        Returns:
            List of discovered plugins
        """
        plugins = []

        for plugin_dir in self.PLUGIN_DIRS:
            # Try relative to workspace
            if not plugin_dir.is_absolute():
                plugin_dir = self.workspace / plugin_dir

            if plugin_dir.exists() and plugin_dir.is_dir():
                found = self._discover_from_dir(plugin_dir)
                plugins.extend(found)

        logger.info("Discovered %d plugins", len(plugins))
        return plugins

    def _discover_from_dir(self, plugin_dir: Path) -> List[Plugin]:
        """Discover plugins from a directory.

        Args:
            plugin_dir: Directory to search

        Returns:
            List of discovered plugins
        """
        plugins = []

        for entry in plugin_dir.iterdir():
            if not entry.is_dir():
                continue

            manifest_file = entry / "plugin.json"
            if not manifest_file.exists():
                continue

            try:
                plugin = self._load_plugin(entry)
                if plugin and self._validate_plugin(plugin):
                    plugins.append(plugin)
                    self._plugins[plugin.manifest.name] = plugin
                    self._register_hooks(plugin)
                    logger.debug("Loaded plugin: %s", plugin.manifest.name)
            except Exception as e:
                logger.error("Failed to load plugin %s: %s", entry, e)

        return plugins

    def _load_plugin(self, path: Path) -> Optional[Plugin]:
        """Load a plugin from directory.

        Args:
            path: Plugin directory path

        Returns:
            Loaded plugin or None
        """
        manifest_file = path / "plugin.json"

        with open(manifest_file, 'r', encoding='utf-8') as f:
            manifest_data = json.load(f)

        manifest = PluginManifest(**manifest_data)

        # Load main module
        main_file = path / manifest.main

        if not main_file.exists():
            logger.error("Plugin main file not found: %s", main_file)
            return None

        # Dynamically import module
        spec = importlib.util.spec_from_file_location(
            f"plugin_{manifest.name}",
            main_file
        )

        if not spec or not spec.loader:
            return None

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Calculate checksum
        with open(main_file, 'rb') as f:
            checksum = hashlib.sha256(f.read()).hexdigest()[:16]

        plugin = Plugin(
            manifest=manifest,
            module=module,
            path=path,
            checksum=checksum,
        )

        return plugin

    def _validate_plugin(self, plugin: Plugin) -> bool:
        """Validate a plugin against requirements.

        Args:
            plugin: Plugin to validate

        Returns:
            True if valid
        """
        # Check version compatibility
        min_version = plugin.manifest.min_ai_support_version
        current_version = self._get_ai_support_version()

        if not self._version_compatible(current_version, min_version):
            logger.warning(
                "Plugin %s requires AI_SUPPORT >= %s, but current version is %s",
                plugin.manifest.name, min_version, current_version
            )
            return False

        # Check dependencies
        for dep in plugin.manifest.dependencies:
            if not self._check_dependency(dep):
                logger.warning(
                    "Plugin %s missing dependency: %s",
                    plugin.manifest.name, dep
                )
                return False

        return True

    def _check_dependency(self, dep: str) -> bool:
        """Check if a dependency is available.

        Args:
            dep: Dependency name (e.g., 'numpy>=1.20')

        Returns:
            True if available
        """
        try:
            name = dep.split('>')[0].split('<')[0].split('=')[0].strip()
            importlib.import_module(name)
            return True
        except ImportError:
            return False

    def _version_compatible(self, current: str, required: str) -> bool:
        """Check if versions are compatible.

        Args:
            current: Current version
            required: Required version

        Returns:
            True if compatible
        """
        # Simplified version check
        try:
            cur_parts = [int(x) for x in current.split('.')[:2]]
            req_parts = [int(x) for x in required.split('.')[:2]]

            return cur_parts >= req_parts
        except (ValueError, IndexError):
            return True  # Assume compatible if can't parse

    def _get_ai_support_version(self) -> str:
        """Get current AI_SUPPORT version."""
        try:
            from src import __version__
            return __version__
        except ImportError:
            return "1.0.0"

    def _register_hooks(self, plugin: Plugin) -> None:
        """Register plugin hooks.

        Args:
            plugin: Plugin with hooks to register
        """
        for hook_name in plugin.manifest.hooks:
            if hasattr(plugin.module, hook_name):
                hook_func = getattr(plugin.module, hook_name)
                if hook_name in self._hooks:
                    self._hooks[hook_name].append(hook_func)

    def enable(self, name: str) -> bool:
        """Enable a plugin by name.

        Args:
            name: Plugin name

        Returns:
            True if enabled
        """
        if name in self._plugins:
            self._plugins[name].enabled = True
            return True
        return False

    def disable(self, name: str) -> bool:
        """Disable a plugin by name.

        Args:
            name: Plugin name

        Returns:
            True if disabled
        """
        if name in self._plugins:
            self._plugins[name].enabled = False
            return True
        return False

    def list_plugins(self) -> List[Plugin]:
        """List all loaded plugins."""
        return list(self._plugins.values())

    def get_plugin(self, name: str) -> Optional[Plugin]:
        """Get a plugin by name."""
        return self._plugins.get(name)

    def execute_hook(self, hook_name: str, data: Any) -> Any:
        """Execute a hook with all enabled plugins.

        Args:
            hook_name: Name of hook to execute
            data: Data to pass to hook

        Returns:
            Modified data after all hooks run
        """
        if hook_name not in self._hooks:
            return data

        result = data
        for hook in self._hooks[hook_name]:
            try:
                result = hook(result)
            except Exception as e:
                logger.error("Hook %s failed: %s", hook_name, e)

        return result


class PluginRegistry:
    """Registry for built-in and user rule types."""

    _rules: Dict[str, Type] = {}
    _formatters: Dict[str, Type] = {}
    _detectors: Dict[str, Type] = {}

    @classmethod
    def register_rule(cls, name: str, rule_class: Type) -> None:
        """Register a rule type.

        Args:
            name: Rule identifier
            rule_class: Rule class
        """
        cls._rules[name] = rule_class

    @classmethod
    def register_formatter(cls, name: str, formatter_class: Type) -> None:
        """Register a formatter type.

        Args:
            name: Formatter identifier
            formatter_class: Formatter class
        """
        cls._formatters[name] = formatter_class

    @classmethod
    def register_detector(cls, name: str, detector_class: Type) -> None:
        """Register a detector type.

        Args:
            name: Detector identifier
            detector_class: Detector class
        """
        cls._detectors[name] = detector_class

    @classmethod
    def get_rule(cls, name: str) -> Optional[Type]:
        """Get a rule class by name."""
        return cls._rules.get(name)

    @classmethod
    def get_formatter(cls, name: str) -> Optional[Type]:
        """Get a formatter class by name."""
        return cls._formatters.get(name)

    @classmethod
    def get_detector(cls, name: str) -> Optional[Type]:
        """Get a detector class by name."""
        return cls._detectors.get(name)
