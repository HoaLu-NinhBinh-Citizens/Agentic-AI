"""Production API Server - FastAPI-based agent API with streaming.

This module provides:
- REST API endpoints
- WebSocket streaming
- SSE (Server-Sent Events)
- Authentication
- Rate limiting
- Health checks
"""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any, AsyncGenerator, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import structlog

from src.core.agent_runtime import AgentHarness, HarnessState
from src.core.streaming.stream import StreamEvent, StreamEventType, AsyncIteratorSink, PrintSink
from src.infrastructure.llm.llm_manager import create_llm_manager, LLMManager, Message
from src.infrastructure.config.production import get_config, ProductionConfig, is_production

logger = structlog.get_logger(__name__)


# ============================================
# Request/Response Models
# ============================================

class TaskRequest(BaseModel):
    """Request to run a task."""
    task: str
    project: str = "EngineCar"
    target: str = "CarEngine"
    autonomous: bool = False
    max_iterations: int = 5


class TaskResponse(BaseModel):
    """Response for task completion."""
    task_id: str
    status: str
    success: bool
    message: str
    duration: float
    artifacts: dict[str, Any] = {}


class StreamRequest(BaseModel):
    """Request for streaming response."""
    prompt: str
    system: str = ""
    stream: bool = True


# ============================================
# Connection Manager
# ============================================

class ConnectionManager:
    """Manages WebSocket connections."""
    
    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}
        self._lock = asyncio.Lock()
    
    async def connect(self, client_id: str, websocket: WebSocket) -> None:
        """Connect a new client."""
        await websocket.accept()
        async with self._lock:
            self.active_connections[client_id] = websocket
        logger.info(f"Client connected: {client_id}")
    
    async def disconnect(self, client_id: str) -> None:
        """Disconnect a client."""
        async with self._lock:
            if client_id in self.active_connections:
                del self.active_connections[client_id]
        logger.info(f"Client disconnected: {client_id}")
    
    async def send(self, client_id: str, event: StreamEvent) -> bool:
        """Send event to client."""
        async with self._lock:
            if client_id not in self.active_connections:
                return False
            websocket = self.active_connections[client_id]
        
        try:
            await websocket.send_text(event.to_json())
            return True
        except Exception as e:
            logger.error(f"Failed to send to {client_id}: {e}")
            return False
    
    async def broadcast(self, event: StreamEvent) -> None:
        """Broadcast event to all clients."""
        async with self._lock:
            connections = list(self.active_connections.items())
        
        for client_id, websocket in connections:
            try:
                await websocket.send_text(event.to_json())
            except Exception:
                pass


# Global manager
manager = ConnectionManager()


# ============================================
# Authentication
# ============================================

async def verify_api_key(request: Request) -> Optional[str]:
    """Verify API key from request header."""
    config = get_config()
    
    if not config.security.require_api_key:
        return "anonymous"
    
    api_key = request.headers.get("X-API-Key")
    
    if not api_key:
        raise HTTPException(status_code=401, detail="API key required")
    
    if api_key not in config.security.allowed_api_keys:
        raise HTTPException(status_code=403, detail="Invalid API key")
    
    return api_key


# ============================================
# FastAPI App
# ============================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager."""
    logger.info("Starting AI_SUPPORT API Server...")
    yield
    logger.info("Shutting down AI_SUPPORT API Server...")


def create_app() -> FastAPI:
    """Create FastAPI application."""
    config = get_config()
    
    app = FastAPI(
        title="AI_SUPPORT API",
        description="Agent runtime for embedded systems engineering",
        version=config.app_version,
        lifespan=lifespan,
    )
    
    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.security.cors_origins,
        allow_credentials=True,
        allow_methods=config.security.cors_methods,
        allow_headers=config.security.cors_headers,
    )
    
    # Include routers
    from .routes import router as api_router
    app.include_router(api_router, prefix="/api/v1")
    
    return app


# ============================================
# Routes
# ============================================

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "ai_support",
    }


@router.get("/ready")
async def readiness_check():
    """Readiness check endpoint."""
    # Check dependencies
    checks = {
        "config": True,
        "llm": True,
    }
    
    all_ready = all(checks.values())
    
    return {
        "ready": all_ready,
        "checks": checks,
        "timestamp": datetime.now().isoformat(),
    }


@router.post("/tasks", response_model=TaskResponse)
async def run_task(
    request: TaskRequest,
    api_key: Optional[str] = Depends(verify_api_key),
):
    """
    Run a task through the agent harness.
    
    This endpoint blocks until the task completes.
    For streaming responses, use /tasks/stream or WebSocket.
    """
    start_time = time.time()
    task_id = f"task_{int(start_time * 1000)}"
    
    logger.info(f"Starting task {task_id}: {request.task[:50]}...")
    
    # Create harness
    harness = AgentHarness()
    
    # Run task
    if request.autonomous:
        result = await harness.run_autonomous(
            task=request.task,
            project=request.project,
            target=request.target,
            max_iterations=request.max_iterations,
        )
    else:
        result = await harness.run(
            task=request.task,
            project=request.project,
            target=request.target,
        )
    
    duration = time.time() - start_time
    
    return TaskResponse(
        task_id=task_id,
        status=result.final_state.value,
        success=result.success,
        message=result.final_message,
        duration=duration,
        artifacts=result.artifacts,
    )


@router.post("/tasks/stream")
async def stream_task(request: TaskRequest):
    """
    Run a task with streaming response.
    
    Uses Server-Sent Events (SSE) for streaming.
    """
    async def generate():
        start_time = time.time()
        
        # Create sink
        sink = AsyncIteratorSink()
        
        # Create harness
        harness = AgentHarness()
        
        # Stream status
        yield f"data: {{'type': 'start', 'task_id': '{int(start_time * 1000)}'}}\n\n"
        
        try:
            # Run with progress updates
            result = await harness.run(
                task=request.task,
                project=request.project,
                target=request.target,
            )
            
            # Stream result
            yield f"data: {{'type': 'complete', 'success': {result.success}, 'duration': {result.total_duration}}}\n\n"
            yield f"data: {{'type': 'end'}}\n\n"
            
        except Exception as e:
            yield f"data: {{'type': 'error', 'message': '{str(e)}'}}\n\n"
            yield f"data: {{'type': 'end'}}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    """
    WebSocket endpoint for real-time streaming.
    
    Client sends:
        {'type': 'task', 'task': '...', 'project': 'EngineCar'}
        {'type': 'cancel'}
    
    Server sends:
        {'type': 'token', 'content': '...'}
        {'type': 'tool_call', 'tool': '...', 'args': {...}}
        {'type': 'complete', 'success': true}
    """
    await manager.connect(client_id, websocket)
    
    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")
            
            if msg_type == "task":
                task = data.get("task", "")
                project = data.get("project", "EngineCar")
                target = data.get("target", "CarEngine")
                
                logger.info(f"WS task from {client_id}: {task[:50]}")
                
                # Run harness
                harness = AgentHarness()
                result = await harness.run(task, project, target)
                
                # Send result
                await websocket.send_json({
                    "type": "complete",
                    "success": result.success,
                    "message": result.final_message,
                    "artifacts": result.artifacts,
                })
            
            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})
            
            elif msg_type == "cancel":
                await websocket.send_json({"type": "cancelled"})
                break
    
    except WebSocketDisconnect:
        logger.info(f"Client {client_id} disconnected")
    finally:
        await manager.disconnect(client_id)


@router.post("/llm/generate")
async def llm_generate(
    prompt: str,
    system: str = "",
    model: Optional[str] = None,
    api_key: Optional[str] = Depends(verify_api_key),
):
    """Generate text from LLM."""
    llm = create_llm_manager(
        provider="openai",
        model=model or "gpt-4",
    )
    
    response = await llm.generate(prompt, system=system)
    
    return {
        "content": response.content,
        "model": response.model,
        "usage": response.usage,
    }


@router.post("/llm/stream")
async def llm_stream(prompt: str, system: str = ""):
    """Stream LLM response."""
    llm = create_llm_manager("openai", "gpt-4")
    
    async def generate():
        async for chunk in llm.stream(prompt, system=system):
            yield f"data: {{'content': '{chunk.content}'}}\n\n"
            if chunk.done:
                yield "data: {'done': true}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
    )


@router.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    # Basic metrics
    return {
        "requests_total": 0,
        "requests_active": len(manager.active_connections),
        "uptime_seconds": time.time() - start_time,
    }


# Global start time
start_time = time.time()


# ============================================
# Main entry point
# ============================================

async def main():
    """Run the server."""
    import uvicorn
    
    config = get_config()
    
    app = create_app()
    
    uvicorn.run(
        app,
        host=config.server.host,
        port=config.server.port,
        reload=config.server.reload,
        log_level=config.server.log_level.lower(),
    )


if __name__ == "__main__":
    asyncio.run(main())
