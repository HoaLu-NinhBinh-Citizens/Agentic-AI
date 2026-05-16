"""FastAPI server for Phase 1A.

Minimal viable runtime that allows clients to:
- Create sessions
- Send chat messages over WebSocket
- Receive streaming tokens from mock agent
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware

from core.agent.runtime_agent import RuntimeAgent
from core.session.session_manager import InMemorySessionManager
from interfaces.server.websocket.manager import ConnectionManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")


class ServerState:
    """Application state container."""

    def __init__(
        self,
        session_manager: InMemorySessionManager,
        connection_manager: ConnectionManager,
        mock_agent: MockAgent,
    ) -> None:
        self.session_manager = session_manager
        self.connection_manager = connection_manager
        self.mock_agent = mock_agent
        self._busy_sessions: set[str] = set()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info("Starting AI_support Phase 1A server...")
    yield
    logger.info("Shutting down AI_support Phase 1A server...")


app = FastAPI(
    title="AI_support Phase 1A",
    description="Minimal viable runtime for AI_support",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def logging_middleware(request, call_next):
    """Log all HTTP requests."""
    import time

    start = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - start
    logger.info(
        "%s %s %s %.3fs",
        request.method,
        request.url.path,
        response.status_code,
        duration,
    )
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Handle all unhandled exceptions."""
    logger.exception("Unhandled exception: %s", exc)
    return {"detail": "Internal server error"}, 500


state = ServerState(
    session_manager=InMemorySessionManager(),
    connection_manager=ConnectionManager(),
    mock_agent=RuntimeAgent(),
)


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/sessions", status_code=status.HTTP_201_CREATED)
async def create_session(body: dict[str, Any] | None = None) -> dict[str, str]:
    """Create a new session.

    Args:
        body: Optional request body with workspace path.

    Returns:
        Session ID and WebSocket URL.
    """
    workspace = None
    if body and "workspace" in body:
        workspace = body["workspace"]

    session_id = state.session_manager.create_session(workspace=workspace)
    ws_url = f"ws://{HOST}:{PORT}/ws/{session_id}"
    logger.info("Created session: %s", session_id)
    return {"session_id": session_id, "ws_url": ws_url}


@app.get("/sessions/{session_id}")
async def get_session(session_id: str) -> dict:
    """Get session info by ID.

    Args:
        session_id: The session ID.

    Returns:
        Session dictionary.

    Raises:
        HTTPException: If session not found.
    """
    session = state.session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str) -> dict[str, str]:
    """Delete a session and close all its WebSocket connections.

    Args:
        session_id: The session ID.

    Returns:
        Deletion confirmation.

    Raises:
        HTTPException: If session not found.
    """
    session = state.session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    connections = state.connection_manager.get_connections(session_id)
    for ws in connections:
        try:
            await ws.close(code=1000)
        except Exception:
            pass

    state.connection_manager.close_all_for_session(session_id)

    try:
        state.session_manager.delete_session(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")

    logger.info("Deleted session: %s", session_id)
    return {"status": "deleted"}


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for chat interaction.

    Flow:
    1. Validate session exists
    2. Register connection
    3. Wait for chat messages
    4. Process with mock agent
    5. Keep connection open for more messages

    Args:
        websocket: The WebSocket connection.
        session_id: The session ID from URL path.
    """
    session = state.session_manager.get_session(session_id)
    if not session:
        logger.warning("WebSocket connection rejected: session %s not found", session_id)
        await websocket.close(code=4001)
        return

    await state.connection_manager.connect(session_id, websocket)
    logger.info("WebSocket connected: session=%s", session_id)

    try:
        while True:
            try:
                data = await websocket.receive_json()
            except Exception:
                break

            if data.get("type") == "chat":
                if session_id in state._busy_sessions:
                    await state.connection_manager.send_to_session(
                        session_id,
                        {
                            "type": "error",
                            "data": {
                                "code": "BUSY",
                                "message": "Another chat in progress",
                            },
                        },
                    )
                    continue

                message = data.get("message", "")
                state._busy_sessions.add(session_id)
                logger.info("Processing chat: session=%s, message=%s", session_id, message)

                async def send_event(event: dict) -> None:
                    await state.connection_manager.send_to_session(session_id, event)

                try:
                    await state.mock_agent.stream_response(message, send_event)
                except Exception as e:
                    logger.exception("Error in mock agent: %s", e)
                    await state.connection_manager.send_to_session(
                        session_id,
                        {
                            "type": "error",
                            "data": {
                                "code": "INTERNAL_ERROR",
                                "message": str(e),
                            },
                        },
                    )
                finally:
                    state._busy_sessions.discard(session_id)

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected: session=%s", session_id)
    except Exception:
        logger.exception("WebSocket error: session=%s", session_id)
    finally:
        state.connection_manager.disconnect(session_id, websocket)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "interfaces.server.main:app",
        host=HOST,
        port=PORT,
        log_level=LOG_LEVEL.lower(),
        reload=False,
    )
