"""Server state management for the CARV API server."""
import asyncio
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional, Any

from fastapi import WebSocket

from src.application.api.app.api_models import LogEntry, ToolStatus

logger = logging.getLogger(__name__)


class ServerState:
    """Shared state for the server."""

    def __init__(self):
        self.agent: Optional[Any] = None
        self.start_time: float = time.time()
        self.task_count: int = 0
        self.success_count: int = 0
        self.error_count: int = 0
        self.logs: List[LogEntry] = []
        self.max_logs: int = 500
        self.websocket_connections: List[WebSocket] = []
        self._metrics: Dict[str, float] = {
            "cpu": 0.0,
            "memory": 0.0,
            "speed": 0.0,
            "temperature": 0.0,
        }
        self._tool_statuses: Dict[str, ToolStatus] = {}

    @property
    def uptime(self) -> float:
        return time.time() - self.start_time

    def add_log(self, level: str, source: str, message: str):
        entry = LogEntry(
            level=level,
            source=source,
            message=message,
            timestamp=datetime.now().isoformat()
        )
        self.logs.append(entry)
        if len(self.logs) > self.max_logs:
            self.logs = self.logs[-self.max_logs:]
        return entry

    def update_metrics(self, metrics: Dict[str, float]):
        """Update metrics synchronously."""
        self._metrics.update(metrics)
        # Broadcast only if event loop is running
        try:
            loop = asyncio.get_running_loop()
            loop.call_soon(lambda: asyncio.create_task(self.broadcast({"type": "metric_update", "data": metrics})))
        except RuntimeError:
            pass  # No event loop in sync context

    def update_tool_status(self, tool: str, status: str, latency: int):
        """Update tool status synchronously."""
        self._tool_statuses[tool] = ToolStatus(tool=tool, status=status, latency=latency)
        # Broadcast only if event loop is running
        try:
            loop = asyncio.get_running_loop()
            loop.call_soon(lambda: asyncio.create_task(self.broadcast({
                "type": "tool_status",
                "data": {"tool": tool, "status": status, "latency": latency}
            })))
        except RuntimeError:
            pass  # No event loop in sync context

    async def broadcast(self, message: Dict):
        """Send message to all connected WebSocket clients."""
        disconnected = []
        connections = list(self.websocket_connections)
        for ws in connections:
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            try:
                self.websocket_connections.remove(ws)
            except ValueError:
                pass


state = ServerState()
