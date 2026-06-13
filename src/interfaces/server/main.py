"""FastAPI server for Phase 2B.

Runtime with reliability and resource protection:
- Sessions persist across restarts (SQLite)
- Heartbeat to detect dead WebSocket clients
- Graceful cancellation of ongoing streams
- Request timeout (30s)
- Token-level backpressure (per WebSocket queue)
- Basic rate limiting (per session)
- MCP connectivity and tool discovery
- Tool execution runtime (Phase 2B)

Phase 2B additions:
- Tool execution via ToolExecutionService
- WebSocket tool_call message handling
- Tool registry per session with concurrency control
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

# Add src/ to path so 'from core.', 'from infrastructure.' etc. work
_SRC_DIR = Path(__file__).parent.parent.parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import time
from datetime import datetime

from application.orchestration.tool_execution.config import get_tool_execution_config
from application.orchestration.tool_execution.service import ToolExecutionService
from core.agent.real_agent import RealAgent
from core.rate_limiter import SlidingWindowRateLimiter
from core.runtime.runtime_manager import RuntimeManager
from core.session.persistent_manager import PersistentSessionManager
from infrastructure.persistence.sqlite.session_store import SessionStore
from infrastructure.mcp.manager import MCPClientManager
from interfaces.server.websocket.manager import ConnectionManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

RATE_LIMIT_CHAT_MAX = 5
RATE_LIMIT_CHAT_WINDOW = 10.0
# Clients that disconnect without calling the delete-session API would
# otherwise leak one limiter per session forever (8h+ uptime hazard).
RATE_LIMITER_IDLE_TTL_SECONDS = 1800.0
RATE_LIMITER_PRUNE_INTERVAL_SECONDS = 60.0


class ServerState:
    """Application state container for Phase 2B."""

    def __init__(
        self,
        session_manager: PersistentSessionManager,
        connection_manager: ConnectionManager,
        runtime_manager: RuntimeManager,
        real_agent: RealAgent,
        tool_execution_service: ToolExecutionService,
    ) -> None:
        self.session_manager = session_manager
        self.connection_manager = connection_manager
        self.runtime_manager = runtime_manager
        self.real_agent = real_agent
        self.tool_execution_service = tool_execution_service
        # session_id -> (limiter, last_used monotonic timestamp)
        self._rate_limiters: dict[str, tuple[SlidingWindowRateLimiter, float]] = {}
        self._last_prune: float = 0.0

    def get_rate_limiter(self, session_id: str) -> SlidingWindowRateLimiter:
        """Get or create rate limiter for a session."""
        now = time.monotonic()
        self._prune_idle_rate_limiters(now)
        existing = self._rate_limiters.get(session_id)
        limiter = existing[0] if existing else SlidingWindowRateLimiter(
            max_requests=RATE_LIMIT_CHAT_MAX,
            window_seconds=RATE_LIMIT_CHAT_WINDOW,
        )
        self._rate_limiters[session_id] = (limiter, now)
        return limiter

    def _prune_idle_rate_limiters(self, now: float) -> None:
        """Drop limiters for sessions idle past the TTL (leak prevention)."""
        if now - self._last_prune < RATE_LIMITER_PRUNE_INTERVAL_SECONDS:
            return
        self._last_prune = now
        expired = [
            sid
            for sid, (_, last_used) in self._rate_limiters.items()
            if now - last_used > RATE_LIMITER_IDLE_TTL_SECONDS
        ]
        for sid in expired:
            self._rate_limiters.pop(sid, None)
        if expired:
            logger.debug("Pruned %d idle rate limiters", len(expired))

    def clear_rate_limiter(self, session_id: str) -> None:
        """Clear rate limiter for a session."""
        self._rate_limiters.pop(session_id, None)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info("Starting AI_support Phase 2B server...")

    # Load tool execution configuration
    tool_config = get_tool_execution_config()

    store = SessionStore()
    session_manager = PersistentSessionManager(store)
    session_manager.set_config(tool_config)
    await session_manager.initialize()

    connection_manager = ConnectionManager()
    real_agent = RealAgent()
    runtime_manager = RuntimeManager(real_agent)
    await runtime_manager.start()

    # Initialize MCP manager (skip if config not found)
    mcp_manager = None
    mcp_config_path = Path("configs/mcp/servers.yaml")
    if mcp_config_path.exists():
        mcp_manager = MCPClientManager(config_path=str(mcp_config_path))
        try:
            await asyncio.wait_for(mcp_manager.initialize(), timeout=15.0)
            logger.info(
                "MCP client manager ready",
                servers=len(mcp_manager._servers),
                tools=len(mcp_manager._global_tools),
            )
        except (RuntimeError, asyncio.TimeoutError, Exception) as e:
            logger.warning("MCP initialization skipped: %s", str(e))
            mcp_manager = None
    else:
        logger.info("MCP config not found, skipping MCP initialization")

    # Set MCP manager in session manager for tool execution
    session_manager.set_mcp_manager(mcp_manager)

    # Create tool execution service
    tool_execution_service = ToolExecutionService(session_manager)

    # Optional: live workspace indexing (file watcher + incremental indexer).
    # Off by default — requires Ollama for embeddings; enable explicitly.
    indexing_service = None
    if os.getenv("AI_SUPPORT_ENABLE_INDEXING", "0") == "1":
        try:
            from src.infrastructure.indexing.service import IndexingService

            workspace = Path(os.getenv("AI_SUPPORT_WORKSPACE", ".")).resolve()
            indexing_service = IndexingService(workspace=workspace)
            await indexing_service.start()
            logger.info("Workspace indexing enabled for %s", workspace)
        except Exception as e:
            logger.warning("Workspace indexing failed to start: %s", e)
            indexing_service = None

    workspace_root = Path(os.getenv("AI_SUPPORT_WORKSPACE", ".")).resolve()
    app.state.workspace_root = workspace_root

    app.state.server_state = ServerState(
        session_manager=session_manager,
        connection_manager=connection_manager,
        runtime_manager=runtime_manager,
        real_agent=real_agent,
        tool_execution_service=tool_execution_service,
    )
    app.state.mcp_manager = mcp_manager
    app.state.indexing_service = indexing_service

    logger.info("Workspace root: %s", workspace_root)

    logger.info(
        "AI_support Phase 2B server started. "
        "Loaded %d active sessions from database.",
        len(session_manager.list_sessions()),
    )

    yield

    logger.info("Shutting down AI_support Phase 2B server...")
    if indexing_service is not None:
        await indexing_service.stop()
    await session_manager.close()
    await runtime_manager.stop()
    await connection_manager.close_all_for_session("*")
    if mcp_manager is not None:
        await mcp_manager.shutdown()
    logger.info("AI_support Phase 2B server stopped")


app = FastAPI(
    title="AI_support Phase 2B",
    description="Runtime with tool execution support",
    version="1.3.0",
    lifespan=lifespan,
)

_DEFAULT_CORS_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:8000",
]
_cors_env = os.getenv("AI_SUPPORT_CORS_ORIGINS", "")
CORS_ORIGINS = [o.strip() for o in _cors_env.split(",") if o.strip()] if _cors_env else _DEFAULT_CORS_ORIGINS

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
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


def get_state() -> ServerState:
    """Get server state."""
    return app.state.server_state


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/api/score")
async def get_score() -> dict[str, Any]:
    """Get AI_SUPPORT score for desktop app.
    
    Returns a score representing the system's quality/reliability
    for embedded engineering assistance.
    """
    return {
        "score": 60,
        "label": "Production Readiness",
        "details": {
            "architecture": 6.0,
            "distributed_systems": 4.0,
            "embedded_infrastructure": 5.5,
            "ai_architecture": 6.0,
            "security": 4.5,
            "reliability": 5.0,
            "observability": 5.5,
            "scalability": 4.5,
        },
        "timestamp": None,
        "version": "1.0.0",
    }


@app.get("/api/fs/read")
async def read_file(path: str) -> dict[str, str]:
    """Read a file from the workspace.

    Args:
        path: Path to the file to read.

    Returns:
        File content.
    """
    workspace_root = app.state.workspace_root

    try:
        resolved = Path(path).resolve()
    except (ValueError, OSError):
        raise HTTPException(status_code=400, detail="Invalid path")

    if not resolved.is_relative_to(workspace_root):
        raise HTTPException(status_code=403, detail="Access denied: path is outside workspace")

    if not resolved.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    try:
        content = resolved.read_text(encoding="utf-8", errors="replace")
        return {"content": content, "path": str(resolved)}
    except Exception as e:
        logger.error("Error reading file %s: %s", path, e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/fs/dir")
async def read_directory(path: str) -> dict[str, Any]:
    """Read a directory listing.

    Args:
        path: Path to the directory to read.

    Returns:
        Directory contents.
    """
    workspace_root = app.state.workspace_root

    try:
        resolved = Path(path).resolve()
    except (ValueError, OSError):
        raise HTTPException(status_code=400, detail="Invalid path")

    if not resolved.is_relative_to(workspace_root):
        raise HTTPException(status_code=403, detail="Access denied: path is outside workspace")

    if not resolved.is_dir():
        raise HTTPException(status_code=404, detail="Directory not found")

    try:
        items = []
        for item in resolved.iterdir():
            items.append({
                "name": item.name,
                "path": str(item),
                "isDir": item.is_dir(),
            })

        items.sort(key=lambda x: (not x["isDir"], x["name"].lower()))

        return {"path": str(resolved), "items": items}
    except Exception as e:
        logger.error("Error reading directory %s: %s", path, e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/sessions", status_code=status.HTTP_201_CREATED)
async def create_session(body: dict[str, Any] | None = None) -> dict[str, str]:
    """Create a new session.

    Args:
        body: Optional request body with workspace path.

    Returns:
        Session ID and WebSocket URL.
    """
    server_state = get_state()
    workspace = None
    if body and "workspace" in body:
        workspace = body["workspace"]

    session_id = server_state.session_manager.create_session()
    await server_state.session_manager.save_session(session_id)
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
    server_state = get_state()
    session = server_state.session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str) -> dict[str, str]:
    """Delete a session and close all its WebSocket connections.

    Phase 2B: Also closes the tool registry for this session.

    Args:
        session_id: The session ID.

    Returns:
        Deletion confirmation.

    Raises:
        HTTPException: If session not found.
    """
    server_state = get_state()
    session = server_state.session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    await server_state.runtime_manager.cancel_stream(session_id)
    await server_state.connection_manager.close_all_for_session(session_id)
    server_state.clear_rate_limiter(session_id)

    try:
        await server_state.session_manager.delete_session(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")

    logger.info("Deleted session: %s", session_id)
    return {"status": "deleted"}


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for chat interaction and tool execution.

    Flow:
    1. Validate session exists
    2. Check connection rate limit
    3. Register connection with heartbeat
    4. Handle messages: chat, cancel, tool_call
    5. Stream response with timeout
    6. Keep connection open for more messages

    Phase 2B additions:
    - tool_call message handling for tool execution
    - Broadcast of tool_call_start, tool_call_result, tool_call_error events

    Args:
        websocket: The WebSocket connection.
        session_id: The session ID from URL path.
    """
    server_state = get_state()

    session = server_state.session_manager.get_session(session_id)
    if not session:
        logger.warning(
            "WebSocket connection rejected: session %s not found",
            session_id,
        )
        await websocket.close(code=4001)
        return

    client = await server_state.connection_manager.connect(session_id, websocket)
    if not client:
        logger.warning(
            "WebSocket connection rejected: max connections for session %s",
            session_id,
        )
        return

    logger.info("WebSocket connected: session=%s", session_id)

    async def send_event(event: dict) -> None:
        await client.send_event(event)

    async def broadcast_to_session(session_id: str, event: dict) -> None:
        """Broadcast an event to all clients of a session."""
        await server_state.connection_manager.broadcast_to_session(session_id, event)

    try:
        while True:
            try:
                data = await websocket.receive_json()
            except Exception:
                break

            msg_type = data.get("type")

            if msg_type == "chat":
                if server_state.runtime_manager.is_streaming(session_id):
                    await send_event({
                        "type": "error",
                        "data": {
                            "code": "BUSY",
                            "message": "Another chat in progress",
                        },
                    })
                    continue

                rate_limiter = server_state.get_rate_limiter(session_id)
                if not rate_limiter.allow():
                    await send_event({
                        "type": "error",
                        "data": {
                            "code": "RATE_LIMITED",
                            "message": "Too many requests, please wait",
                        },
                    })
                    continue

                message = data.get("message", "")
                logger.info(
                    "Processing chat: session=%s, message=%s",
                    session_id,
                    message,
                )

                await server_state.runtime_manager.execute(
                    session_id,
                    message,
                    send_event,
                    client,
                )

            elif msg_type == "cancel":
                logger.info("Cancellation requested: session=%s", session_id)
                await server_state.runtime_manager.cancel_stream(session_id)

            elif msg_type == "tool_call":
                await handle_tool_call(
                    server_state,
                    session_id,
                    data,
                    broadcast_to_session,
                )

            elif msg_type == "pong":
                pass

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected: session=%s", session_id)
    except Exception:
        logger.exception("WebSocket error: session=%s", session_id)
    finally:
        await server_state.runtime_manager.cancel_stream_for_client(
            session_id,
            client,
        )
        await server_state.connection_manager.disconnect(session_id, client)
        await client.close()


async def handle_tool_call(
    server_state: ServerState,
    session_id: str,
    data: dict,
    broadcast_callback: Any,
) -> None:
    """Handle a tool_call message from WebSocket.

    Args:
        server_state: Server state.
        session_id: Session ID.
        data: Message data containing tool_call details.
        broadcast_callback: Callback for broadcasting events.
    """
    message_data = data.get("data", {})
    tool_name = message_data.get("tool_name")
    arguments = message_data.get("arguments", {})
    call_id = message_data.get("call_id")
    trace_id = message_data.get("trace_id")

    if not tool_name or not isinstance(arguments, dict):
        await server_state.connection_manager.broadcast_to_session(
            session_id,
            {
                "type": "error",
                "data": {
                    "code": "INVALID_TOOL_CALL",
                    "message": "Missing tool_name or arguments",
                },
            }
        )
        return

    logger.info(
        "Processing tool_call: session=%s, tool=%s",
        session_id,
        tool_name,
    )

    await server_state.tool_execution_service.execute_tool(
        session_id=session_id,
        tool_name=tool_name,
        arguments=arguments,
        call_id=call_id,
        trace_id=trace_id,
        broadcast_callback=broadcast_callback,
    )


# ============================================
# AI Configuration & Test Endpoints
# ============================================


@app.get("/api/ai/config/status")
async def get_ai_config_status() -> dict[str, Any]:
    """Get AI provider configuration status."""
    server_state = get_state()
    status = server_state.real_agent.get_configuration_status()

    # Check Ollama availability
    ollama_available = False
    ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    try:
        import aiohttp

        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{ollama_url}/api/tags", timeout=aiohttp.ClientTimeout(total=2)
            ) as resp:
                ollama_available = resp.status == 200
    except Exception:
        ollama_available = False

    return {
        "configured": status.get("configured", False),
        "active_provider": status.get("active_provider"),
        "providers": status.get("providers", {}),
        "ollama_available": ollama_available,
        "environment": {
            "OPENAI_API_KEY": bool(os.getenv("OPENAI_API_KEY")),
            "ANTHROPIC_API_KEY": bool(os.getenv("ANTHROPIC_API_KEY")),
            "OLLAMA_BASE_URL": ollama_url,
        },
        "suggestions": status.get("suggestions", []),
    }


@app.post("/api/ai/test")
async def test_ai_connection(body: dict[str, Any] | None = None) -> dict[str, Any]:
    """Test AI provider connection with a simple prompt."""
    server_state = get_state()

    test_prompt = "Respond with: AI_SUPPORT is working."
    if body and "prompt" in body:
        test_prompt = body["prompt"]

    result = await server_state.real_agent.generate_response(
        message=test_prompt,
        session_id="test_session",
        trace_id=f"test_{uuid.uuid4().hex[:8]}",
    )

    return result


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "interfaces.server.main:app",
        host=HOST,
        port=PORT,
        log_level=LOG_LEVEL.lower(),
        reload=False,
    )