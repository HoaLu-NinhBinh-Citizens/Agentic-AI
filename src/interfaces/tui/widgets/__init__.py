"""TUI widgets module."""

from typing import Any


class Widget:
    """Base widget class."""
    
    def render(self) -> str:
        """Render widget."""
        return ""


class TextWidget(Widget):
    """Text display widget."""
    
    def __init__(self, text: str):
        self.text = text
    
    def render(self) -> str:
        return self.text
