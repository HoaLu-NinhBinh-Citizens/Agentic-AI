"""Tool executor abstraction and MCP implementation for Phase 2B/2C.

Provides the abstract interface for tool execution and the concrete
MCP-based implementation that calls MCP server tools.
Phase 2C: Adds capability model and process handle support.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ToolCapabilities:
    """Capabilities of a tool executor.

    Phase 2C: Declarative capabilities for routing and policy decisions.

    Attributes:
        cancellable: Whether the executor supports cancellation.
        streaming: Whether the executor supports streaming results.
        priority: Execution priority (higher = more urgent).
    """

    cancellable: bool = False
    streaming: bool = False
    priority: int = 0


class ToolExecutor(ABC):
    """Abstract base class for tool execution implementations.

    Concrete implementations handle the actual execution of tools,
    whether through MCP servers, local functions, or remote services.
    """

    def __init__(self) -> None:
        """Initialize the tool executor."""
        self._capabilities = ToolCapabilities()

    @abstractmethod
    async def execute(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute a tool with the given arguments.

        Args:
            tool_name: Name of the tool to execute.
            arguments: Tool input arguments as a dictionary.

        Returns:
            Raw result dictionary containing at minimum 'content' key
            with the tool's output.

        Raises:
            Exception: Any error during tool execution.
        """
        ...

    @property
    def capabilities(self) -> ToolCapabilities:
        """Return the capabilities of this executor."""
        return self._capabilities


class MCPToolExecutor(ToolExecutor):
    """MCP-based tool executor implementation.

    Executes tools by calling through the MCPClientManager which
    handles communication with MCP servers.

    Phase 2C: Supports cancellation tokens for true cancellation.
    """

    def __init__(self, mcp_manager: Any) -> None:
        """Initialize the MCP tool executor.

        Args:
            mcp_manager: MCPClientManager instance for making tool calls.
        """
        super().__init__()
        self._mcp_manager = mcp_manager
        self._capabilities.cancellable = True

    async def execute(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute a tool via MCP.

        Args:
            tool_name: Namespaced tool name (e.g., 'filesystem/read_file').
            arguments: Tool input arguments.

        Returns:
            Tool result as a dictionary with 'content' key.

        Raises:
            RuntimeError: If MCP manager is not initialized.
            Exception: Any error from the MCP server.
        """
        if self._mcp_manager is None:
            raise RuntimeError("MCP manager not available")

        if not self._mcp_manager.is_ready():
            raise RuntimeError("MCP manager not initialized")

        logger.debug(
            "Executing MCP tool",
            tool_name=tool_name,
            arguments_keys=list(arguments.keys()),
        )

        result = await self._mcp_manager.call_tool(tool_name, arguments)

        if hasattr(result, "model_dump"):
            return result.model_dump()

        return dict(result) if result else {"content": []}


class MockToolExecutor(ToolExecutor):
    """Mock executor for testing without real MCP servers.

    Provides simple responses based on tool name patterns.
    """

    def __init__(self) -> None:
        """Initialize the mock executor."""
        super().__init__()
        self._call_count = 0
        self._capabilities.cancellable = True
        self._capabilities.streaming = False
        self._capabilities.priority = 0

    async def execute(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute a mock tool.

        Returns mock responses based on tool name:
        - 'echo' tools: return arguments as content
        - 'fail' tools: raise an exception
        - 'timeout' tools: sleep for long time
        - Default: return generic success response

        Args:
            tool_name: Name of the mock tool.
            arguments: Tool arguments.

        Returns:
            Mock result dictionary.
        """
        self._call_count += 1

        if "fail" in tool_name.lower():
            raise RuntimeError(f"Mock failure for tool: {tool_name}")

        if "echo" in tool_name.lower():
            return {"content": [{"type": "text", "text": str(arguments)}]}

        if "timeout" in tool_name.lower():
            import asyncio
            await asyncio.sleep(60)
            return {"content": []}

        return {
            "content": [
                {"type": "text", "text": f"Mock result for {tool_name}"}
            ]
        }

    @property
    def call_count(self) -> int:
        """Return the number of calls made to this executor."""
        return self._call_count
