"""Mock agent for Phase 1A.

This module provides a streaming mock agent that responds character by character.
Deterministic behavior with no cancellation or tool execution.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Awaitable, Callable

if TYPE_CHECKING:
    pass


class MockAgent:
    """Mock agent that streams character-by-character responses.

    This is a deterministic mock for testing purposes.
    Each character is sent as a separate token with a 50ms delay.
    """

    async def stream_response(
        self,
        message: str,
        send_event: Callable[[dict], Awaitable[None]],
    ) -> None:
        """Stream a response by sending each character as a token.

        Args:
            message: The message to respond to.
            send_event: Callback to send events to the client.
        """
        try:
            if not message:
                await send_event({
                    "type": "done",
                    "data": {"success": True},
                })
                return

            for i, ch in enumerate(message):
                event = {
                    "type": "token",
                    "data": {
                        "content": ch,
                        "is_last": i == len(message) - 1,
                    },
                }
                await send_event(event)
                await asyncio.sleep(0.05)

            await send_event({
                "type": "done",
                "data": {"success": True},
            })
        except Exception as e:
            await send_event({
                "type": "error",
                "data": {
                    "code": "INTERNAL_ERROR",
                    "message": str(e),
                },
            })
