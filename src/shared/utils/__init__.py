"""Shared utils module."""

import hashlib
from typing import Any


def generate_id(data: str) -> str:
    """Generate unique ID from data."""
    return hashlib.sha256(data.encode()).hexdigest()[:16]


def merge_dicts(base: dict, update: dict) -> dict:
    """Merge two dictionaries."""
    result = base.copy()
    result.update(update)
    return result
