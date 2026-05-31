"""Tests for file watcher."""

import pytest
import time
from pathlib import Path

from src.infrastructure.indexing.file_watcher import (
    FileWatcher,
    FileChange,
    IncrementalIndexer,
    WATCHDOG_AVAILABLE,
)


class TestFileChange:
    """Tests for FileChange."""

    def test_create_file_change(self):
        """Should create file change with correct attributes."""
        path = Path("test.py")
        change = FileChange(path=path, event_type="modified")

        assert change.path == path
        assert change.event_type == "modified"
        assert change.timestamp > 0

    def test_file_change_with_timestamp(self):
        """Should accept custom timestamp."""
        ts = 1234567890.0
        path = Path("test.py")
        change = FileChange(path=path, event_type="created", timestamp=ts)

        assert change.timestamp == ts

    def test_file_change_event_types(self):
        """Should support all event types."""
        path = Path("test.py")

        for event_type in ("created", "modified", "deleted"):
            change = FileChange(path=path, event_type=event_type)
            assert change.event_type == event_type


class TestFileWatcher:
    """Tests for FileWatcher."""

    def test_initialization(self, tmp_path):
        """Should initialize with correct defaults."""
        watcher = FileWatcher(tmp_path)

        assert watcher.workspace == tmp_path
        assert ".py" in watcher.extensions

    def test_extensions_filter(self, tmp_path):
        """Should only watch specified extensions."""
        extensions = {".py"}
        watcher = FileWatcher(tmp_path, extensions=extensions)

        assert watcher.extensions == extensions

    def test_custom_extensions(self, tmp_path):
        """Should accept custom extensions."""
        extensions = {".ts", ".tsx", ".jsx"}
        watcher = FileWatcher(tmp_path, extensions=extensions)

        assert watcher.extensions == extensions
        assert ".ts" in watcher.extensions
        assert ".tsx" in watcher.extensions
        assert ".jsx" in watcher.extensions

    def test_default_extensions_include_common(self, tmp_path):
        """Default extensions should include common code files."""
        watcher = FileWatcher(tmp_path)

        expected = {".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".c", ".cpp", ".h", ".hpp", ".go", ".rs"}
        for ext in expected:
            assert ext in watcher.extensions

    def test_not_running_initially(self, tmp_path):
        """Should not be running on init."""
        watcher = FileWatcher(tmp_path)

        assert watcher.is_running is False

    def test_on_change_callback(self, tmp_path):
        """Should store on_change callback."""
        callback_called = []

        def callback(change):
            callback_called.append(change)

        watcher = FileWatcher(tmp_path, on_change=callback)
        assert watcher.on_change is callback

    def test_get_pending_changes_empty(self, tmp_path):
        """Should return empty list initially."""
        watcher = FileWatcher(tmp_path)

        changes = watcher.get_pending_changes()
        assert changes == []

    def test_clear_pending(self, tmp_path):
        """Should clear pending changes."""
        watcher = FileWatcher(tmp_path)
        watcher._pending_changes["test.py"] = FileChange(
            path=Path("test.py"), event_type="modified"
        )

        watcher.clear_pending()

        assert watcher.get_pending_changes() == []


class TestFileWatcherStartStop:
    """Tests for FileWatcher start/stop lifecycle."""

    def test_start_without_watchdog(self, tmp_path, monkeypatch):
        """Should handle missing watchdog gracefully."""
        # Force watchdog unavailable
        import src.infrastructure.indexing.file_watcher as fw

        monkeypatch.setattr(fw, "WATCHDOG_AVAILABLE", False)

        watcher = FileWatcher(tmp_path)
        result = watcher.start()

        assert result is False
        assert watcher.is_running is False

    def test_stop_when_not_running(self, tmp_path):
        """Should handle stop when not running."""
        watcher = FileWatcher(tmp_path)

        # Should not raise
        watcher.stop()

        assert watcher.is_running is False

    @pytest.mark.skipif(not WATCHDOG_AVAILABLE, reason="watchdog not available")
    def test_start_stop_cycle(self, tmp_path):
        """Should start and stop successfully."""
        watcher = FileWatcher(tmp_path)

        started = watcher.start()
        assert started is True
        assert watcher.is_running is True

        watcher.stop()
        assert watcher.is_running is False


class TestIncrementalIndexer:
    """Tests for IncrementalIndexer."""

    def test_initialization(self, tmp_path):
        """Should initialize with workspace."""
        indexer = IncrementalIndexer(tmp_path)

        assert indexer.workspace == tmp_path
        assert isinstance(indexer.watcher, FileWatcher)

    def test_set_call_graph(self, tmp_path):
        """Should set call graph."""
        indexer = IncrementalIndexer(tmp_path)

        class MockGraph:
            pass

        graph = MockGraph()
        indexer.set_call_graph(graph)

        assert indexer._call_graph is graph

    def test_average_index_time_initially_zero(self, tmp_path):
        """Should have zero average index time initially."""
        indexer = IncrementalIndexer(tmp_path)

        assert indexer.average_index_time_ms == 0.0

    def test_watcher_workspace(self, tmp_path):
        """Should use same workspace as indexer."""
        indexer = IncrementalIndexer(tmp_path)

        assert indexer.watcher.workspace == tmp_path


class TestIncrementalIndexerStartStop:
    """Tests for IncrementalIndexer start/stop lifecycle."""

    def test_stop_when_not_started(self, tmp_path):
        """Should handle stop when not started."""
        indexer = IncrementalIndexer(tmp_path)

        # Should not raise
        indexer.stop()

    @pytest.mark.skipif(not WATCHDOG_AVAILABLE, reason="watchdog not available")
    def test_start_stop_cycle(self, tmp_path):
        """Should start and stop successfully."""
        indexer = IncrementalIndexer(tmp_path)

        started = indexer.start()
        assert started is True
        assert indexer.watcher.is_running is True

        indexer.stop()
        assert indexer.watcher.is_running is False


class TestWatchdogAvailability:
    """Tests for watchdog availability detection."""

    def test_watchdog_available_flag(self):
        """Should expose watchdog availability."""
        # The flag should be a boolean
        assert isinstance(WATCHDOG_AVAILABLE, bool)

    def test_watchdog_available_types(self):
        """WATCHDOG_AVAILABLE should be True or False."""
        assert WATCHDOG_AVAILABLE in (True, False)
