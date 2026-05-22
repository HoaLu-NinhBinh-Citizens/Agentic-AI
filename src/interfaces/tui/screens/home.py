"""Home screen for TUI (Phase 7)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class HomeScreen:
    """Minimal home screen state."""

    title: str = "AI_SUPPORT"
    status: str = "Ready"

    def render(self) -> str:
        lines = [
            f"=== {self.title} ===",
            f"Status: {self.status}",
            "",
            "Commands: health | debug | flash | trace",
            "Press Ctrl+C to exit",
        ]
        return "\n".join(lines)
