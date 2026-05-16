"""WebSocket manager for real-time dashboard events."""
import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class EventChannel(str, Enum):
    """Dashboard event channels."""
    OVERVIEW = "overview"
    WORKFLOWS = "workflows"
    HARDWARE = "hardware"
    METRICS = "metrics"
    TIMELINE = "timeline"
    ALERTS = "alerts"
    ALL = "all"


@dataclass
class DashboardEvent:
    """A dashboard event."""
    channel: EventChannel
    event_type: str
    data: Dict[str, Any]
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    event_id: str = ""


class DashboardWebSocketManager:
    """
    WebSocket manager for real-time dashboard updates.
    
    Features:
    - Multi-channel subscriptions
    - Event broadcasting
    - Heartbeat/ping support
    - Automatic reconnection handling
    
    Usage:
        manager = DashboardWebSocketManager()
        await manager.connect(websocket)
        await manager.broadcast(EventChannel.OVERVIEW, "update", {"status": "ready"})
    """

    def __init__(self):
        self._connections: Dict[WebSocket, Set[EventChannel]] = {}
        self._event_handlers: Dict[str, List[Callable]] = {}
        self._last_events: Dict[EventChannel, DashboardEvent] = {}
        self._heartbeat_interval: float = 30.0
        self._running = False

    @property
    def connections(self) -> int:
        """Get number of active connections."""
        return len(self._connections)

    @property
    def channels(self) -> Dict[str, int]:
        """Get subscription count per channel."""
        counts = {ch.value: 0 for ch in EventChannel if ch != EventChannel.ALL}
        for ws, channels in self._connections.items():
            for ch in channels:
                if ch != EventChannel.ALL:
                    counts[ch.value] = counts.get(ch.value, 0) + 1
        return counts

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        self._connections[websocket] = {EventChannel.ALL}
        
        logger.info(f"Dashboard WebSocket connected. Total: {self.connections}")
        
        await self._send_to_websocket(websocket, {
            "type": "connection",
            "data": {
                "status": "connected",
                "timestamp": datetime.now().isoformat(),
                "channels": list(EventChannel),
            }
        })
        
        await self._send_cached_events(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection."""
        if websocket in self._connections:
            del self._connections[websocket]
            logger.info(f"Dashboard WebSocket disconnected. Total: {self.connections}")

    async def subscribe(self, websocket: WebSocket, channel: EventChannel) -> None:
        """Subscribe a connection to a channel."""
        if websocket in self._connections:
            self._connections[websocket].add(channel)
            await self._send_to_websocket(websocket, {
                "type": "subscribed",
                "data": {"channel": channel.value}
            })

    async def unsubscribe(self, websocket: WebSocket, channel: EventChannel) -> None:
        """Unsubscribe a connection from a channel."""
        if websocket in self._connections:
            self._connections[websocket].discard(channel)
            await self._send_to_websocket(websocket, {
                "type": "unsubscribed",
                "data": {"channel": channel.value}
            })

    async def broadcast(
        self,
        channel: EventChannel,
        event_type: str,
        data: Dict[str, Any],
    ) -> None:
        """Broadcast an event to all subscribers of a channel."""
        event = DashboardEvent(
            channel=channel,
            event_type=event_type,
            data=data,
            event_id=f"{channel.value}_{int(time.time() * 1000)}",
        )
        
        self._last_events[channel] = event
        
        message = {
            "type": "event",
            "channel": channel.value,
            "event_type": event_type,
            "event_id": event.event_id,
            "timestamp": event.timestamp,
            "data": data,
        }
        
        await self._broadcast_to_channel(channel, message)
        
        for handler in self._event_handlers.get(event_type, []):
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as e:
                logger.error(f"Event handler error: {e}")

    async def send_to_all(self, message: Dict[str, Any]) -> None:
        """Send a message to all connected clients."""
        disconnected = []
        for ws in list(self._connections.keys()):
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.append(ws)
        
        for ws in disconnected:
            await self.disconnect(ws)

    def on_event(self, event_type: str, handler: Callable) -> None:
        """Register an event handler."""
        if event_type not in self._event_handlers:
            self._event_handlers[event_type] = []
        self._event_handlers[event_type].append(handler)

    async def start_heartbeat(self) -> None:
        """Start heartbeat task to keep connections alive."""
        self._running = True
        while self._running:
            await asyncio.sleep(self._heartbeat_interval)
            await self._send_heartbeat()

    async def stop_heartbeat(self) -> None:
        """Stop heartbeat task."""
        self._running = False

    async def _broadcast_to_channel(self, channel: EventChannel, message: Dict) -> None:
        """Send message to all clients subscribed to a channel."""
        disconnected = []
        
        for ws, channels in self._connections.items():
            if channel in channels or EventChannel.ALL in channels:
                try:
                    await ws.send_json(message)
                except Exception:
                    disconnected.append(ws)
        
        for ws in disconnected:
            await self.disconnect(ws)

    async def _send_to_websocket(self, websocket: WebSocket, message: Dict) -> None:
        """Send a message to a specific WebSocket."""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"Failed to send to WebSocket: {e}")
            await self.disconnect(websocket)

    async def _send_cached_events(self, websocket: WebSocket) -> None:
        """Send cached events for all channels to a new connection."""
        for channel, event in self._last_events.items():
            await self._send_to_websocket(websocket, {
                "type": "cached_event",
                "channel": channel.value,
                "event_type": event.event_type,
                "timestamp": event.timestamp,
                "data": event.data,
            })

    async def _send_heartbeat(self) -> None:
        """Send heartbeat/ping to all connections."""
        await self.send_to_all({
            "type": "heartbeat",
            "timestamp": datetime.now().isoformat(),
        })


# Dashboard-specific event helpers

async def broadcast_workflow_update(
    manager: DashboardWebSocketManager,
    workflow_id: str,
    status: str,
    details: Dict[str, Any],
) -> None:
    """Broadcast a workflow status update."""
    await manager.broadcast(
        EventChannel.WORKFLOWS,
        "workflow_update",
        {
            "workflow_id": workflow_id,
            "status": status,
            "details": details,
        }
    )


async def broadcast_hardware_status(
    manager: DashboardWebSocketManager,
    board_id: str,
    status: str,
    uart_data: Optional[List[str]] = None,
) -> None:
    """Broadcast hardware/HIL status update."""
    await manager.broadcast(
        EventChannel.HARDWARE,
        "hardware_status",
        {
            "board_id": board_id,
            "status": status,
            "uart_data": uart_data or [],
        }
    )


async def broadcast_metric_update(
    manager: DashboardWebSocketManager,
    metrics: Dict[str, float],
) -> None:
    """Broadcast metrics update."""
    await manager.broadcast(
        EventChannel.METRICS,
        "metric_update",
        metrics,
    )


async def broadcast_alert(
    manager: DashboardWebSocketManager,
    level: str,
    message: str,
    details: Dict[str, Any],
) -> None:
    """Broadcast an alert."""
    await manager.broadcast(
        EventChannel.ALERTS,
        "alert",
        {
            "level": level,
            "message": message,
            "details": details,
        }
    )


# Global dashboard WebSocket manager instance
_dashboard_manager: Optional[DashboardWebSocketManager] = None


def get_dashboard_manager() -> DashboardWebSocketManager:
    """Get the global dashboard WebSocket manager."""
    global _dashboard_manager
    if _dashboard_manager is None:
        _dashboard_manager = DashboardWebSocketManager()
    return _dashboard_manager
