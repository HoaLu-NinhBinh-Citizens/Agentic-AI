"""Watchdog — real-time file watching and auto-review.

Modules:
    file_watcher: Cross-platform file watcher with debouncing.
    auto_review: Auto-review service triggered by file changes.
"""

from .file_watcher import FileWatcher, WatchConfig, FileWatchEvent
from .auto_review import AutoReviewService

__all__ = [
    "FileWatcher",
    "WatchConfig",
    "FileWatchEvent",
    "AutoReviewService",
]
