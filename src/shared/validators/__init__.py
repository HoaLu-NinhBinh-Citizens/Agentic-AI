"""Shared validators module."""

from typing import Any


def validate_task_input(task: dict[str, Any]) -> bool:
    """Validate task input."""
    if not isinstance(task, dict):
        return False
    if "description" not in task:
        return False
    return True


def validate_config(config: dict[str, Any]) -> bool:
    """Validate configuration."""
    if not isinstance(config, dict):
        return False
    return True
