"""Shared hashing utilities for incremental indexing.

Provides deterministic content hashing to detect file changes
regardless of filesystem timestamp resolution.
"""

from __future__ import annotations

import hashlib
from pathlib import Path


def compute_content_hash(content: str) -> str:
    """Compute SHA256 hash of a content string.

    Args:
        content: String content to hash.

    Returns:
        64-character hexadecimal hash string.
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def compute_file_hash(file_path: str | Path) -> str:
    """Compute SHA256 hash of file content.

    Reads file as text with UTF-8 encoding to ensure consistency
    with compute_content_hash (handles CRLF normalization on Windows).

    Args:
        file_path: Path to file to hash.

    Returns:
        64-character hexadecimal hash string, or empty string if file
        cannot be read.
    """
    try:
        path = Path(file_path)
        return compute_content_hash(path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return ""


def compute_short_hash(content: str) -> str:
    """Compute a shortened (24-char) SHA256 hash for storage efficiency.

    Useful for SQLite state tracking where full hashes are overkill.

    Args:
        content: String content to hash.

    Returns:
        24-character hexadecimal hash string.
    """
    return hashlib.sha256(content.encode()).hexdigest()[:24]
