"""Mock agent for Phase 1B.

This module provides a streaming mock agent that responds character by character.
Supports cancellation via asyncio.Event.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Awaitable, Callable

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class MockAgent:
    """Mock agent that streams character-by-character responses.

    This is a deterministic mock for testing purposes.
    Each character is sent as a separate token with a 50ms delay.
    Supports cancellation via cancellation_event.
    """

    async def stream_response(
        self,
        message: str,
        send_event: Callable[[dict], Awaitable[None]],
        cancellation_event: asyncio.Event | None = None,
    ) -> None:
        """Stream a response by sending each character as a token.

        Args:
            message: The message to respond to.
            send_event: Callback to send events to the client.
            cancellation_event: Optional event to check for cancellation.
        """
        try:
            if not message:
                await send_event({
                    "type": "done",
                    "data": {"success": True},
                })
                return

            for i, ch in enumerate(message):
                if cancellation_event and cancellation_event.is_set():
                    await send_event({
                        "type": "cancelled",
                        "data": {},
                    })
                    logger.debug("Stream cancelled")
                    return

                event = {
                    "type": "token",
                    "data": {
                        "content": ch,
                        "is_last": i == len(message) - 1,
                    },
                }
                await send_event(event)
                await asyncio.sleep(0.05)

            if cancellation_event and cancellation_event.is_set():
                return

            await send_event({
                "type": "done",
                "data": {"success": True},
            })
        except Exception as e:
            logger.error("Error in mock agent: %s", e)
            await send_event({
                "type": "error",
                "data": {
                    "code": "INTERNAL_ERROR",
                    "message": str(e),
                },
            })
