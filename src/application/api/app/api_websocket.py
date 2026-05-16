"""WebSocket handler for the CARV API server."""
import logging
import time

from fastapi import WebSocket, WebSocketDisconnect

from src.application.api.app.api_state import state

logger = logging.getLogger(__name__)


async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates."""
    await websocket.accept()
    state.websocket_connections.append(websocket)

    state.add_log("info", "WebSocket", "New client connected")

    await websocket.send_json({
        "type": "connection",
        "data": {
            "status": "connected",
            "uptime": state.uptime,
        }
    })

    await websocket.send_json({
        "type": "metric_update",
        "data": state._metrics,
    })

    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"type": "pong", "data": {"timestamp": time.time()}})
            elif data.startswith("subscribe:"):
                channel = data.split(":", 1)[1]
                await websocket.send_json({
                    "type": "subscribed",
                    "data": {"channel": channel}
                })
    except WebSocketDisconnect:
        try:
            state.websocket_connections.remove(websocket)
        except ValueError:
            pass
        state.add_log("info", "WebSocket", "Client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        try:
            state.websocket_connections.remove(websocket)
        except ValueError:
            pass
