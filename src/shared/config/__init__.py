"""Shared config module."""

from pathlib import Path
from typing import Any
import json


def load_config(path: str = "config.yaml") -> dict[str, Any]:
    """Load configuration from file."""
    config_path = Path(path)
    if config_path.exists():
        if config_path.suffix == ".json":
            return json.loads(config_path.read_text())
    return {}


def save_config(config: dict[str, Any], path: str = "config.yaml") -> None:
    """Save configuration to file."""
    config_path = Path(path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, indent=2))
