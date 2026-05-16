"""
Event Replayer - Replay Events from Journal

Provides event replay capabilities:
- Replay events from journal offset
- Filter by event type, source, time range
- Custom handler override for replay
- Progress tracking and statistics
- Partial replay support
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

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
class ReplayResult:
    events_replayed: int = 0
    events_filtered: int = 0
    events_failed: int = 0
    duration_ms: float = 0.0
    final_offset: int = 0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    success: bool = True

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
        }


class EventReplayer:
    def __init__(self, journal):
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
    ) -> ReplayResult:
        if self._is_replaying:
            logger.warning("Replay already in progress")
            result = ReplayResult()
            result.success = False
            result.errors.append("Replay already in progress")
            return result

        self._is_replaying = True
        self._replay_start_time = datetime.now()
        self._current_offset = from_offset

        result = ReplayResult()
        start_time = asyncio.get_event_loop().time()

        active_handlers = {**self._handlers}
        if handlers:
            active_handlers.update(handlers)

        try:
            entries = await self.journal.scan(
                event_types=replay_filter.event_types if replay_filter else None,
                sources=replay_filter.sources if replay_filter else None,
                since=replay_filter.since if replay_filter else None,
                until=replay_filter.until if replay_filter else None,
                limit=max_events if max_events > 0 else 100000,
            )

            total_events = len(entries)
            processed = 0

            logger.info("Starting replay from offset %d, %d events to process", from_offset, total_events)

            for entry in entries:
                if entry.offset < from_offset:
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

            self._stats["total_replays"] += 1
            self._stats["total_events_replayed"] += result.events_replayed
            self._stats["total_errors"] += result.events_failed

        except Exception as exc:
            result.success = False
            result.errors.append(str(exc))
            logger.exception("Replay failed")

        finally:
            self._is_replaying = False
            result.duration_ms = (asyncio.get_event_loop().time() - start_time) * 1000

        logger.info(
            "Replay complete: %d/%d events replayed (%d failed, %d filtered) in %.2fms",
            result.events_replayed,
            processed,
            result.events_failed,
            result.events_filtered,
            result.duration_ms,
        )

        return result

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

    def reset_stats(self) -> None:
        self._stats = {
            "total_replays": 0,
            "total_events_replayed": 0,
            "total_errors": 0,
        }
