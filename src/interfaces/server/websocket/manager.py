"""WebSocket connection manager for Phase 1A.

This module provides a simple connection manager for WebSocket connections.
No heartbeat, no queue, no backpressure.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import WebSocket


class ConnectionManager:
    """Simple WebSocket connection manager.

    Manages WebSocket connections per session.
    No heartbeat - TCP will eventually error if client dies.
    No queue - sends directly to WebSocket.
    No backpressure - slow client may block.
    """

    def __init__(self) -> None:
        self._connections: dict[str, list[WebSocket]] = {}

    async def connect(self, session_id: str, ws: WebSocket) -> None:
        """Register a WebSocket connection for a session.

        Args:
            session_id: The session ID to associate the connection with.
            ws: The WebSocket connection to register.
        """
        await ws.accept()
        if session_id not in self._connections:
            self._connections[session_id] = []
        self._connections[session_id].append(ws)

    def disconnect(self, session_id: str, ws: WebSocket) -> None:
        """Unregister a WebSocket connection from a session.

        Args:
            session_id: The session ID.
            ws: The WebSocket connection to remove.
        """
        if session_id in self._connections:
            if ws in self._connections[session_id]:
                self._connections[session_id].remove(ws)
            if not self._connections[session_id]:
                del self._connections[session_id]

    async def send_to_session(self, session_id: str, event: dict) -> None:
        """Send an event to all WebSocket connections for a session.

        Args:
            session_id: The session ID to send to.
            event: The event dict to send.
        """
        if session_id in self._connections:
            for ws in self._connections[session_id]:
                await ws.send_json(event)

    def get_connections(self, session_id: str) -> list[WebSocket]:
        """Get all WebSocket connections for a session.

        Args:
            session_id: The session ID.

        Returns:
            List of WebSocket connections.
        """
        return self._connections.get(session_id, [])

    def close_all_for_session(self, session_id: str) -> None:
        """Close all WebSocket connections for a session.

        Args:
            session_id: The session ID.
        """
        if session_id in self._connections:
            for ws in self._connections[session_id]:
                pass
            del self._connections[session_id]
