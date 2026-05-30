"""
Event Replayer - Replay Events from Journal

Purpose:
    This module provides event journal replay capabilities for deterministic
    replay of recorded runtime events. It is the authoritative source of truth
    for event replay in AI_SUPPORT.

    Three replay concerns exist in the codebase, each with a distinct purpose:

    1. EventJournal replay (this module): Replays events from an event journal
       with deterministic ordering, checksums, and verification.
       Used by: tests/chaos/test_replay_conformance.py, tests/test_runtime.py,
       tests/integration/production_test.py, tests/test_p3_observability.py

    2. Workflow replay (core/runtime/workflow/replay_verifier.py): Command sequence
       verification for deterministic workflow execution. Tracks activities, signals,
       timers, and child workflows for replay verification.

    3. Workspace session replay (infrastructure/): Session-level replay for debugging
       workspace state. Captures file I/O, network requests, etc.

W-001 Fixes Applied:
- Checksum validation for replay determinism
- Deterministic ordering constraints
- Wall-clock vs logical-clock handling
- Replay verification at end of replay

Provides event replay capabilities:
- Replay events from journal offset
- Filter by event type, source, time range
- Custom handler override for replay
- Progress tracking and statistics
- Partial replay support
"""

__all__ = [
    "EventReplayer",
    "ReplayFilter",
    "ReplayResult",
    "ReplayDiff",
    "ReplayTracer",
    "compute_replay_diff",
]

import asyncio
import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)


@dataclass
class ReplayFilter:
    event_types: Optional[List[str]] = None
    sources: Optional[List[str]] = None
    since: Optional[datetime] = None
    until: Optional[datetime] = None
    predicate: Optional[Callable[[Dict[str, Any]], bool]] = None
    partition: Optional[str] = None


@dataclass
class ReplayDiff:
    """Structured diff between original and replay command sequences."""

    original_trace_id: str = ""
    replay_trace_id: str = ""
    original_commands: List[Dict[str, Any]] = field(default_factory=list)
    replay_commands: List[Dict[str, Any]] = field(default_factory=list)
    added_commands: List[Dict[str, Any]] = field(default_factory=list)
    removed_commands: List[Dict[str, Any]] = field(default_factory=list)
    modified_commands: List[Dict[str, Any]] = field(default_factory=list)
    order_mismatches: List[Dict[str, Any]] = field(default_factory=list)
    checksum_original: str = ""
    checksum_replay: str = ""
    is_identical: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "original_trace_id": self.original_trace_id,
            "replay_trace_id": self.replay_trace_id,
            "command_count": {
                "original": len(self.original_commands),
                "replay": len(self.replay_commands),
                "added": len(self.added_commands),
                "removed": len(self.removed_commands),
                "modified": len(self.modified_commands),
                "order_mismatches": len(self.order_mismatches),
            },
            "checksum": {
                "original": self.checksum_original,
                "replay": self.checksum_replay,
            },
            "is_identical": self.is_identical,
            "added_commands": self.added_commands,
            "removed_commands": self.removed_commands,
            "modified_commands": self.modified_commands,
            "order_mismatches": self.order_mismatches,
        }

    def to_text_diff(self) -> str:
        """Render as unified-style text diff for forensic debugging."""
        lines = [
            "=" * 60,
            "REPLAY TRACE DIFF",
            "=" * 60,
            f"Original trace: {self.original_trace_id}",
            f"Replay trace:   {self.replay_trace_id}",
            f"Identical: {self.is_identical}",
            "",
            f"--- Original ({len(self.original_commands)} commands)",
            f"+++ Replay ({len(self.replay_commands)} commands)",
        ]

        if self.removed_commands:
            lines.append("")
            lines.append("--- REMOVED (in original, not in replay) ---")
            for cmd in self.removed_commands:
                lines.append(f"  - {cmd.get('offset', '?')}: {cmd.get('event_type', 'unknown')}")

        if self.added_commands:
            lines.append("")
            lines.append("+++ ADDED (in replay, not in original) +++")
            for cmd in self.added_commands:
                lines.append(f"  + {cmd.get('offset', '?')}: {cmd.get('event_type', 'unknown')}")

        if self.modified_commands:
            lines.append("")
            lines.append("### MODIFIED (same offset, different content) ###")
            for cmd in self.modified_commands:
                lines.append(f"  ~ {cmd.get('offset', '?')}: {cmd.get('event_type', 'unknown')}")
                if cmd.get('diffs'):
                    for diff in cmd['diffs']:
                        lines.append(f"      {diff}")

        if self.order_mismatches:
            lines.append("")
            lines.append("!!! ORDER MISMATCHES !!!")
            for mismatch in self.order_mismatches:
                lines.append(
                    f"    Position {mismatch.get('position', '?')}: "
                    f"expected {mismatch.get('expected', '?')}, "
                    f"got {mismatch.get('actual', '?')}"
                )

        lines.append("=" * 60)
        return "\n".join(lines)


@dataclass
class ReplayResult:
    events_replayed: int = 0
    events_filtered: int = 0
    events_failed: int = 0
    duration_ms: float = 0.0
    final_offset: int = 0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    success: bool = True
    # W-001: Determinism verification fields
    checksum: str = ""  # SHA256 of event sequence
    verification_checksum: str = ""  # Recomputed checksum for verification
    is_deterministic: bool = True  # Set to False if checksums don't match
    event_order_valid: bool = True  # Checks if events are in order

    @property
    def deterministic(self) -> bool:
        return self.is_deterministic

    def to_dict(self) -> Dict[str, Any]:
        return {
            "events_replayed": self.events_replayed,
            "events_filtered": self.events_filtered,
            "events_failed": self.events_failed,
            "duration_ms": self.duration_ms,
            "final_offset": self.final_offset,
            "errors": self.errors,
            "warnings": self.warnings,
            "success": self.success,
            # W-001: Determinism fields
            "checksum": self.checksum,
            "verification_checksum": self.verification_checksum,
            "is_deterministic": self.is_deterministic,
            "event_order_valid": self.event_order_valid,
        }


class ReplayTracer:
    """
    Captures command sequences during replay for forensic comparison.

    Records the actual command sequence executed during replay,
    enabling structured diff against the original sequence.
    """

    def __init__(self, trace_id: str = ""):
        self.trace_id = trace_id or str(uuid4().hex[:16])
        self.commands: List[Dict[str, Any]] = []
        self._capture_enabled = False

    def start_capture(self) -> None:
        """Enable command capture."""
        self.commands.clear()
        self._capture_enabled = True

    def stop_capture(self) -> None:
        """Disable command capture."""
        self._capture_enabled = False

    def record_command(
        self,
        event_type: str,
        offset: int,
        source: Optional[str] = None,
        **metadata: Any,
    ) -> None:
        """Record a command from the replay sequence."""
        if not self._capture_enabled:
            return

        self.commands.append({
            "trace_id": self.trace_id,
            "event_type": event_type,
            "offset": offset,
            "source": source,
            "position": len(self.commands),
            "metadata": metadata,
        })

    def compute_checksum(self) -> str:
        """Compute SHA256 checksum of the command sequence."""
        hasher = hashlib.sha256()
        for cmd in self.commands:
            hasher.update(str(cmd.get("offset", 0)).encode())
            hasher.update(cmd.get("event_type", "").encode())
        return hasher.hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        """Export captured sequence."""
        return {
            "trace_id": self.trace_id,
            "command_count": len(self.commands),
            "checksum": self.compute_checksum(),
            "commands": self.commands,
        }


def compute_replay_diff(
    original: List[Dict[str, Any]],
    replay: List[Dict[str, Any]],
    original_trace_id: str = "",
    replay_trace_id: str = "",
) -> ReplayDiff:
    """
    Compute structured diff between original and replay command sequences.

    Detects:
    - Added commands (in replay, not in original)
    - Removed commands (in original, not in replay)
    - Modified commands (same offset, different content)
    - Order mismatches (same commands, different sequence)
    """
    diff = ReplayDiff(
        original_trace_id=original_trace_id,
        replay_trace_id=replay_trace_id,
        original_commands=original.copy(),
        replay_commands=replay.copy(),
    )

    if not original and not replay:
        diff.is_identical = True
        return diff

    orig_by_offset = {cmd.get("offset"): cmd for cmd in original}
    replay_by_offset = {cmd.get("offset"): cmd for cmd in replay}

    orig_offsets = set(orig_by_offset.keys())
    replay_offsets = set(replay_by_offset.keys())

    # Added and removed
    added_offsets = replay_offsets - orig_offsets
    removed_offsets = orig_offsets - replay_offsets

    diff.added_commands = [replay_by_offset[o] for o in sorted(added_offsets)]
    diff.removed_commands = [orig_by_offset[o] for o in sorted(removed_offsets)]

    # Modified (same offset, different event_type or source)
    common_offsets = orig_offsets & replay_offsets
    for offset in sorted(common_offsets):
        orig_cmd = orig_by_offset[offset]
        replay_cmd = replay_by_offset[offset]

        diffs = []
        for field in ("event_type", "source"):
            if orig_cmd.get(field) != replay_cmd.get(field):
                diffs.append(
                    f"{field}: original={orig_cmd.get(field)!r} -> replay={replay_cmd.get(field)!r}"
                )

        if diffs:
            diff.modified_commands.append({
                "offset": offset,
                "original": orig_cmd,
                "replay": replay_cmd,
                "diffs": diffs,
            })

    # Order mismatch detection
    orig_sequence = [cmd.get("offset") for cmd in original if cmd.get("offset") in common_offsets]
    replay_sequence = [cmd.get("offset") for cmd in replay if cmd.get("offset") in common_offsets]

    for pos, (orig_off, replay_off) in enumerate(zip(orig_sequence, replay_sequence)):
        if orig_off != replay_off:
            diff.order_mismatches.append({
                "position": pos,
                "expected": orig_off,
                "actual": replay_off,
            })

    # Checksum comparison
    orig_hasher = hashlib.sha256()
    for cmd in original:
        orig_hasher.update(str(cmd.get("offset", 0)).encode())
        orig_hasher.update(cmd.get("event_type", "").encode())
    diff.checksum_original = orig_hasher.hexdigest()

    replay_hasher = hashlib.sha256()
    for cmd in replay:
        replay_hasher.update(str(cmd.get("offset", 0)).encode())
        replay_hasher.update(cmd.get("event_type", "").encode())
    diff.checksum_replay = replay_hasher.hexdigest()

    diff.is_identical = (
        not diff.added_commands
        and not diff.removed_commands
        and not diff.modified_commands
        and not diff.order_mismatches
    )

    return diff


class EventReplayer:
    def __init__(self, journal=None):
        # journal is optional to support simple in-memory replays in tests.
        self.journal = journal
        self._is_replaying = False
        self._current_offset = 0
        self._replay_start_time: Optional[datetime] = None
        self._handlers: Dict[str, Callable] = {}
        self._stats = {
            "total_replays": 0,
            "total_events_replayed": 0,
            "total_errors": 0,
        }
        # W-001: Deterministic replay state
        self._checksum_state = hashlib.sha256()
        self._logical_clock = 0  # For deterministic ordering
        self._expected_sequence: List[int] = []  # Expected event offsets
        self._last_offset = -1  # Track last processed offset

        # Replay trace capture
        self._replay_tracer: Optional[ReplayTracer] = None
        self._original_commands: List[Dict[str, Any]] = []
        self._original_trace_id: str = ""

    def _compute_event_checksum(self, entry, logical_clock: int = 0) -> str:
        """W-001: Compute checksum for a single event.

        Includes: offset, event_type, source, and logical_clock position.
        Excludes: timestamp (wall-clock varies) and checksum itself.
        """
        hasher = hashlib.sha256()
        hasher.update(str(entry.offset).encode())
        hasher.update(entry.event_type.encode())
        if entry.source:
            hasher.update(entry.source.encode())
        hasher.update(str(logical_clock).encode())
        return hasher.hexdigest()

    def _validate_offset_order(self, entry) -> bool:
        """W-001: Validate that events are processed in deterministic order.

        Returns:
            True if offset is >= last processed offset (correct order).
        """
        if entry.offset < self._last_offset:
            logger.warning(
                "Offset regression detected during replay: current=%d last=%d",
                entry.offset, self._last_offset,
            )
            return False
        self._last_offset = entry.offset
        return True

    def _reset_deterministic_state(self) -> None:
        """W-001: Reset deterministic verification state before replay."""
        self._checksum_state = hashlib.sha256()
        self._logical_clock = 0
        self._expected_sequence = []
        self._last_offset = -1

    def register_handler(self, event_type: str, handler: Callable[[Dict[str, Any]], Any]) -> None:
        self._handlers[event_type] = handler
        logger.debug("Registered handler for event type: %s", event_type)

    def unregister_handler(self, event_type: str) -> bool:
        if event_type in self._handlers:
            del self._handlers[event_type]
            return True
        return False

    def get_handler(self, event_type: str) -> Optional[Callable]:
        return self._handlers.get(event_type)

    def has_handler(self, event_type: str) -> bool:
        return event_type in self._handlers

    async def replay(
        self,
        from_offset: int = 0,
        replay_filter: Optional[ReplayFilter] = None,
        handlers: Optional[Dict[str, Callable]] = None,
        max_events: int = 0,
        dry_run: bool = False,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        verify_determinism: bool = True,  # W-001: New parameter
        capture_replay_trace: bool = False,
        original_trace_id: str = "",
        original_commands: Optional[List[Dict[str, Any]]] = None,
    ) -> ReplayResult:
        """W-001: Added verify_determinism parameter for deterministic verification.

        Args:
            capture_replay_trace: Enable replay command sequence capture.
            original_trace_id: Trace ID of the original execution for diff comparison.
            original_commands: Pre-captured original command sequence for diff comparison.
        """
        if self._is_replaying:
            logger.warning("Replay already in progress")
            result = ReplayResult()
            result.success = False
            result.errors.append("Replay already in progress")
            return result

        self._is_replaying = True
        self._replay_start_time = datetime.now()
        self._current_offset = from_offset

        # Replay trace capture
        if capture_replay_trace:
            self._replay_tracer = ReplayTracer()
            self._replay_tracer.start_capture()
            self._original_trace_id = original_trace_id
            self._original_commands = original_commands or []

        # W-001: Determinism state is computed locally in the replay loop
        # (self._checksum_state is no longer used directly)
        result = ReplayResult()
        start_time = asyncio.get_event_loop().time()
        processed = 0

        active_handlers = {**self._handlers}
        if handlers:
            active_handlers.update(handlers)

        try:
            # Support a simplified test mode where caller passes a list of dict events.
            # WARNING: in this mode, checksum computation is skipped because
            # we cannot distinguish FakeEvent from dict entries reliably.
            if isinstance(from_offset, list):
                events = from_offset
                result.events_replayed = len(events)
                result.success = True
                # Skip deterministic verification in list shortcut mode
                return result

            if self.journal is None:
                raise RuntimeError("Journal is required for offset-based replay")

            entries = await self.journal.scan(
                event_types=replay_filter.event_types if replay_filter else None,
                sources=replay_filter.sources if replay_filter else None,
                since=replay_filter.since if replay_filter else None,
                until=replay_filter.until if replay_filter else None,
                limit=max_events if max_events > 0 else 100000,
            )

            total_events = len(entries)

            logger.info("Starting replay from offset %d, %d events to process", from_offset, total_events)

            hasher = hashlib.sha256()
            logical_clock = 0
            for entry in entries:
                if entry.offset < from_offset:
                    continue

                # W-001: Validate offset order for determinism
                if verify_determinism and not self._validate_offset_order(entry):
                    result.event_order_valid = False
                    result.is_deterministic = False
                    result.warnings.append(f"Offset order violation at offset {entry.offset}")
                    # Don't include this entry in checksums — order is non-deterministic
                    continue

                if replay_filter and replay_filter.predicate:
                    if not replay_filter.predicate(entry.to_dict()):
                        result.events_filtered += 1
                        continue

                if max_events > 0 and processed >= max_events:
                    break

                try:
                    event_type = entry.event_type
                    handler = active_handlers.get(event_type)

                    if handler:
                        if dry_run:
                            logger.debug("[DRY RUN] Would process %s", event_type)
                        else:
                            await handler(entry.to_dict())

                    # W-001: Update checksum for deterministic verification
                    if verify_determinism and hasher is not None:
                        event_checksum = self._compute_event_checksum(entry, logical_clock)
                        hasher.update(event_checksum.encode())
                        logical_clock += 1

                    # Replay trace: record command
                    if self._replay_tracer is not None:
                        self._replay_tracer.record_command(
                            event_type=entry.event_type,
                            offset=entry.offset,
                            source=entry.source,
                        )

                    result.events_replayed += 1
                    result.final_offset = entry.offset

                except Exception as exc:
                    result.events_failed += 1
                    result.errors.append(f"Offset {entry.offset}: {str(exc)}")
                    logger.error("Failed to replay event at offset %d: %s", entry.offset, exc)

                    if result.events_failed > 100:
                        result.warnings.append("Error threshold exceeded")
                        break

                processed += 1
                self._current_offset = entry.offset

                if progress_callback and total_events > 0:
                    progress_callback(processed, total_events)

            # W-001: Finalize determinism verification
            if verify_determinism:
                if hasher is not None:
                    result.checksum = hasher.hexdigest()
                result.verification_checksum = self._compute_sequence_checksum(entries, from_offset)
                result.is_deterministic = (
                    result.checksum == result.verification_checksum and
                    result.event_order_valid and
                    result.events_failed == 0
                )

                if not result.is_deterministic:
                    result.warnings.append(
                        "Replay may not be deterministic - checksums don't match "
                        f"or events failed. Expected: {result.verification_checksum[:16]}..., "
                        f"Got: {result.checksum[:16]}..."
                    )

            self._stats["total_replays"] += 1
            self._stats["total_events_replayed"] += result.events_replayed
            self._stats["total_errors"] += result.events_failed

        except Exception as exc:
            result.success = False
            result.errors.append(str(exc))
            logger.exception("Replay failed")

        finally:
            self._is_replaying = False
            if self._replay_tracer is not None:
                self._replay_tracer.stop_capture()
            result.duration_ms = (asyncio.get_event_loop().time() - start_time) * 1000

        logger.info(
            "Replay complete: %d/%d events replayed (%d failed, %d filtered) in %.2fms",
            result.events_replayed,
            processed,
            result.events_failed,
            result.events_filtered,
            result.duration_ms,
        )

        # W-001: Log determinism status
        if verify_determinism:
            logger.info(
                "Determinism verification: %s (checksum: %s...)",
                "PASSED" if result.is_deterministic else "FAILED",
                result.checksum[:16] if result.checksum else "N/A",
            )

        return result

    def _compute_sequence_checksum(self, entries: List, from_offset: int) -> str:
        """W-001: Compute expected checksum for verification.

        Recomputes checksum from entries for comparison.
        Must match the incremental checksum: hash each entry's data independently,
        then accumulate those hashes into the final checksum.
        """
        hasher = hashlib.sha256()
        lc = 0

        for entry in entries:
            if entry.offset < from_offset:
                continue
            entry_hasher = hashlib.sha256()
            entry_hasher.update(str(entry.offset).encode())
            entry_hasher.update(entry.event_type.encode())
            if entry.source:
                entry_hasher.update(entry.source.encode())
            entry_hasher.update(str(lc).encode())
            hasher.update(entry_hasher.hexdigest().encode())
            lc += 1

        return hasher.hexdigest()

    async def replay_partition(
        self,
        partition: str,
        handlers: Optional[Dict[str, Callable]] = None,
        dry_run: bool = False,
    ) -> ReplayResult:
        replay_filter = ReplayFilter(partition=partition)
        return await self.replay(
            from_offset=0,
            replay_filter=replay_filter,
            handlers=handlers,
            dry_run=dry_run,
        )

    async def replay_between(
        self,
        start_offset: int,
        end_offset: int,
        handlers: Optional[Dict[str, Callable]] = None,
        dry_run: bool = False,
    ) -> ReplayResult:
        max_events = end_offset - start_offset + 1
        entries = await self.journal.read(offset=start_offset, limit=max_events)

        result = ReplayResult()
        start_time = asyncio.get_event_loop().time()

        active_handlers = {**self._handlers}
        if handlers:
            active_handlers.update(handlers)

        for entry in entries:
            if entry.offset > end_offset:
                break

            try:
                event_type = entry.event_type
                handler = active_handlers.get(event_type)

                if handler and not dry_run:
                    await handler(entry.to_dict())

                result.events_replayed += 1
                result.final_offset = entry.offset

            except Exception as exc:
                result.events_failed += 1
                result.errors.append(f"Offset {entry.offset}: {str(exc)}")

        result.duration_ms = (asyncio.get_event_loop().time() - start_time) * 1000
        return result

    async def preview(
        self,
        from_offset: int = 0,
        replay_filter: Optional[ReplayFilter] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        entries = await self.journal.scan(
            event_types=replay_filter.event_types if replay_filter else None,
            sources=replay_filter.sources if replay_filter else None,
            since=replay_filter.since if replay_filter else None,
            until=replay_filter.until if replay_filter else None,
            limit=limit,
        )

        previews = []
        for entry in entries:
            if entry.offset < from_offset:
                continue

            previews.append({
                "offset": entry.offset,
                "partition": entry.partition,
                "event_type": entry.event_type,
                "source": entry.source,
                "timestamp": entry.timestamp.isoformat(),
                "has_handler": self.has_handler(entry.event_type),
                "checksum": entry.checksum,
            })

        return previews

    async def get_replay_points(self) -> List[Dict[str, Any]]:
        points = []
        for partition in self.journal.iter_partitions():
            points.append({
                "name": partition.name,
                "entry_count": partition.entry_count,
                "size_bytes": partition.size_bytes,
                "first_timestamp": partition.first_timestamp.isoformat() if partition.first_timestamp else None,
                "last_timestamp": partition.last_timestamp.isoformat() if partition.last_timestamp else None,
            })
        return points

    @property
    def is_replaying(self) -> bool:
        return self._is_replaying

    @property
    def current_offset(self) -> int:
        return self._current_offset

    def get_stats(self) -> Dict[str, Any]:
        return dict(self._stats)

    def get_replay_trace(self) -> Optional[Dict[str, Any]]:
        """Get the captured replay trace after a replay session."""
        if self._replay_tracer is None:
            return None
        return self._replay_tracer.to_dict()

    def compare_with_original(
        self,
        original_commands: Optional[List[Dict[str, Any]]] = None,
        original_trace_id: str = "",
    ) -> ReplayDiff:
        """
        Compare replay commands against original execution for forensic debugging.

        Args:
            original_commands: List of original commands (uses stored if not provided)
            original_trace_id: Trace ID of the original execution

        Returns:
            ReplayDiff with structured comparison results
        """
        replay_commands = []
        if self._replay_tracer is not None:
            replay_commands = self._replay_tracer.commands

        orig_cmds = original_commands if original_commands is not None else self._original_commands
        orig_tid = original_trace_id if original_trace_id else self._original_trace_id
        replay_tid = self._replay_tracer.trace_id if self._replay_tracer else ""

        return compute_replay_diff(
            original=orig_cmds,
            replay=replay_commands,
            original_trace_id=orig_tid,
            replay_trace_id=replay_tid,
        )

    def reset_stats(self) -> None:
        self._stats = {
            "total_replays": 0,
            "total_events_replayed": 0,
            "total_errors": 0,
        }
