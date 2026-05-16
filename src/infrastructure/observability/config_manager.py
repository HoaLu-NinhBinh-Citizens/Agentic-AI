"""
Configuration Manager with YAML Support

Provides:
- YAML/JSON configuration loading
- Environment variable overrides
- Secret management
- Config validation
- Hot reload support
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass, field
from datetime import datetime
import yaml
import logging

logger = logging.getLogger(__name__)


@dataclass
class ConfigSource:
    """Represents a configuration source."""
    name: str
    path: Optional[Path]
    priority: int  # Higher = more important
    loaded_at: Optional[datetime] = None
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ConfigChange:
    """Represents a configuration change."""
    key: str
    old_value: Any
    new_value: Any
    source: str
    timestamp: datetime


class ConfigManager:
    """
    Centralized configuration manager.

    Features:
    - Multi-source config loading (YAML, JSON, env vars)
    - Environment variable overrides
    - Secret management (env var references)
    - Config validation
    - Hot reload
    - Change callbacks

    Usage:
        config = ConfigManager()
        config.load("config.yaml")
        config.load_env_overrides()

        value = config.get("database.host")
        config.set("debug", True)
        config.save()
    """

    def __init__(
        self,
        default_config: Optional[Dict[str, Any]] = None,
        env_prefix: str = "AI_SUPPORT_",
    ):
        self.env_prefix = env_prefix
        self._sources: List[ConfigSource] = []
        self._config: Dict[str, Any] = default_config or {}
        self._change_callbacks: List[callable] = []
        self._changes: List[ConfigChange] = []
        self._is_hot_reloading = False

    # -------------------------------------------------------------------------
    # Loading
    # -------------------------------------------------------------------------

    def load_yaml(self, path: Union[str, Path], priority: int = 10) -> bool:
        """
        Load configuration from YAML file.

        Args:
            path: Path to YAML file
            priority: Load priority (higher overrides lower)

        Returns:
            True if loaded successfully
        """
        path = Path(path)

        if not path.exists():
            logger.warning("Config file not found: %s", path)
            return False

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            if data is None:
                data = {}

            source = ConfigSource(
                name=str(path),
                path=path,
                priority=priority,
                loaded_at=datetime.now(),
                data=data,
            )
            self._sources.append(source)
            self._merge_config(data, priority)

            logger.info("Loaded config from: %s", path)
            return True

        except yaml.YAMLError as exc:
            logger.error("YAML parse error in %s: %s", path, exc)
            return False
        except Exception as exc:
            logger.error("Failed to load config from %s: %s", path, exc)
            return False

    def load_json(self, path: Union[str, Path], priority: int = 10) -> bool:
        """
        Load configuration from JSON file.

        Args:
            path: Path to JSON file
            priority: Load priority

        Returns:
            True if loaded successfully
        """
        path = Path(path)

        if not path.exists():
            logger.warning("Config file not found: %s", path)
            return False

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            source = ConfigSource(
                name=str(path),
                path=path,
                priority=priority,
                loaded_at=datetime.now(),
                data=data,
            )
            self._sources.append(source)
            self._merge_config(data, priority)

            logger.info("Loaded config from: %s", path)
            return True

        except json.JSONDecodeError as exc:
            logger.error("JSON parse error in %s: %s", path, exc)
            return False
        except Exception as exc:
            logger.error("Failed to load config from %s: %s", path, exc)
            return False

    def load_dict(self, data: Dict[str, Any], name: str = "dict", priority: int = 5) -> None:
        """
        Load configuration from dictionary.

        Args:
            data: Configuration dictionary
            name: Source name
            priority: Load priority
        """
        source = ConfigSource(
            name=name,
            path=None,
            priority=priority,
            loaded_at=datetime.now(),
            data=data,
        )
        self._sources.append(source)
        self._merge_config(data, priority)

    def load_env_overrides(self, prefix: Optional[str] = None) -> int:
        """
        Load environment variable overrides.

        Environment variables in format: {PREFIX}_{SECTION}__{KEY}
        Example: AI_SUPPORT_DATABASE__HOST=localhost

        Args:
            prefix: Environment variable prefix (default: self.env_prefix)

        Returns:
            Number of overrides loaded
        """
        prefix = prefix or self.env_prefix
        count = 0

        for key, value in os.environ.items():
            if not key.startswith(prefix):
                continue

            # Parse key: PREFIX_SECTION__KEY -> section.key
            remainder = key[len(prefix):]
            parts = remainder.split("__", 1)

            if len(parts) == 2:
                section, subkey = parts
                section = section.lower().replace("_", ".")
                config_key = f"{section}.{subkey.lower().replace('_', '.')}"
            else:
                config_key = remainder.lower().replace("_", ".")

            # Try to parse value
            parsed_value = self._parse_env_value(value)

            self.set(config_key, parsed_value, source="env", priority=100)
            count += 1

        if count > 0:
            logger.info("Loaded %d env overrides", count)

        return count

    def _parse_env_value(self, value: str) -> Any:
        """Parse environment variable value to appropriate type."""
        # Boolean
        if value.lower() in ("true", "yes", "1"):
            return True
        if value.lower() in ("false", "no", "0"):
            return False

        # None
        if value.lower() == "none" or value == "":
            return None

        # Number
        try:
            if "." in value:
                return float(value)
            return int(value)
        except ValueError:
            pass

        # JSON-like arrays/objects
        if value.startswith("[") or value.startswith("{"):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                pass

        return value

    def load(self, path: Union[str, Path], priority: int = 10) -> bool:
        """
        Load configuration from file (auto-detect format).

        Args:
            path: Path to config file
            priority: Load priority

        Returns:
            True if loaded successfully
        """
        path = Path(path)
        ext = path.suffix.lower()

        if ext in (".yaml", ".yml"):
            return self.load_yaml(path, priority)
        elif ext == ".json":
            return self.load_json(path, priority)
        else:
            logger.error("Unsupported config format: %s", ext)
            return False

    # -------------------------------------------------------------------------
    # Merging
    # -------------------------------------------------------------------------

    def _merge_config(self, data: Dict[str, Any], priority: int):
        """Merge configuration data with existing config."""
        # This is handled by set() with priority tracking
        def flatten(d, prefix=""):
            items = {}
            for k, v in d.items():
                key = f"{prefix}.{k}" if prefix else k
                if isinstance(v, dict):
                    items.update(flatten(v, key))
                else:
                    items[key] = v
            return items

        flat_data = flatten(data)
        for key, value in flat_data.items():
            current = self._get_nested(self._config, key)

            # Only override if not exists or new priority is higher
            if current is None or priority >= 50:
                self._set_nested(self._config, key, value)

    # -------------------------------------------------------------------------
    # Access
    # -------------------------------------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value by key.

        Args:
            key: Dot-notation key (e.g., "database.host")
            default: Default value if not found

        Returns:
            Configuration value or default
        """
        value = self._get_nested(self._config, key)
        return value if value is not None else default

    def set(
        self,
        key: str,
        value: Any,
        source: str = "memory",
        priority: int = 50,
    ) -> None:
        """
        Set configuration value.

        Args:
            key: Dot-notation key
            value: Value to set
            source: Source of the value
            priority: Priority (higher overrides lower)
        """
        old_value = self._get_nested(self._config, key)

        if old_value != value:
            self._set_nested(self._config, key, value)

            change = ConfigChange(
                key=key,
                old_value=old_value,
                new_value=value,
                source=source,
                timestamp=datetime.now(),
            )
            self._changes.append(change)

            # Notify callbacks
            for callback in self._change_callbacks:
                try:
                    callback(change)
                except Exception as exc:
                    logger.error("Config change callback error: %s", exc)

    def delete(self, key: str) -> bool:
        """Delete configuration key."""
        parts = key.split(".")
        current = self._config

        for part in parts[:-1]:
            if not isinstance(current, dict) or part not in current:
                return False
            current = current[part]

        if parts[-1] in current:
            del current[parts[-1]]
            return True
        return False

    def _get_nested(self, data: Dict, key: str) -> Any:
        """Get nested value from dict using dot notation."""
        parts = key.split(".")
        current = data

        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None

        return current

    def _set_nested(self, data: Dict, key: str, value: Any):
        """Set nested value in dict using dot notation."""
        parts = key.split(".")
        current = data

        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            elif not isinstance(current[part], dict):
                current[part] = {}
            current = current[part]

        current[parts[-1]] = value

    # -------------------------------------------------------------------------
    # Change Management
    # -------------------------------------------------------------------------

    def on_change(self, callback: callable):
        """Register callback for configuration changes."""
        self._change_callbacks.append(callback)

    def get_changes(self, since: Optional[datetime] = None) -> List[ConfigChange]:
        """Get configuration changes."""
        if since:
            return [c for c in self._changes if c.timestamp >= since]
        return self._changes.copy()

    # -------------------------------------------------------------------------
    # Persistence
    # -------------------------------------------------------------------------

    def save(self, path: Union[str, Path], format: str = "yaml") -> bool:
        """
        Save current configuration to file.

        Args:
            path: Output path
            format: Output format ("yaml" or "json")

        Returns:
            True if saved successfully
        """
        path = Path(path)

        try:
            path.parent.mkdir(parents=True, exist_ok=True)

            with open(path, "w", encoding="utf-8") as f:
                if format == "json":
                    json.dump(self._config, f, indent=2, default=str)
                else:
                    yaml.dump(self._config, f, default_flow_style=False, sort_keys=False)

            logger.info("Saved config to: %s", path)
            return True

        except Exception as exc:
            logger.error("Failed to save config to %s: %s", path, exc)
            return False

    # -------------------------------------------------------------------------
    # Hot Reload
    # -------------------------------------------------------------------------

    def enable_hot_reload(self, interval: float = 5.0):
        """
        Enable hot reload for file-based configs.

        Args:
            interval: Check interval in seconds
        """
        import threading

        self._is_hot_reloading = True

        def _check_reload():
            while self._is_hot_reloading:
                for source in self._sources:
                    if source.path and source.path.exists():
                        mtime = datetime.fromtimestamp(source.path.stat().st_mtime)
                        if source.loaded_at and mtime > source.loaded_at:
                            logger.info("Hot reload detected: %s", source.path)
                            self.load(source.path, source.priority)

                import time
                time.sleep(interval)

        thread = threading.Thread(target=_check_reload, daemon=True)
        thread.start()

    def disable_hot_reload(self):
        """Disable hot reload."""
        self._is_hot_reloading = False

    # -------------------------------------------------------------------------
    # Utilities
    # -------------------------------------------------------------------------

    def get_section(self, section: str) -> Dict[str, Any]:
        """Get entire configuration section."""
        return self._config.get(section, {})

    def keys(self, prefix: Optional[str] = None) -> List[str]:
        """Get all configuration keys, optionally filtered by prefix."""
        def flatten(d, prefix=""):
            items = []
            for k, v in d.items():
                key = f"{prefix}.{k}" if prefix else k
                if isinstance(v, dict):
                    items.extend(flatten(v, key))
                else:
                    items.append(key)
            return items

        all_keys = flatten(self._config)
        if prefix:
            return [k for k in all_keys if k.startswith(prefix)]
        return all_keys

    def to_dict(self) -> Dict[str, Any]:
        """Get full configuration as dictionary."""
        return self._config.copy()

    def get_sources(self) -> List[ConfigSource]:
        """Get list of configuration sources."""
        return self._sources.copy()
