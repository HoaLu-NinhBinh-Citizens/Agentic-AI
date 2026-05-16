"""ToolCallAccumulator for handling partial JSON arguments during streaming.

When LLM providers stream tool calls, the arguments may be delivered in multiple
chunks. This accumulator buffers these chunks and parses the complete JSON
only when the stream ends.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from .provider import ToolCall

logger = logging.getLogger(__name__)


@dataclass
class ToolCallBuffer:
    """Buffer for accumulating a single tool call."""

    call_id: str = ""
    function_name: str = ""
    arguments_str: str = ""
    started: bool = False

    def is_complete(self) -> bool:
        """Check if arguments are complete (valid JSON)."""
        if not self.arguments_str:
            return False
        try:
            json.loads(self.arguments_str)
            return True
        except json.JSONDecodeError:
            return False

    def to_tool_call(self, index: int) -> ToolCall | None:
        """Convert buffer to ToolCall if complete.

        Args:
            index: The index of this tool call in the response.

        Returns:
            ToolCall if arguments are valid JSON, None otherwise.
        """
        if not self.function_name:
            return None
        try:
            args = json.loads(self.arguments_str) if self.arguments_str else {}
            return ToolCall(
                id=self.call_id or f"call_{index}",
                name=self.function_name,
                arguments=args,
            )
        except json.JSONDecodeError as e:
            logger.warning(
                "Failed to parse tool call arguments: %s",
                str(e),
                extra={"function_name": self.function_name, "arguments": self.arguments_str[:100]},
            )
            return None


class ToolCallAccumulator:
    """Accumulates streaming tool call chunks into complete ToolCall objects.

    Handles partial JSON arguments that arrive in multiple chunks during streaming.
    """

    def __init__(self) -> None:
        """Initialize the accumulator."""
        self._buffers: dict[int, ToolCallBuffer] = {}
        self._finalized: list[ToolCall] = []
        self._is_finalized: bool = False

    def add_token(self, content: str) -> None:
        """Add a text token to the accumulator.

        This is for text content, not tool calls.

        Args:
            content: Text content from the stream.
        """
        pass

    def add_tool_call_start(
        self,
        index: int,
        call_id: str,
        function_name: str,
    ) -> None:
        """Record the start of a tool call.

        Args:
            index: Index of the tool call (0-based).
            call_id: Unique identifier for this call.
            function_name: Name of the function to call.
        """
        if self._is_finalized:
            logger.warning("Attempted to add tool call after finalization")
            return

        if index not in self._buffers:
            self._buffers[index] = ToolCallBuffer()

        buf = self._buffers[index]
        buf.started = True
        buf.call_id = call_id
        buf.function_name = function_name

    def add_tool_call_delta(
        self,
        index: int,
        call_id: str | None = None,
        function_name: str | None = None,
        arguments: str = "",
    ) -> None:
        """Add a delta update to a tool call's arguments.

        Args:
            index: Index of the tool call (0-based).
            call_id: Optional call ID (may come in first delta).
            function_name: Optional function name (may come in first delta).
            arguments: Partial argument string (may be incomplete JSON).
        """
        if self._is_finalized:
            logger.warning("Attempted to add delta after finalization")
            return

        if index not in self._buffers:
            self._buffers[index] = ToolCallBuffer()

        buf = self._buffers[index]
        buf.started = True

        if call_id and not buf.call_id:
            buf.call_id = call_id
        if function_name and not buf.function_name:
            buf.function_name = function_name

        buf.arguments_str += arguments

    def add_chunk(self, chunk: dict[str, Any]) -> None:
        """Add a raw chunk from the provider stream.

        Normalizes different provider formats to internal events.

        Args:
            chunk: Raw chunk dict from provider.
        """
        chunk_type = chunk.get("type", "")

        if chunk_type == "tool_call_delta":
            self.add_tool_call_delta(
                index=chunk.get("index", 0),
                call_id=chunk.get("call_id"),
                function_name=chunk.get("function", {}).get("name"),
                arguments=chunk.get("function", {}).get("arguments", ""),
            )
        elif chunk_type == "tool_call_start":
            self.add_tool_call_start(
                index=chunk.get("index", 0),
                call_id=chunk.get("call_id", ""),
                function_name=chunk.get("function", {}).get("name", ""),
            )
        elif chunk_type == "token":
            self.add_token(chunk.get("content", ""))

    def get_in_progress_calls(self) -> list[tuple[int, ToolCallBuffer]]:
        """Get all tool calls currently being accumulated.

        Returns:
            List of (index, buffer) tuples for in-progress calls.
        """
        return [(i, buf) for i, buf in self._buffers.items() if buf.started]

    def finalize(self) -> list[ToolCall]:
        """Finalize and return all accumulated tool calls.

        Returns:
            List of complete ToolCall objects.
        """
        if self._is_finalized:
            return self._finalized

        self._is_finalized = True
        self._finalized = []

        for index in sorted(self._buffers.keys()):
            buf = self._buffers[index]
            tool_call = buf.to_tool_call(index)
            if tool_call:
                self._finalized.append(tool_call)
            elif buf.started:
                logger.warning(
                    "Skipping malformed tool call at index %d: function=%s, args=%s",
                    index,
                    buf.function_name,
                    buf.arguments_str[:100] + "..." if len(buf.arguments_str) > 100 else buf.arguments_str,
                )

        return self._finalized

    def get_final_calls(self) -> list[ToolCall]:
        """Get final tool calls (alias for finalize).

        Returns:
            List of complete ToolCall objects.
        """
        return self.finalize()

    def has_tool_calls(self) -> bool:
        """Check if any tool calls have been started.

        Returns:
            True if at least one tool call has been started.
        """
        return any(buf.started for buf in self._buffers.values())

    def reset(self) -> None:
        """Reset the accumulator for reuse."""
        self._buffers.clear()
        self._finalized.clear()
        self._is_finalized = False

    @property
    def buffer_count(self) -> int:
        """Get number of tool call buffers.

        Returns:
            Number of buffers being maintained.
        """
        return len(self._buffers)

    @property
    def finalized_count(self) -> int:
        """Get number of finalized tool calls.

        Returns:
            Number of tool calls that have been finalized.
        """
        return len(self._finalized)
