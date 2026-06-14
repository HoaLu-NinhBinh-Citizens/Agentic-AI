"""
Tests for Runtime Kernel Module

Tests RuntimeController, EventJournal, DeadLetterQueue, and EventReplayer.
"""

import pytest
import asyncio
import tempfile
import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

from src.core.runtime.controller import (
    RuntimeController,
    RuntimeState,
    LifecycleEvent,
)
from src.core.runtime.journal import (
    EventJournal,
    JournalEntry,
    JournalPartition,
    PartitionStrategy,
)
from src.core.runtime.dlq import (
    DeadLetterQueue,
    DLQEntry,
    DLQReason,
    DLQStatus,
)
from src.core.runtime.replayer import (
    EventReplayer,
    ReplayFilter,
    ReplayResult,
)


# =============================================================================
# RuntimeController Tests
# =============================================================================

class TestRuntimeState:
    """Test RuntimeState enum."""

    def test_all_states_exist(self):
        """Test all expected states exist."""
        assert RuntimeState.BOOT.value == "boot"
        assert RuntimeState.INIT.value == "init"
        assert RuntimeState.READY.value == "ready"
        assert RuntimeState.PLANNING.value == "planning"
        assert RuntimeState.EXECUTING.value == "executing"
        assert RuntimeState.VALIDATING.value == "validating"
        assert RuntimeState.RECOVERING.value == "recovering"
        assert RuntimeState.DONE.value == "done"
        assert RuntimeState.FAILED.value == "failed"


class TestLifecycleEvent:
    """Test LifecycleEvent enum."""

    def test_lifecycle_events_exist(self):
        """Test lifecycle events exist."""
        assert LifecycleEvent.BOOT_STARTED.value == "boot_started"
        assert LifecycleEvent.INIT_COMPLETED.value == "init_completed"
        assert LifecycleEvent.TASK_COMPLETED.value == "task_completed"
        assert LifecycleEvent.ERROR_OCCURRED.value == "error_occurred"


class TestRuntimeController:
    """Test RuntimeController functionality."""

    @pytest.fixture
    def controller(self):
        """Create a RuntimeController for testing."""
        return RuntimeController(name="test_runtime")

    def test_controller_initialization(self, controller):
        """Test controller initializes correctly."""
        assert controller.name == "test_runtime"
        assert controller.state == RuntimeState.BOOT
        assert not controller.is_running

    @pytest.mark.asyncio
    async def test_boot(self, controller):
        """Test boot transitions to INIT."""
        result = await controller.boot()
        assert result is True
        assert controller.state == RuntimeState.INIT
        assert controller.is_running

    @pytest.mark.asyncio
    async def test_initialize(self, controller):
        """Test initialize transitions to READY."""
        await controller.boot()
        result = await controller.initialize()
        assert result is True
        assert controller.state == RuntimeState.READY

    @pytest.mark.asyncio
    async def test_lifecycle_flow(self, controller):
        """Test full lifecycle flow."""
        # Boot
        await controller.boot()
        assert controller.state == RuntimeState.INIT

        # Initialize
        await controller.initialize()
        assert controller.state == RuntimeState.READY

        # Start planning
        await controller.start_planning()
        assert controller.state == RuntimeState.PLANNING

        # Start execution
        await controller.start_execution()
        assert controller.state == RuntimeState.EXECUTING

        # Start validation
        await controller.start_validation()
        assert controller.state == RuntimeState.VALIDATING

        # Complete task
        await controller.complete_task()
        assert controller.state == RuntimeState.DONE

    @pytest.mark.asyncio
    async def test_invalid_transition(self, controller):
        """Test invalid state transition is rejected."""
        # Cannot start planning from BOOT state
        result = await controller.start_planning()
        assert result is False
        assert controller.state == RuntimeState.BOOT

    @pytest.mark.asyncio
    async def test_recovery_flow(self, controller):
        """Test recovery flow."""
        await controller.boot()
        await controller.initialize()

        # Simulate failure
        await controller.fail_task("test error")
        assert controller.state == RuntimeState.FAILED

        # Start recovery
        await controller.start_recovery()
        assert controller.state == RuntimeState.RECOVERING

        # Complete recovery
        await controller.complete_recovery(success=True)
        assert controller.state == RuntimeState.READY

    @pytest.mark.asyncio
    async def test_shutdown(self, controller):
        """Test shutdown."""
        await controller.boot()
        await controller.initialize()
        result = await controller.shutdown()
        assert result is True
        assert not controller.is_running

    def test_get_status(self, controller):
        """Test get_status returns correct info."""
        status = controller.get_status()
        assert "id" in status
        assert "name" in status
        assert "state" in status
        assert "is_running" in status
        assert "stats" in status

    def test_is_healthy(self, controller):
        """Test is_healthy."""
        assert not controller.is_healthy()  # Not running yet

    def test_is_ready_for_work(self, controller):
        """Test is_ready_for_work."""
        assert not controller.is_ready_for_work()  # Not ready yet

    def test_subsystem_management(self, controller):
        """Test subsystem registration."""
        mock_subsystem = MagicMock()
        controller.set_subsystem("test_subsystem", mock_subsystem)
        assert controller.get_subsystem("test_subsystem") == mock_subsystem

    def test_lifecycle_hooks(self, controller):
        """Test lifecycle hook registration."""
        called = []

        def hook(ctrl, data):
            called.append(data)

        controller.on_lifecycle(LifecycleEvent.TASK_COMPLETED, hook)

        # Hooks are registered
        assert len(controller._hooks) == 1

    def test_get_transition_history(self, controller):
        """Test transition history."""
        # Make some transitions
        assert len(controller.get_transition_history()) == 0


# =============================================================================
# EventJournal Tests
# =============================================================================

class TestJournalEntry:
    """Test JournalEntry dataclass."""

    def test_entry_creation(self):
        """Test creating a journal entry."""
        entry = JournalEntry(
            id="test-1",
            event_type="task_created",
            source="test",
            timestamp=datetime.now(),
            data={"task_id": "123"},
        )
        assert entry.id == "test-1"
        assert entry.event_type == "task_created"
        assert entry.data["task_id"] == "123"

    def test_to_dict(self):
        """Test converting entry to dict."""
        entry = JournalEntry(
            id="test-1",
            event_type="task_created",
            source="test",
            timestamp=datetime.now(),
            data={},
        )
        data = entry.to_dict()
        assert data["id"] == "test-1"
        assert data["event_type"] == "task_created"

    def test_from_dict(self):
        """Test creating entry from dict."""
        data = {
            "id": "test-1",
            "event_type": "task_created",
            "source": "test",
            "timestamp": datetime.now().isoformat(),
            "data": {},
            "metadata": {},
            "partition": "",
            "offset": 0,
            "checksum": "",
            "version": "1.0.0",
        }
        entry = JournalEntry.from_dict(data)
        assert entry.id == "test-1"

    def test_checksum_computation(self):
        """Test checksum computation and verification."""
        entry = JournalEntry(
            id="test-1",
            event_type="task_created",
            source="test",
            timestamp=datetime.now(),
            data={"key": "value"},
        )
        entry.checksum = entry.compute_checksum()
        assert entry.verify_checksum() is True


class TestEventJournal:
    """Test EventJournal functionality."""

    @pytest.fixture
    def journal_dir(self, tmp_path):
        """Create temporary journal directory."""
        return tmp_path / "journal"

    @pytest.fixture
    def journal(self, journal_dir):
        """Create EventJournal for testing."""
        return EventJournal(
            journal_dir=journal_dir,
            partition_by=PartitionStrategy.DAY,
            retention_days=7,
        )

    @pytest.mark.asyncio
    async def test_append(self, journal):
        """Test appending entries."""
        entry = JournalEntry(
            id="test-1",
            event_type="task_created",
            source="test",
            timestamp=datetime.now(),
            data={"task_id": "123"},
        )
        result = await journal.append(entry)
        assert result.offset == 0
        assert result.checksum != ""

    @pytest.mark.asyncio
    async def test_append_batch(self, journal):
        """Test appending batch of entries."""
        entries = [
            JournalEntry(
                id=f"test-{i}",
                event_type="task_created",
                source="test",
                timestamp=datetime.now(),
                data={"index": i},
            )
            for i in range(5)
        ]
        results = await journal.append_batch(entries)
        assert len(results) == 5

    @pytest.mark.asyncio
    async def test_read(self, journal):
        """Test reading entries."""
        # Append some entries
        for i in range(5):
            entry = JournalEntry(
                id=f"test-{i}",
                event_type="task_created",
                source="test",
                timestamp=datetime.now(),
                data={},
            )
            await journal.append(entry)

        # Read all
        entries = await journal.read(limit=10)
        assert len(entries) == 5

    @pytest.mark.asyncio
    async def test_scan_with_filter(self, journal):
        """Test scanning with event type filter."""
        # Append mixed entries
        for i in range(3):
            await journal.append(JournalEntry(
                id=f"task-{i}",
                event_type="task_created",
                source="test",
                timestamp=datetime.now(),
                data={},
            ))
        for i in range(2):
            await journal.append(JournalEntry(
                id=f"tool-{i}",
                event_type="tool_executed",
                source="test",
                timestamp=datetime.now(),
                data={},
            ))

        # Scan only task_created
        entries = await journal.scan(event_types=["task_created"])
        assert len(entries) == 3

    def test_partition_name(self, journal):
        """Test partition name generation."""
        name = journal._get_partition_name(datetime(2026, 5, 9))
        assert name == "2026-05-09"

    def test_get_stats(self, journal):
        """Test getting journal stats."""
        stats = journal.get_stats()
        assert "journal_dir" in stats
        assert "partition_by" in stats
        assert "total_partitions" in stats


# =============================================================================
# DeadLetterQueue Tests
# =============================================================================

class TestDLQReason:
    """Test DLQReason enum."""

    def test_dlq_reasons_exist(self):
        """Test DLQ reasons exist."""
        assert DLQReason.HANDLER_ERROR.value == "handler_error"
        assert DLQReason.TIMEOUT.value == "timeout"
        assert DLQReason.MAX_RETRIES_EXCEEDED.value == "max_retries_exceeded"


class TestDLQStatus:
    """Test DLQStatus enum."""

    def test_dlq_statuses_exist(self):
        """Test DLQ statuses exist."""
        assert DLQStatus.PENDING.value == "pending"
        assert DLQStatus.RETRYING.value == "retrying"
        assert DLQStatus.EXPIRED.value == "expired"


class TestDLQEntry:
    """Test DLQEntry dataclass."""

    def test_entry_creation(self):
        """Test creating a DLQ entry."""
        entry = DLQEntry(
            id="dlq-1",
            event_id="evt-1",
            event_type="task_created",
            source="test",
            data={},
            error="Timeout error",
            error_type="TimeoutError",
            reason=DLQReason.TIMEOUT,
            status=DLQStatus.PENDING,
            attempts=0,
            max_attempts=3,
            first_failure=datetime.now(),
            last_failure=datetime.now(),
            handler="test_handler",
            stack_trace="",
        )
        assert entry.id == "dlq-1"
        assert entry.can_retry is True

    def test_can_retry_logic(self):
        """Test can_retry property."""
        entry = DLQEntry(
            id="dlq-1",
            event_id="evt-1",
            event_type="task_created",
            source="test",
            data={},
            error="Error",
            error_type="Error",
            reason=DLQReason.HANDLER_ERROR,
            status=DLQStatus.PENDING,
            attempts=3,
            max_attempts=3,
            first_failure=datetime.now(),
            last_failure=datetime.now(),
            handler="test_handler",
            stack_trace="",
        )
        assert entry.can_retry is False

    def test_to_dict(self):
        """Test converting to dict."""
        entry = DLQEntry(
            id="dlq-1",
            event_id="evt-1",
            event_type="task_created",
            source="test",
            data={},
            error="Error",
            error_type="Error",
            reason=DLQReason.HANDLER_ERROR,
            status=DLQStatus.PENDING,
            attempts=0,
            max_attempts=3,
            first_failure=datetime.now(),
            last_failure=datetime.now(),
            handler="test_handler",
            stack_trace="",
        )
        data = entry.to_dict()
        assert data["id"] == "dlq-1"
        assert data["reason"] == "handler_error"


class TestDeadLetterQueue:
    """Test DeadLetterQueue functionality."""

    @pytest.fixture
    def dlq_dir(self, tmp_path):
        """Create temporary DLQ directory."""
        return tmp_path / "dlq"

    @pytest.fixture
    def dlq(self, dlq_dir):
        """Create DeadLetterQueue for testing."""
        return DeadLetterQueue(dlq_dir=dlq_dir, max_attempts=3)

    @pytest.mark.asyncio
    async def test_enqueue(self, dlq):
        """Test enqueueing failed event."""
        entry = await dlq.enqueue(
            event_id="evt-1",
            event_type="task_created",
            source="test",
            data={},
            error="Timeout",
            error_type="TimeoutError",
            reason=DLQReason.TIMEOUT,
            handler="test_handler",
        )
        assert entry.id is not None
        assert entry.attempts == 0
        assert entry.status == DLQStatus.PENDING

    @pytest.mark.asyncio
    async def test_retry(self, dlq):
        """Test retrying DLQ entry."""
        entry = await dlq.enqueue(
            event_id="evt-1",
            event_type="task_created",
            source="test",
            data={},
            error="Error",
            error_type="Error",
            reason=DLQReason.HANDLER_ERROR,
            handler="test_handler",
        )

        result = await dlq.retry(entry.id)
        assert result is True

        updated = await dlq.get(entry.id)
        assert updated.attempts == 1

    @pytest.mark.asyncio
    async def test_discard(self, dlq):
        """Test discarding DLQ entry."""
        entry = await dlq.enqueue(
            event_id="evt-1",
            event_type="task_created",
            source="test",
            data={},
            error="Error",
            error_type="Error",
            reason=DLQReason.HANDLER_ERROR,
            handler="test_handler",
        )

        result = await dlq.discard(entry.id)
        assert result is True

        # Entry should be removed
        assert await dlq.get(entry.id) is None

    @pytest.mark.asyncio
    async def test_get_pending(self, dlq):
        """Test getting pending entries."""
        for i in range(3):
            await dlq.enqueue(
                event_id=f"evt-{i}",
                event_type="task_created",
                source="test",
                data={},
                error="Error",
                error_type="Error",
                reason=DLQReason.HANDLER_ERROR,
                handler="test_handler",
            )

        pending = await dlq.get_pending()
        assert len(pending) == 3

    def test_get_stats(self, dlq):
        """Test getting DLQ stats."""
        stats = dlq.get_stats()
        assert "total_entries" in stats
        assert "by_status" in stats
        assert "by_reason" in stats


# =============================================================================
# EventReplayer Tests
# =============================================================================

class TestReplayFilter:
    """Test ReplayFilter dataclass."""

    def test_filter_creation(self):
        """Test creating a replay filter."""
        replay_filter = ReplayFilter(
            event_types=["task_created", "task_completed"],
            sources=["test"],
        )
        assert "task_created" in replay_filter.event_types
        assert "test" in replay_filter.sources


class TestReplayResult:
    """Test ReplayResult dataclass."""

    def test_result_creation(self):
        """Test creating a replay result."""
        result = ReplayResult(
            events_replayed=10,
            events_failed=1,
            events_filtered=5,
            duration_ms=100.5,
            final_offset=15,
        )
        assert result.events_replayed == 10
        assert result.events_failed == 1
        assert result.success is True

    def test_to_dict(self):
        """Test converting to dict."""
        result = ReplayResult(events_replayed=10)
        data = result.to_dict()
        assert data["events_replayed"] == 10
        assert data["success"] is True


class TestEventReplayer:
    """Test EventReplayer functionality."""

    @pytest.fixture
    def mock_journal(self):
        """Create a mock journal."""
        journal = MagicMock()
        journal.scan = AsyncMock(return_value=[])
        journal.read = AsyncMock(return_value=[])
        journal.iter_partitions = MagicMock(return_value=iter([]))
        return journal

    @pytest.fixture
    def replayer(self, mock_journal):
        """Create EventReplayer for testing."""
        return EventReplayer(mock_journal)

    def test_replayer_initialization(self, replayer):
        """Test replayer initializes correctly."""
        assert not replayer.is_replaying
        assert replayer.current_offset == 0

    def test_register_handler(self, replayer):
        """Test handler registration."""
        async def handler(data):
            pass

        replayer.register_handler("task_created", handler)
        assert replayer.has_handler("task_created")
        assert replayer.get_handler("task_created") == handler

    def test_unregister_handler(self, replayer):
        """Test handler unregistration."""
        async def handler(data):
            pass

        replayer.register_handler("task_created", handler)
        result = replayer.unregister_handler("task_created")
        assert result is True
        assert not replayer.has_handler("task_created")

    @pytest.mark.asyncio
    async def test_replay_empty_journal(self, replayer):
        """Test replay with empty journal."""
        result = await replayer.replay()
        assert result.events_replayed == 0
        assert result.success is True

    @pytest.mark.asyncio
    async def test_replay_with_events(self, replayer, mock_journal):
        """Test replay with events."""
        from src.core.runtime.journal import JournalEntry

        # Mock journal to return entries
        mock_journal.scan = AsyncMock(return_value=[
            JournalEntry(
                id="test-1",
                event_type="task_created",
                source="test",
                timestamp=datetime.now(),
                data={},
                offset=0,
            ),
        ])

        called = []

        async def handler(data):
            called.append(data)

        replayer.register_handler("task_created", handler)
        result = await replayer.replay()

        assert result.events_replayed == 1
        assert len(called) == 1

    @pytest.mark.asyncio
    async def test_preview(self, replayer, mock_journal):
        """Test preview without replay."""
        from src.core.runtime.journal import JournalEntry

        mock_journal.scan = AsyncMock(return_value=[
            JournalEntry(
                id="test-1",
                event_type="task_created",
                source="test",
                timestamp=datetime.now(),
                data={},
                offset=0,
                checksum="abc",
            ),
        ])

        previews = await replayer.preview()
        assert len(previews) == 1
        assert previews[0]["event_type"] == "task_created"

    def test_get_stats(self, replayer):
        """Test getting replayer stats."""
        stats = replayer.get_stats()
        assert "total_replays" in stats
        assert "total_events_replayed" in stats
        assert "total_errors" in stats
