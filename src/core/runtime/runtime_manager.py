"""Runtime manager for Phase 1B.

Manages agent runtime lifecycle with:
- Stream cancellation support
- Request timeout support
- Stream ownership tracking

This is the Phase 1B runtime manager for the minimal viable server.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.agent.mock_agent import MockAgent
    from interfaces.server.websocket.client import WebSocketClient

logger = logging.getLogger(__name__)

STREAM_TIMEOUT_SEC = 30.0


class StreamInfo:
    """Information about an active stream."""

    def __init__(
        self,
        task: asyncio.Task,
        cancellation_event: asyncio.Event,
        owner_client: WebSocketClient,
    ) -> None:
        self.task = task
        self.cancellation_event = cancellation_event
        self.owner_client = owner_client


class RuntimeManager:
    """Manages agent runtime lifecycle with cancellation and timeout support."""

    def __init__(self, mock_agent: MockAgent) -> None:
        self._mock_agent = mock_agent
        self._streams: dict[str, StreamInfo] = {}

    async def start(self) -> None:
        """Start the runtime."""
        logger.info("Runtime manager started")

    async def stop(self) -> None:
        """Stop the runtime and cancel all streams."""
        await self.cancel_all_streams()
        logger.info("Runtime manager stopped")

    async def execute(
        self,
        session_id: str,
        message: str,
        send_event: Any,
        owner_client: WebSocketClient,
    ) -> None:
        """Execute a streaming task with cancellation and timeout support.

        Args:
            session_id: The session ID.
            message: The message to process.
            send_event: Callback to send events.
            owner_client: The WebSocket client that owns this stream.
        """
        cancellation_event = asyncio.Event()
        stream_info = StreamInfo(
            task=None,
            cancellation_event=cancellation_event,
            owner_client=owner_client,
        )
        self._streams[session_id] = stream_info

        async def run_stream() -> None:
            try:
                await asyncio.wait_for(
                    self._mock_agent.stream_response(
                        message,
                        send_event,
                        cancellation_event,
                    ),
                    timeout=STREAM_TIMEOUT_SEC,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "Stream timeout for session %s",
                    session_id,
                )
                cancellation_event.set()
                await send_event({
                    "type": "error",
                    "data": {
                        "code": "TIMEOUT",
                        "message": "Stream timeout",
                    },
                })
            except asyncio.CancelledError:
                logger.debug("Stream cancelled for session %s", session_id)
            finally:
                self._streams.pop(session_id, None)

        task = asyncio.create_task(run_stream())
        stream_info.task = task

    async def cancel_stream(self, session_id: str) -> bool:
        """Cancel a stream by session ID.

        Args:
            session_id: The session ID.

        Returns:
            True if stream was cancelled, False if not found.
        """
        stream_info = self._streams.get(session_id)
        if not stream_info:
            return False

        stream_info.cancellation_event.set()

        if stream_info.task and not stream_info.task.done():
            try:
                await asyncio.wait_for(stream_info.task, timeout=1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

        self._streams.pop(session_id, None)
        logger.info("Cancelled stream for session: %s", session_id)
        return True

    async def cancel_stream_for_client(
        self,
        session_id: str,
        client: WebSocketClient,
    ) -> bool:
        """Cancel stream if owned by the given client.

        Args:
            session_id: The session ID.
            client: The WebSocket client.

        Returns:
            True if cancelled, False if not found or different owner.
        """
        stream_info = self._streams.get(session_id)
        if not stream_info:
            return False
        if stream_info.owner_client is not client:
            return False
        return await self.cancel_stream(session_id)

    def is_streaming(self, session_id: str) -> bool:
        """Check if session has an active stream.

        Args:
            session_id: The session ID.

        Returns:
            True if stream is active.
        """
        return session_id in self._streams

    def get_cancellation_event(self, session_id: str) -> asyncio.Event | None:
        """Get cancellation event for a session's stream.

        Args:
            session_id: The session ID.

        Returns:
            Cancellation event or None.
        """
        stream_info = self._streams.get(session_id)
        return stream_info.cancellation_event if stream_info else None

    async def cancel_all_streams(self) -> None:
        """Cancel all active streams."""
        for session_id in list(self._streams.keys()):
            await self.cancel_stream(session_id)
        logger.info("All streams cancelled")

    def get_stream_owner(self, session_id: str) -> WebSocketClient | None:
        """Get the owner client of a stream.

        Args:
            session_id: The session ID.

        Returns:
            The owner WebSocketClient or None.
        """
        stream_info = self._streams.get(session_id)
        return stream_info.owner_client if stream_info else None
