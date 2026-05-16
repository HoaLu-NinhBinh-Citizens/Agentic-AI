"""Websocket schemas module."""

from typing import Any


class WebsocketMessage:
    """Websocket message schema."""
    
    @staticmethod
    def validate(data: dict[str, Any]) -> bool:
        """Validate websocket message."""
        return "type" in data
