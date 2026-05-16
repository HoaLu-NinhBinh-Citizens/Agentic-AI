"""WebSocket client wrapper with heartbeat and backpressure for Phase 1B.

Each WebSocketClient owns:
- outbound_queue: asyncio.Queue (maxsize=100)
- sender_task: asyncio.Task for async sending
- heartbeat_task: asyncio.Task for ping/pong

Event flow:
1. Runtime calls client.send_event(event) -> puts event into queue
2. Sender task continuously gets event from queue -> await ws.send_json(event)
3. If queue is full, drop oldest token event (keep done, error, cancelled, ping, pong)
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastapi import WebSocket

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL_SEC = 30.0
HEARTBEAT_TIMEOUT_SEC = 10.0
QUEUE_MAXSIZE = 100


class WebSocketClient:
    """WebSocket client wrapper with queue-based sending and heartbeat.

    Provides:
    - Backpressure via bounded queue (maxsize=100)
    - Heartbeat ping/pong to detect dead clients
    - Graceful cancellation via _cancelled flag
    """

    def __init__(self, websocket: WebSocket, session_id: str) -> None:
        self.ws = websocket
        self.session_id = session_id
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=QUEUE_MAXSIZE)
        self._sender_task: asyncio.Task[None] | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._cancelled = False
        self._connection_closed = asyncio.Event()

    async def start(self) -> None:
        """Start sender and heartbeat tasks."""
        self._sender_task = asyncio.create_task(self._sender())
        self._heartbeat_task = asyncio.create_task(self._heartbeat())
        logger.debug("Started client tasks for session %s", self.session_id)

    async def _sender(self) -> None:
        """Background task that sends queued events to WebSocket."""
        while not self._cancelled:
            try:
                event = await asyncio.wait_for(
                    self._queue.get(),
                    timeout=1.0,
                )
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            try:
                await self.ws.send_json(event)
            except Exception as e:
                logger.warning(
                    "Send failed for session %s: %s",
                    self.session_id,
                    e,
                )
                self._cancelled = True
                self._connection_closed.set()
                break

    async def _heartbeat(self) -> None:
        """Background task that sends ping and waits for pong."""
        while not self._cancelled:
            await asyncio.sleep(HEARTBEAT_INTERVAL_SEC)
            if self._cancelled:
                break

            try:
                pong_received = asyncio.create_task(
                    self._wait_for_pong()
                )
                ping_task = asyncio.create_task(
                    self.ws.send_json({"type": "ping"})
                )

                try:
                    done, pending = await asyncio.wait(
                        [ping_task, pong_received],
                        timeout=HEARTBEAT_TIMEOUT_SEC,
                    )
                except asyncio.CancelledError:
                    ping_task.cancel()
                    pong_received.cancel()
                    break

                if pong_received not in done:
                    pong_received.cancel()
                    logger.warning(
                        "Heartbeat timeout for session %s, closing",
                        self.session_id,
                    )
                    self._cancelled = True
                    self._connection_closed.set()
                    try:
                        await self.ws.close(code=1000)
                    except Exception:
                        pass
                    break

            except Exception as e:
                logger.warning(
                    "Heartbeat error for session %s: %s",
                    self.session_id,
                    e,
                )
                self._cancelled = True
                self._connection_closed.set()
                break

    async def _wait_for_pong(self) -> None:
        """Wait for a pong message from client."""
        while not self._cancelled:
            try:
                data = await asyncio.wait_for(
                    self.ws.receive_json(),
                    timeout=HEARTBEAT_TIMEOUT_SEC,
                )
                if data.get("type") == "pong":
                    return
            except asyncio.TimeoutError:
                raise
            except asyncio.CancelledError:
                raise
            except Exception:
                continue

    async def send_event(self, event: dict[str, Any]) -> bool:
        """Send an event to the client with backpressure handling.

        Args:
            event: Event dict to send.

        Returns:
            True if sent or queued, False if client disconnected.
        """
        if self._cancelled:
            return False

        try:
            self._queue.put_nowait(event)
            return True
        except asyncio.QueueFull:
            if event.get("type") == "token":
                try:
                    self._queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    self._queue.put_nowait(event)
                except asyncio.QueueFull:
                    pass
                return True
            else:
                try:
                    await asyncio.wait_for(
                        self._queue.put(event),
                        timeout=1.0,
                    )
                    return True
                except asyncio.TimeoutError:
                    return False
        except Exception as e:
            logger.warning(
                "Send event failed for session %s: %s",
                self.session_id,
                e,
            )
            return False

    def is_cancelled(self) -> bool:
        """Check if client is cancelled or disconnected."""
        return self._cancelled

    def connection_closed_event(self) -> asyncio.Event:
        """Get event that is set when connection is closed."""
        return self._connection_closed

    async def close(self, code: int = 1000) -> None:
        """Close the client and cancel all tasks."""
        self._cancelled = True

        if self._sender_task and not self._sender_task.done():
            self._sender_task.cancel()
            try:
                await asyncio.wait_for(self._sender_task, timeout=0.5)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await asyncio.wait_for(self._heartbeat_task, timeout=0.5)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

        try:
            await self.ws.close(code=code)
        except Exception:
            pass

        self._connection_closed.set()
        logger.debug("Closed client for session %s", self.session_id)

    async def wait_closed(self) -> None:
        """Wait until connection is closed."""
        await self._connection_closed.wait()
