"""FastAPI server for CARV AI Support - provides REST API and WebSocket for frontend dashboard."""
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

_repo_root = Path(__file__).resolve().parents[2]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from src.application.api.app.agent_logging import agent_logging
logger = logging.getLogger(__name__)
from src.application.api.app.api_endpoints import (
    add_log,
    analyze_logs,
    create_task,
    export_logs,
    get_logs,
    get_metrics,
    get_status,
    get_tools,
    health_check,
    list_log_files,
    update_metrics,
    update_tool,
)
from src.application.api.app.api_models import (
    LogEntry,
    MetricUpdate,
    SystemStatus,
    TaskRequest,
    TaskResponse,
    ToolStatus,
)
from src.application.api.app.api_state import ServerState, state
from src.application.api.app.api_websocket import websocket_endpoint
from src.application.api.app.chat_endpoints import register_chat_endpoints, register_agent_v2_endpoints, register_reasoning_endpoints
from src.application.api.app.dashboard_api import (
    get_dashboard_overview,
    get_system_health,
    get_workflow_status,
    get_workflow_history,
    get_rollback_events,
    get_token_usage,
    get_context_usage,
    get_hardware_status,
    get_event_timeline,
    get_prometheus_metrics,
)

# Re-export for backwards compatibility
__all__ = [
    "app",
    "ServerState",
    "state",
    "LogEntry",
    "MetricUpdate",
    "SystemStatus",
    "TaskRequest",
    "TaskResponse",
    "ToolStatus",
]


def _get_cors_origins() -> list[str]:
    """Get CORS origins from environment variable or use defaults."""
    env_origins = os.environ.get("CORS_ORIGINS", "")
    if env_origins:
        return [o.strip() for o in env_origins.split(",") if o.strip()]
    return [
        "http://localhost:3001",
        "http://localhost:5173",
        "http://localhost:4173",
    ]


# ============================================================================
# LIFESPAN
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize agent on startup."""
    logger.info("Starting CARV API Server...")

    try:
        state.add_log("info", "Server", "API server starting...")
        state.add_log("info", "Server", "Ready. API server running at http://localhost:8766")
    except Exception as e:
        logger.error(f"Server startup issue: {e}")
        state.add_log("error", "Server", f"Server init issue: {e}")

    yield

    logger.info("Shutting down CARV API Server...")
    for ws in state.websocket_connections:
        try:
            await ws.close()
        except Exception:
            pass
    state.websocket_connections.clear()


# ============================================================================
# APP
# ============================================================================

app = FastAPI(
    title="CARV AI Support API",
    description="Backend API for the CARV embedded development dashboard",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register REST endpoints
app.add_api_route("/api/health", health_check, methods=["GET"])
app.add_api_route("/api/status", get_status, methods=["GET"], response_model=SystemStatus)
app.add_api_route("/api/metrics", get_metrics, methods=["GET"])
app.add_api_route("/api/metrics", update_metrics, methods=["POST"])
app.add_api_route("/api/logs", get_logs, methods=["GET"])
app.add_api_route("/api/logs", add_log, methods=["POST"])
app.add_api_route("/api/logs/export", export_logs, methods=["GET"])
app.add_api_route("/api/tools", get_tools, methods=["GET"])
app.add_api_route("/api/tools", update_tool, methods=["POST"])
app.add_api_route("/api/tasks", create_task, methods=["POST"], response_model=TaskResponse)
app.add_api_route("/api/logs/files", list_log_files, methods=["GET"])
app.add_api_route("/api/logs/analyze", analyze_logs, methods=["POST"])

# Register WebSocket
app.add_api_websocket_route("/ws/stream", websocket_endpoint)

# Register Dashboard endpoints
app.add_api_route("/api/dashboard/overview", get_dashboard_overview, methods=["GET"])
app.add_api_route("/api/dashboard/health", get_system_health, methods=["GET"])
app.add_api_route("/api/dashboard/workflows", get_workflow_status, methods=["GET"])
app.add_api_route("/api/dashboard/workflows/history", get_workflow_history, methods=["GET"])
app.add_api_route("/api/dashboard/rollbacks", get_rollback_events, methods=["GET"])
app.add_api_route("/api/dashboard/tokens", get_token_usage, methods=["GET"])
app.add_api_route("/api/dashboard/context", get_context_usage, methods=["GET"])
app.add_api_route("/api/dashboard/hardware", get_hardware_status, methods=["GET"])
app.add_api_route("/api/dashboard/timeline", get_event_timeline, methods=["GET"])
app.add_api_route("/api/dashboard/prometheus", get_prometheus_metrics, methods=["GET"])

# Call Graph endpoint
from src.application.api.app.dashboard_api import get_call_graph
app.add_api_route("/api/dashboard/callgraph", get_call_graph, methods=["GET"])

# Register Chat endpoints
register_chat_endpoints(app, get_agent_fn=lambda: state.agent)
register_agent_v2_endpoints(app, state)
register_reasoning_endpoints(app, get_agent_fn=lambda: state.agent)


# ============================================================================
# MAIN
# ============================================================================

def run_server(host: str = "0.0.0.0", port: int = 8766):
    """Run the FastAPI server."""
    import uvicorn
    uvicorn.run(
        "src.application.api.app.api_server:app",
        host=host,
        port=port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="CARV API Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8766, help="Port to bind to")
    args = parser.parse_args()

    run_server(host=args.host, port=args.port)
