"""File watcher for incremental indexing using watchdog."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event, Thread
from typing import Callable, Optional, Set

try:
    from watchdog.observers import Observer
    from watchdog.events import (
        FileSystemEventHandler,
        FileModifiedEvent,
        FileCreatedEvent,
        FileDeletedEvent,
    )

    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    Observer = None
    FileSystemEventHandler = object
    FileModifiedEvent = None
    FileCreatedEvent = None
    FileDeletedEvent = None


logger = logging.getLogger(__name__)


@dataclass
class FileChange:
    """Represents a file change event."""

    path: Path
    event_type: str  # 'created', 'modified', 'deleted'
    timestamp: float = field(default_factory=time.time)


class FileChangeHandler(FileSystemEventHandler):
    """Handler for file system events."""

    def __init__(self, callback: Callable[[FileChange], None], extensions: Set[str]):
        """Initialize handler.

        Args:
            callback: Function to call on file change
            extensions: File extensions to watch (e.g., {'.py', '.ts'})
        """
        super().__init__()
        self.callback = callback
        self.extensions = extensions
        self._debounce: dict[str, float] = {}
        self._debounce_seconds = 0.5  # Debounce rapid changes

    def on_modified(self, event):
        """Handle file modification."""
        if event.is_directory:
            return

        path = Path(event.src_path)
        if path.suffix in self.extensions:
            self._handle_change(path, "modified")

    def on_created(self, event):
        """Handle file creation."""
        if event.is_directory:
            return

        path = Path(event.src_path)
        if path.suffix in self.extensions:
            self._handle_change(path, "created")

    def on_deleted(self, event):
        """Handle file deletion."""
        if event.is_directory:
            return

        path = Path(event.src_path)
        if path.suffix in self.extensions:
            self._handle_change(path, "deleted")

    def _handle_change(self, path: Path, event_type: str):
        """Handle change with debouncing."""
        key = str(path)
        now = time.time()

        # Debounce rapid changes
        last = self._debounce.get(key, 0)
        if now - last < self._debounce_seconds:
            return

        self._debounce[key] = now

        change = FileChange(path=path, event_type=event_type)
        try:
            self.callback(change)
        except Exception as e:
            logger.error(f"Error handling file change: {e}")


class FileWatcher:
    """Watch files for changes and trigger incremental re-indexing.

    Uses watchdog to monitor file system changes and triggers
    re-indexing of changed files.
    """

    def __init__(
        self,
        workspace: Path,
        extensions: Optional[Set[str]] = None,
        on_change: Optional[Callable[[FileChange], None]] = None,
    ):
        """Initialize file watcher.

        Args:
            workspace: Root directory to watch
            extensions: File extensions to watch (default: common code files)
            on_change: Callback for file changes
        """
        self.workspace = Path(workspace)
        self.extensions = extensions or {
            ".py",
            ".js",
            ".ts",
            ".tsx",
            ".jsx",
            ".java",
            ".c",
            ".cpp",
            ".h",
            ".hpp",
            ".go",
            ".rs",
        }
        self.on_change = on_change

        self._observer: Optional[Observer] = None
        self._running = False
        self._thread: Optional[Thread] = None
        self._stop_event = Event()

        # Track changes for batch processing
        self._pending_changes: dict[str, FileChange] = {}
        self._batch_interval = 1.0  # Process changes every 1 second

    def start(self) -> bool:
        """Start watching files.

        Returns:
            True if started successfully
        """
        if not WATCHDOG_AVAILABLE:
            logger.warning("watchdog not installed. File watching disabled.")
            return False

        if self._running:
            logger.warning("File watcher already running")
            return True

        try:
            self._observer = Observer()
            handler = FileChangeHandler(self._on_file_change, self.extensions)
            self._observer.schedule(handler, str(self.workspace), recursive=True)
            self._observer.start()

            self._running = True
            self._stop_event.clear()

            logger.info(f"File watcher started for: {self.workspace}")
            return True

        except Exception as e:
            logger.error(f"Failed to start file watcher: {e}")
            return False

    def stop(self):
        """Stop watching files."""
        if not self._running:
            return

        self._stop_event.set()

        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None

        self._running = False
        logger.info("File watcher stopped")

    def _on_file_change(self, change: FileChange):
        """Handle file change event."""
        key = str(change.path)

        # For deleted files, process immediately
        if change.event_type == "deleted":
            self._process_change(change)
            self._pending_changes.pop(key, None)
            return

        # Track pending change for observers that poll get_pending_changes()
        self._pending_changes[key] = change

        # Process now: per-path debouncing already happened in
        # FileChangeHandler (0.5s window), so this does not storm on rapid
        # saves. Previously modified/created events were queued forever and
        # the on_change callback never fired for them.
        self._process_change(change)
        self._pending_changes.pop(key, None)

    def _process_change(self, change: FileChange):
        """Process a single file change."""
        if self.on_change:
            try:
                self.on_change(change)
                logger.debug(
                    f"Processed change: {change.path} ({change.event_type})"
                )
            except Exception as e:
                logger.error(f"Error processing change: {e}")

    def get_pending_changes(self) -> list[FileChange]:
        """Get all pending changes."""
        return list(self._pending_changes.values())

    def clear_pending(self):
        """Clear pending changes."""
        self._pending_changes.clear()

    @property
    def is_running(self) -> bool:
        """Check if watcher is running."""
        return self._running


class IncrementalIndexer:
    """Incremental indexer that reacts to file changes.

    Combines file watching with call graph updates for real-time indexing.
    """

    def __init__(self, workspace: Path):
        """Initialize incremental indexer.

        Args:
            workspace: Root directory to index
        """
        self.workspace = workspace
        self.watcher = FileWatcher(workspace, on_change=self._on_change)
        self._call_graph = None
        self._index_time_ms = 0.0

    def set_call_graph(self, call_graph):
        """Set call graph to update."""
        self._call_graph = call_graph

    def _on_change(self, change: FileChange):
        """Handle file change and update index."""
        start = time.time()

        if change.event_type == "deleted":
            self._remove_file(change.path)
        else:
            self._update_file(change.path)

        self._index_time_ms = (time.time() - start) * 1000
        logger.info(f"Indexed {change.path} in {self._index_time_ms:.1f}ms")

    def _update_file(self, path: Path):
        """Update index for a single file."""
        if not self._call_graph:
            return

        try:
            content = path.read_text(encoding="utf-8")
            self._call_graph.build_incremental(path, content)
        except Exception as e:
            logger.error(f"Failed to update index for {path}: {e}")

    def _remove_file(self, path: Path):
        """Remove file from index."""
        if not self._call_graph:
            return

        try:
            self._call_graph.clear_file(path)
        except Exception as e:
            logger.error(f"Failed to remove {path} from index: {e}")

    def start(self) -> bool:
        """Start incremental indexing."""
        return self.watcher.start()

    def stop(self):
        """Stop incremental indexing."""
        self.watcher.stop()

    @property
    def average_index_time_ms(self) -> float:
        """Get average index time per file."""
        return self._index_time_ms
