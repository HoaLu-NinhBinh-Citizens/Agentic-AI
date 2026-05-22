"""Status bar widget for TUI."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class StatusBar:
    """Single-line status display."""

    message: str = ""

    def render(self, width: int = 80) -> str:
        text = self.message[: max(0, width - 1)]
        return text.ljust(width)[:width]
