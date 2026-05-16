"""WebSocket connection manager for Phase 1B.

Manages WebSocket connections per session using WebSocketClient wrappers.
Provides:
- Multi-client per session support
- Heartbeat and backpressure per client
- Session-level broadcast
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from interfaces.server.websocket.client import WebSocketClient

if TYPE_CHECKING:
    from fastapi import WebSocket

logger = logging.getLogger(__name__)

MAX_CONCURRENT_CONNECTIONS_PER_SESSION = 5


class ConnectionManager:
    """WebSocket connection manager with WebSocketClient support.

    Manages WebSocket connections per session.
    Each connection is wrapped in a WebSocketClient for:
    - Queue-based sending (backpressure)
    - Heartbeat (ping/pong)
    """

    def __init__(self) -> None:
        self._clients: dict[str, list[WebSocketClient]] = {}

    async def connect(
        self,
        session_id: str,
        ws: WebSocket,
    ) -> WebSocketClient | None:
        """Register a WebSocket connection for a session.

        Args:
            session_id: The session ID.
            ws: The WebSocket connection.

        Returns:
            WebSocketClient wrapper or None if max connections reached.
        """
        current = self._clients.get(session_id, [])
        if len(current) >= MAX_CONCURRENT_CONNECTIONS_PER_SESSION:
            logger.warning(
                "Max connections reached for session %s",
                session_id,
            )
            await ws.close(code=4003)
            return None

        await ws.accept()
        client = WebSocketClient(ws, session_id)
        await client.start()

        if session_id not in self._clients:
            self._clients[session_id] = []
        self._clients[session_id].append(client)

        logger.info(
            "WebSocket connected: session=%s, total=%d",
            session_id,
            len(self._clients[session_id]),
        )
        return client

    async def disconnect(self, session_id: str, client: WebSocketClient) -> None:
        """Unregister a WebSocketClient from a session.

        Args:
            session_id: The session ID.
            client: The WebSocketClient to remove.
        """
        if session_id in self._clients:
            if client in self._clients[session_id]:
                self._clients[session_id].remove(client)
            if not self._clients[session_id]:
                del self._clients[session_id]
            logger.info(
                "WebSocket disconnected: session=%s, remaining=%d",
                session_id,
                len(self._clients.get(session_id, [])),
            )

    async def send_to_session(self, session_id: str, event: dict) -> None:
        """Send an event to all WebSocket clients for a session.

        Args:
            session_id: The session ID.
            event: The event dict to send.
        """
        if session_id not in self._clients:
            return

        for client in self._clients[session_id]:
            await client.send_event(event)

    async def broadcast_to_session(
        self,
        session_id: str,
        event: dict,
    ) -> None:
        """Broadcast event to all clients (alias for send_to_session)."""
        await self.send_to_session(session_id, event)

    def get_clients(self, session_id: str) -> list[WebSocketClient]:
        """Get all WebSocket clients for a session.

        Args:
            session_id: The session ID.

        Returns:
            List of WebSocketClient instances.
        """
        return self._clients.get(session_id, [])

    def get_client_count(self, session_id: str) -> int:
        """Get number of clients for a session.

        Args:
            session_id: The session ID.

        Returns:
            Number of connected clients.
        """
        return len(self._clients.get(session_id, []))

    async def close_all_for_session(self, session_id: str) -> None:
        """Close all WebSocket connections for a session.

        Args:
            session_id: The session ID.
        """
        if session_id in self._clients:
            for client in self._clients[session_id]:
                await client.close()
            del self._clients[session_id]
            logger.info("Closed all connections for session: %s", session_id)

    async def close_client(self, session_id: str, client: WebSocketClient) -> None:
        """Close a specific client connection.

        Args:
            session_id: The session ID.
            client: The WebSocketClient to close.
        """
        await client.close()
        await self.disconnect(session_id, client)
