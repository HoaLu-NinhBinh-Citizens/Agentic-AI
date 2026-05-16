"""TUI screens module."""

from typing import Any


class Screen:
    """Base screen class."""
    
    async def render(self) -> str:
        """Render screen."""
        return ""


class HomeScreen(Screen):
    """Home screen."""
    
    async def render(self) -> str:
        return "AI_support Home"
