"""TUI application (Phase 7)."""

from __future__ import annotations

import asyncio
import sys

from src.interfaces.tui.screens.home import HomeScreen
from src.interfaces.tui.widgets.status_bar import StatusBar

POLL_INTERVAL_S = 0.5


class TUIApp:
    """Terminal UI — lightweight status loop."""

    def __init__(self) -> None:
        self._running = False
        self._home = HomeScreen()
        self._status = StatusBar(message="ai-support tui")

    async def run(self, once: bool = False) -> None:
        self._running = True
        try:
            while self._running:
                self._render_frame()
                if once:
                    break
                await asyncio.sleep(POLL_INTERVAL_S)
        finally:
            self._running = False

    def _render_frame(self) -> None:
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.write(self._home.render())
        sys.stdout.write("\n")
        sys.stdout.write(self._status.render())
        sys.stdout.write("\n")
        sys.stdout.flush()

    def stop(self) -> None:
        self._running = False


async def main() -> int:
    app = TUIApp()
    await app.run(once=True)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
