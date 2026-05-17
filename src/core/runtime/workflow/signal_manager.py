"""Signal Manager with Sequence - Phase 5A (v6).

Implements signal sequencing and idempotent handling.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, Optional, Callable, Awaitable
from dataclasses import dataclass, field

from .types import Signal, SequencedSignal, WorkflowInstance, SignalBackpressureError

logger = logging.getLogger(__name__)


class SignalManager:
    """Manages signals with sequence numbers for ordering.
    
    Features:
    - Sequence numbers for ordering
    - Idempotent signal handling
    - Signal buffering (wait for specific sequence)
    - Signal deduplication
    - Signal backpressure (max pending signals per workflow)
    - Signal retention and cleanup
    """

    def __init__(
        self,
        signal_store: "SignalStore",
        max_pending_signals: int = 1000,
        signal_retention_days: int = 30,
        dedupe_ttl_seconds: float = 60.0,
    ):
        self._store = signal_store
        self._handlers: dict[str, Callable[[Any], Awaitable[Any]]] = {}
        self._waiters: dict[str, asyncio.Future] = {}
        self._lock = asyncio.Lock()
        
        # Backpressure settings
        self._max_pending_signals = max_pending_signals
        self._signal_retention_days = signal_retention_days
        self._dedupe_ttl_seconds = dedupe_ttl_seconds
        
        # Deduplication cache: idempotency_key -> timestamp
        self._dedupe_cache: dict[str, float] = {}
        self._dedupe_lock = asyncio.Lock()

    def register_handler(
        self,
        signal_name: str,
        handler: Callable[[Any], Awaitable[Any]],
    ) -> None:
        """Register a signal handler.
        
        Args:
            signal_name: Name of signal to handle.
            handler: Async function to handle signal payload.
        """
        self._handlers[signal_name] = handler

    async def send_signal(
        self,
        workflow_id: str,
        name: str,
        payload: Any,
        idempotency_key: Optional[str] = None,
    ) -> str:
        """Send a signal to a workflow.
        
        Args:
            workflow_id: Target workflow ID.
            name: Signal name.
            payload: Signal payload.
            idempotency_key: Optional idempotency key.
            
        Returns:
            Signal ID.
            
        Raises:
            SignalBackpressureError: If max pending signals exceeded.
        """
        # Check for duplicate (deduplication)
        key = idempotency_key or f"{workflow_id}:{name}"
        async with self._dedupe_lock:
            if key in self._dedupe_cache:
                dedupe_time = self._dedupe_cache[key]
                if time.time() - dedupe_time < self._dedupe_ttl_seconds:
                    logger.debug(f"Duplicate signal ignored: {key}")
                    return ""  # Return empty to indicate duplicate
            self._dedupe_cache[key] = time.time()
        
        # Backpressure check
        pending = await self._store.get_pending_count(workflow_id)
        if pending >= self._max_pending_signals:
            raise SignalBackpressureError(workflow_id, pending, self._max_pending_signals)
        
        # Get next sequence number
        sequence = await self._store.get_next_sequence(workflow_id)

        signal = Signal(
            signal_id=str(uuid.uuid4()),
            workflow_id=workflow_id,
            name=name,
            payload=payload,
            sequence=sequence,
            idempotency_key=idempotency_key or f"{workflow_id}:{name}:{sequence}",
            received_at=time.time(),
        )

        # Save signal
        await self._store.save(signal)

        # Check for waiting workflow
        await self._deliver_signal(signal)

        logger.info(
            f"Signal {name} sent to workflow {workflow_id[:8]}... "
            f"(sequence={sequence})"
        )

        return signal.signal_id

    async def wait_for_signal(
        self,
        workflow_id: str,
        name: str,
        timeout_seconds: Optional[float] = None,
    ) -> Any:
        """Wait for a specific signal.
        
        Args:
            workflow_id: Workflow waiting for signal.
            name: Signal name.
            timeout_seconds: Optional timeout.
            
        Returns:
            Signal payload.
            
        Raises:
            SignalTimeoutError: If timeout expires.
        """
        future: asyncio.Future = asyncio.get_event_loop().create_future()

        async with self._lock:
            key = f"{workflow_id}:{name}"
            self._waiters[key] = future

        try:
            if timeout_seconds:
                return await asyncio.wait_for(future, timeout=timeout_seconds)
            return await future
        except asyncio.TimeoutError:
            raise SignalTimeoutError(f"Signal {name} timeout")
        finally:
            async with self._lock:
                self._waiters.pop(f"{workflow_id}:{name}", None)

    async def _deliver_signal(self, signal: Signal) -> None:
        """Deliver signal to waiting workflow or handler."""
        key = f"{signal.workflow_id}:{signal.name}"
        
        # Check for waiting workflow
        async with self._lock:
            future = self._waiters.get(key)

        if future and not future.done():
            future.set_result(signal.payload)
            signal.processed = True
            signal.processed_at = time.time()
            await self._store.save(signal)
            return

        # Deliver to registered handler
        handler = self._handlers.get(signal.name)
        if handler:
            try:
                result = await handler(signal.payload)
                signal.processed = True
                signal.processed_at = time.time()
                await self._store.save(signal)
                logger.debug(f"Signal {signal.name} processed by handler")
            except Exception as e:
                logger.error(f"Signal handler error: {e}")

    async def get_signal_history(
        self,
        workflow_id: str,
        name: Optional[str] = None,
        limit: int = 100,
    ) -> list[Signal]:
        """Get signal history for a workflow.
        
        Args:
            workflow_id: Workflow ID.
            name: Optional filter by signal name.
            limit: Maximum signals to return.
            
        Returns:
            List of signals.
        """
        return await self._store.get_signals(workflow_id, name, limit)

    async def get_pending_signals(
        self,
        workflow_id: str,
    ) -> list[Signal]:
        """Get unprocessed signals for a workflow."""
        return await self._store.get_pending(workflow_id)

    async def replay_signals(
        self,
        workflow_id: str,
        from_sequence: int,
    ) -> list[Signal]:
        """Get signals from a sequence number (for replay)."""
        return await self._store.get_from_sequence(workflow_id, from_sequence)


class SignalStore:
    """Storage interface for signals."""

    async def save(self, signal: Signal) -> None:
        """Save signal."""
        raise NotImplementedError()

    async def get(self, signal_id: str) -> Optional[Signal]:
        """Get signal by ID."""
        raise NotImplementedError()

    async def get_signals(
        self,
        workflow_id: str,
        name: Optional[str] = None,
        limit: int = 100,
    ) -> list[Signal]:
        """Get signals for a workflow."""
        raise NotImplementedError()

    async def get_pending(self, workflow_id: str) -> list[Signal]:
        """Get unprocessed signals."""
        raise NotImplementedError()

    async def get_pending_count(self, workflow_id: str) -> int:
        """Get count of pending (unprocessed) signals."""
        raise NotImplementedError()

    async def get_from_sequence(
        self,
        workflow_id: str,
        from_sequence: int,
    ) -> list[Signal]:
        """Get signals from sequence number."""
        raise NotImplementedError()

    async def get_next_sequence(self, workflow_id: str) -> int:
        """Get next sequence number for workflow."""
        raise NotImplementedError()


class InMemorySignalStore(SignalStore):
    """In-memory implementation of signal store."""

    def __init__(self):
        self._signals: dict[str, list[Signal]] = {}
        self._sequences: dict[str, int] = {}
        self._lock = asyncio.Lock()

    async def save(self, signal: Signal) -> None:
        async with self._lock:
            if signal.workflow_id not in self._signals:
                self._signals[signal.workflow_id] = []
            self._signals[signal.workflow_id].append(signal)

    async def get(self, signal_id: str) -> Optional[Signal]:
        async with self._lock:
            for signals in self._signals.values():
                for sig in signals:
                    if sig.signal_id == signal_id:
                        return sig
        return None

    async def get_signals(
        self,
        workflow_id: str,
        name: Optional[str] = None,
        limit: int = 100,
    ) -> list[Signal]:
        async with self._lock:
            signals = self._signals.get(workflow_id, [])
            if name:
                signals = [s for s in signals if s.name == name]
            return signals[-limit:]

    async def get_pending(self, workflow_id: str) -> list[Signal]:
        async with self._lock:
            signals = self._signals.get(workflow_id, [])
            return [s for s in signals if not s.processed]

    async def get_pending_count(self, workflow_id: str) -> int:
        async with self._lock:
            signals = self._signals.get(workflow_id, [])
            return len([s for s in signals if not s.processed])

    async def get_from_sequence(
        self,
        workflow_id: str,
        from_sequence: int,
    ) -> list[Signal]:
        async with self._lock:
            signals = self._signals.get(workflow_id, [])
            return [s for s in signals if s.sequence >= from_sequence]

    async def get_next_sequence(self, workflow_id: str) -> int:
        async with self._lock:
            current = self._sequences.get(workflow_id, 0)
            self._sequences[workflow_id] = current + 1
            return current + 1

    async def cleanup_old_signals(self, retention_days: int) -> int:
        """Remove signals older than retention period.
        
        Args:
            retention_days: Number of days to retain signals.
            
        Returns:
            Number of signals removed.
        """
        cutoff = time.time() - (retention_days * 86400)
        removed = 0
        
        async with self._lock:
            for workflow_id, signals in list(self._signals.items()):
                original_count = len(signals)
                signals = [s for s in signals if s.received_at > cutoff]
                self._signals[workflow_id] = signals
                removed += original_count - len(signals)
        
        return removed


class SignalTimeoutError(Exception):
    """Signal wait timeout."""
    pass
