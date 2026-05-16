"""TUI state module."""

from typing import Any


class TUIState:
    """TUI application state."""
    
    def __init__(self):
        self.current_screen: str = "home"
        self.data: dict[str, Any] = {}
