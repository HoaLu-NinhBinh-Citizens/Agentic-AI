"""Real-time file watcher for AI_SUPPORT.

Monitors code files and triggers callbacks on changes with debouncing
to avoid flooding on bulk operations.
"""

from __future__ import annotations

import asyncio
import fnmatch
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Awaitable

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


@dataclass
class WatchConfig:
    """Configuration for file watcher."""

    paths: list[Path]
    patterns: list[str]  # e.g. ["*.py", "*.c", "*.js"]
    debounce_ms: int = 2000  # Wait before re-triggering
    exclude_dirs: set[str] = field(default_factory=lambda: {
        ".git", "__pycache__", "node_modules", ".venv", "venv",
        "build", "dist", ".pytest_cache", ".mypy_cache",
    })
    exclude_files: set[str] = field(default_factory=lambda: {
        ".DS_Store", "thumbs.db", "*.pyc", "*.pyo",
    })


@dataclass
class FileWatchEvent:
    """Event representing a file change."""

    path: Path
    event_type: str  # "created", "modified", "deleted"
    timestamp: float = field(default_factory=time.time)


class FileWatcher:
    """Watch files and trigger callbacks on changes.

    Uses watchdog library for cross-platform file monitoring.
    Falls back to polling if watchdog is unavailable.

    Usage:
        config = WatchConfig(
            paths=[Path("src/")],
            patterns=["*.py", "*.c"],
            debounce_ms=2000,
        )
        watcher = FileWatcher(config, on_change_callback)
        await watcher.start()
    """

    def __init__(
        self,
        config: WatchConfig,
        callback: Callable[[list[FileWatchEvent]], Awaitable[None]],
    ):
        self.config = config
        self.callback = callback
        self._pending_events: dict[str, float] = {}  # path -> last_trigger
        self._running = False
        self._watch_task: asyncio.Task | None = None
        self._stop_event: asyncio.Event | None = None
        self._watchdog_observer = None

    async def start(self) -> None:
        """Start watching files. Non-blocking."""
        self._running = True
        self._stop_event = asyncio.Event()
        self._watch_task = asyncio.create_task(self._run_watcher())
        logger.info("file_watcher_started", paths=[str(p) for p in self.config.paths])

    async def stop(self) -> None:
        """Stop watching files."""
        self._running = False
        if self._stop_event:
            self._stop_event.set()
        if self._watchdog_observer:
            self._watchdog_observer.stop()
            self._watchdog_observer.join(timeout=5)
            self._watchdog_observer = None
        if self._watch_task:
            self._watch_task.cancel()
            try:
                await self._watch_task
            except asyncio.CancelledError:
                pass
            self._watch_task = None
        logger.info("file_watcher_stopped")

    def _filter_events(self, events: list[FileWatchEvent]) -> list[FileWatchEvent]:
        """Debounce: only keep events after debounce period."""
        now = time.time()
        debounce_s = self.config.debounce_ms / 1000
        filtered = []
        for event in events:
            path_str = str(event.path)
            last = self._pending_events.get(path_str, 0)
            if now - last >= debounce_s:
                self._pending_events[path_str] = now
                filtered.append(event)
            else:
                logger.debug(
                    "event_debounced",
                    path=path_str,
                    waited_ms=int((now - last) * 1000),
                    debounce_ms=self.config.debounce_ms,
                )
        return filtered

    def _should_watch(self, path: Path) -> bool:
        """Check if path matches watch patterns and should be monitored."""
        # Check exclude directories
        for part in path.parts:
            if part in self.config.exclude_dirs:
                return False

        # Check exclude files
        for pattern in self.config.exclude_files:
            if fnmatch.fnmatch(path.name, pattern):
                return False

        # Check include patterns
        for pattern in self.config.patterns:
            if fnmatch.fnmatch(path.name, pattern):
                return True

        return False

    async def _run_watcher(self) -> None:
        """Main watcher loop using watchdog."""
        try:
            from watchdog.observers import Observer
            from watchdog.events import (
                FileSystemEventHandler,
                FileCreatedEvent,
                FileModifiedEvent,
                FileDeletedEvent,
            )
        except ImportError:
            logger.warning("watchdog_not_available_using_polling")
            await self._run_polling()
            return

        event_queue: asyncio.Queue[FileWatchEvent] = asyncio.Queue()
        events_batch: list[FileWatchEvent] = []
        batch_lock = asyncio.Lock()

        class Handler(FileSystemEventHandler):
            def on_created(self, event):
                if not event.is_directory:
                    path = Path(event.src_path)
                    if self._should_watch(path):
                        event_queue.put_nowait(FileWatchEvent(path, "created"))

            def on_modified(self, event):
                if not event.is_directory:
                    path = Path(event.src_path)
                    if self._should_watch(path):
                        event_queue.put_nowait(FileWatchEvent(path, "modified"))

            def on_deleted(self, event):
                if not event.is_directory:
                    path = Path(event.src_path)
                    if self._should_watch(path):
                        event_queue.put_nowait(FileWatchEvent(path, "deleted"))

            _should_watch = self._should_watch  # Bind method

        handler = Handler()
        observer = Observer()

        for watch_path in self.config.paths:
            if watch_path.exists():
                observer.schedule(handler, str(watch_path), recursive=True)
                logger.info("watching_path", path=str(watch_path))
            else:
                logger.warning("watch_path_not_found", path=str(watch_path))

        observer.start()
        self._watchdog_observer = observer

        batch_interval = self.config.debounce_ms / 1000 / 2

        try:
            while self._running:
                try:
                    event = await asyncio.wait_for(
                        event_queue.get(),
                        timeout=batch_interval,
                    )
                    events_batch.append(event)

                    # Collect more events within the batch interval
                    while not event_queue.empty():
                        try:
                            event = event_queue.get_nowait()
                            events_batch.append(event)
                        except asyncio.QueueEmpty:
                            break

                    # Filter and trigger callback
                    filtered = self._filter_events(events_batch)
                    if filtered:
                        await self.callback(filtered)
                    events_batch.clear()

                except asyncio.TimeoutError:
                    # Process remaining batch on timeout
                    if events_batch:
                        filtered = self._filter_events(events_batch)
                        if filtered:
                            await self.callback(filtered)
                        events_batch.clear()

        except asyncio.CancelledError:
            observer.stop()
            raise

    async def _run_polling(self) -> None:
        """Fallback polling watcher when watchdog is unavailable."""
        file_mtimes: dict[str, float] = {}

        while self._running:
            try:
                for watch_path in self.config.paths:
                    if not watch_path.exists():
                        continue

                    for path in watch_path.rglob("*"):
                        if not path.is_file():
                            continue
                        if not self._should_watch(path):
                            continue

                        path_str = str(path)
                        try:
                            mtime = path.stat().st_mtime
                            old_mtime = file_mtimes.get(path_str)

                            if old_mtime is None:
                                # New file
                                file_mtimes[path_str] = mtime
                                event = FileWatchEvent(path, "created")
                                filtered = self._filter_events([event])
                                if filtered:
                                    await self.callback(filtered)
                            elif mtime > old_mtime:
                                # Modified
                                file_mtimes[path_str] = mtime
                                event = FileWatchEvent(path, "modified")
                                filtered = self._filter_events([event])
                                if filtered:
                                    await self.callback(filtered)

                        except OSError:
                            pass

                await asyncio.sleep(1)

            except asyncio.CancelledError:
                break
