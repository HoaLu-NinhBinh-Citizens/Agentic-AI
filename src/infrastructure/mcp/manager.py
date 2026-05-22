"""MCP Client Manager for spawning and managing MCP server subprocesses.

Phase 2A provides:
- Spawning MCP servers via stdio subprocesses
- MCP session initialization handshake
- Tool discovery from connected servers
- Global namespaced tool registry

Phase 2B adds:
- Tool execution via call_tool method
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

import structlog

from infrastructure.mcp.config import MCPServerConfig, MCPConfigLoader
from infrastructure.resilience.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError
from shared.exceptions.tool_errors import ToolNotFoundError

logger = structlog.get_logger(__name__)


@dataclass
class ConnectedServer:
    """Represents a connected MCP server.

    Attributes:
        name: Server name from configuration.
        config: Original server configuration.
        process: The spawned subprocess.
        session: MCP ClientSession for communication.
        read_stream: Input stream from server.
        write_stream: Output stream to server.
        tools: List of tool definitions discovered from this server.
        stdio_context: The stdio context manager for cleanup.
    """

    name: str
    config: MCPServerConfig
    process: asyncio.subprocess.Process
    session: Any
    read_stream: Any
    write_stream: Any
    tools: list[dict] = field(default_factory=list)
    stdio_context: Any = None


class ToolInfo(dict):
    """Tool information with metadata.

    Keys:
        server: Name of the server providing this tool.
        original_name: Original tool name from the server.
        definition: Full tool definition dictionary.
    """

    def __init__(self, server: str, original_name: str, definition: dict) -> None:
        super().__init__(
            server=server,
            original_name=original_name,
            definition=definition,
        )


class MCPClientManager:
    """Manages MCP server lifecycle and tool registry.

    Responsibilities:
    - Load MCP server configurations
    - Spawn enabled servers as stdio subprocesses
    - Perform MCP initialization handshake
    - Discover tools from each server
    - Build global namespaced tool registry
    - Graceful shutdown of all servers

    Phase 2A Scope:
    - Only stdio transport supported
    - No tool execution (call_tool)
    - No retries or recovery
    - In-memory tool registry only

    Attributes:
        config_path: Path to servers.yaml configuration file.
    """

    INITIALIZE_TIMEOUT = 60.0
    LIST_TOOLS_TIMEOUT = 30.0

    def __init__(self, config_path: str = "configs/mcp/servers.yaml") -> None:
        """Initialize the MCP client manager.

        Args:
            config_path: Path to the MCP servers configuration file.
        """
        self._config_path = config_path
        self._config_loader = MCPConfigLoader(config_path)
        self._servers: dict[str, ConnectedServer] = {}
        self._global_tools: dict[str, ToolInfo] = {}
        self._initialized = False
        
        # FIX: Add circuit breakers for each server
        self._server_breakers: dict[str, CircuitBreaker] = {}

    async def initialize(self) -> None:
        """Initialize all enabled MCP servers.

        Loads configuration, spawns servers, performs handshake,
        discovers tools, and builds the global tool registry.

        Raises:
            RuntimeError: If called more than once, or if no server can be started.
        """
        if self._initialized:
            logger.warning("MCPClientManager already initialized, skipping")
            return

        logger.info("Initializing MCP client manager")
        config = self._config_loader.load()
        enabled_servers = [s for s in config.servers if s.enabled]

        if not enabled_servers:
            logger.info("No enabled MCP servers in configuration")
            self._initialized = True
            return

        for server_config in enabled_servers:
            await self._start_server(server_config)

        if not self._servers:
            raise RuntimeError(
                "No MCP servers could be started. "
                "Check that required commands (npx, uvx) are installed."
            )

        self._initialized = True
        logger.info(
            "MCP client manager initialized",
            servers_count=len(self._servers),
            total_tools=len(self._global_tools),
        )

    async def _start_server(self, config: MCPServerConfig) -> None:
        """Start a single MCP server.

        Steps:
        1. Spawn subprocess with stdio transport
        2. Create MCP session
        3. Perform initialize handshake (30s timeout)
        4. Discover tools (30s timeout)
        5. Normalize and namespace tool names
        6. Add to global registry

        Args:
            config: Server configuration.
        """
        name = config.name
        command = config.command

        logger.info(
            "Starting MCP server",
            server=name,
            command=command,
            args=config.args,
        )

        read_stream = None
        write_stream = None
        session = None
        stdio_context = None

        try:
            # Step 1: Import MCP SDK and spawn subprocess
            from mcp import ClientSession
            from mcp.client.stdio import stdio_client, StdioServerParameters

            params = StdioServerParameters(command=config.command, args=config.args)

            # Enter async context manager to get streams
            stdio_context = stdio_client(params)
            read_stream, write_stream = await stdio_context.__aenter__()

            # Create and initialize session
            session = ClientSession(read_stream, write_stream)

            # Step 2: Initialize handshake with timeout
            await asyncio.wait_for(session.initialize(), timeout=self.INITIALIZE_TIMEOUT)
            logger.info("MCP server handshake complete", server=name)

            # Step 3: Discover tools with timeout
            result = await asyncio.wait_for(session.list_tools(), timeout=self.LIST_TOOLS_TIMEOUT)
            tools = [tool.model_dump() for tool in result.tools]
            logger.info(
                "Discovered tools from MCP server",
                server=name,
                tools_count=len(tools),
            )

            # Step 4: Normalize and namespace tools
            for tool_def in tools:
                original_name = tool_def.get("name", "")
                # Replace / and - with _ to avoid namespace issues
                normalized_name = original_name.replace("/", "_").replace("-", "_")
                namespaced_name = f"{name}/{normalized_name}"

                if namespaced_name in self._global_tools:
                    logger.warning(
                        "Tool name collision, keeping first",
                        server=name,
                        tool=namespaced_name,
                        existing_server=self._global_tools[namespaced_name]["server"],
                    )
                    continue

                self._global_tools[namespaced_name] = ToolInfo(
                    server=name,
                    original_name=original_name,
                    definition=tool_def,
                )

            # Step 5: Store connected server (keep context manager open)
            self._servers[name] = ConnectedServer(
                name=name,
                config=config,
                process=None,
                session=session,
                read_stream=read_stream,
                write_stream=write_stream,
                tools=tools,
                stdio_context=stdio_context,
            )
            
            # FIX: Create circuit breaker for this server
            self._server_breakers[name] = CircuitBreaker(
                name=f"mcp_{name}",
                failure_threshold=3,
                window_seconds=60,
                timeout_seconds=30,
            )

            logger.info(
                "MCP server started successfully",
                server=name,
                tools_count=len(tools),
            )

        except asyncio.TimeoutError:
            logger.error(
                "MCP server initialization timed out",
                server=name,
                timeout=self.INITIALIZE_TIMEOUT,
            )
            await self._cleanup_server(
                name, session, read_stream, write_stream, stdio_context
            )

        except ImportError as e:
            logger.error(
                "MCP SDK import failed, ensure 'mcp' package is installed",
                server=name,
                error=str(e),
            )
            await self._cleanup_server(
                name, session, read_stream, write_stream, stdio_context
            )

        except Exception as e:
            logger.error(
                "MCP server failed to start",
                server=name,
                error=str(e),
                error_type=type(e).__name__,
            )
            await self._cleanup_server(
                name, session, read_stream, write_stream, stdio_context
            )

    async def _cleanup_server(
        self,
        name: str,
        session: Any,
        read_stream: Any,
        write_stream: Any,
        stdio_context: Any,
    ) -> None:
        """Clean up resources for a failed or shutting down server.

        Args:
            name: Server name.
            session: MCP session (unused, kept for compatibility).
            read_stream: Input stream to close.
            write_stream: Output stream to close.
            stdio_context: The async context manager to exit.
        """
        # FIX: Log cleanup errors instead of silently swallowing them
        try:
            if write_stream is not None:
                await write_stream.aclose()
        except Exception as e:
            logger.warning(f"Failed to close write stream for {name}: {e}")

        try:
            if read_stream is not None:
                await read_stream.aclose()
        except Exception as e:
            logger.warning(f"Failed to close read stream for {name}: {e}")

        try:
            if stdio_context is not None:
                await stdio_context.__aexit__(None, None, None)
        except Exception as e:
            logger.warning(f"Failed to cleanup stdio context for {name}: {e}")

        self._servers.pop(name, None)

    async def list_tools(self) -> dict[str, ToolInfo]:
        """Return a copy of the global tool registry.

        Returns:
            Dictionary mapping namespaced tool names to ToolInfo.
        """
        return self._global_tools.copy()

    def is_ready(self) -> bool:
        """Check if the manager is initialized.

        Returns True after successful initialization, even if no servers
        are connected (e.g., all servers are disabled).

        Returns:
            True if initialization completed successfully.
        """
        return self._initialized

    async def call_tool(self, tool_name: str, arguments: dict) -> Any:
        """Call an MCP tool by namespaced name.

        Phase 2B: Implements tool execution via MCP.

        Args:
            tool_name: Namespaced tool name (e.g., 'filesystem/read_file').
            arguments: Tool input arguments.

        Returns:
            Tool result from the MCP server.

        Raises:
            ToolNotFoundError: If tool doesn't exist.
            RuntimeError: If MCP manager is not initialized.
            Exception: Any error from the MCP server.
        """
        if not self._initialized:
            raise RuntimeError("MCP manager not initialized")

        tool_info = self._global_tools.get(tool_name)
        if not tool_info:
            raise ToolNotFoundError(f"Tool not found: {tool_name}")

        server_name = tool_info["server"]
        original_name = tool_info["original_name"]

        server = self._servers.get(server_name)
        if not server or not server.session:
            # FIX: Check circuit breaker before failing
            breaker = self._server_breakers.get(server_name)
            if breaker:
                breaker.record_failure()
                raise RuntimeError(
                    f"Server not connected: {server_name}. "
                    f"Circuit breaker state: {breaker.state.value}"
                )
            raise RuntimeError(f"Server not connected: {server_name}")

        logger.debug(
            "Calling MCP tool",
            tool_name=tool_name,
            original_name=original_name,
            server=server_name,
        )

        try:
            result = await server.session.call_tool(original_name, arguments)
            # Record success in circuit breaker
            breaker = self._server_breakers.get(server_name)
            if breaker:
                breaker.record_success()
            return result
        except Exception as e:
            # Record failure in circuit breaker
            breaker = self._server_breakers.get(server_name)
            if breaker:
                breaker.record_failure()
            raise

    async def shutdown(self) -> None:
        """Gracefully shut down all MCP servers.

        Closes all sessions and terminates subprocesses.
        Never raises exceptions - logs errors and continues.
        """
        if not self._initialized:
            return

        logger.info("Shutting down MCP client manager", servers_count=len(self._servers))

        for name, server in list(self._servers.items()):
            try:
                # Close write stream first, then read stream
                if server.write_stream is not None:
                    try:
                        await server.write_stream.aclose()
                    except Exception:
                        pass
                if server.read_stream is not None:
                    try:
                        await server.read_stream.aclose()
                    except Exception:
                        pass
                # Exit the stdio context manager to terminate the subprocess
                if server.stdio_context is not None:
                    try:
                        await server.stdio_context.__aexit__(None, None, None)
                    except Exception:
                        pass
                logger.debug("Closed MCP server", server=name)
            except Exception as e:
                logger.debug(
                    "Error closing MCP server",
                    server=name,
                    error=str(e),
                )

        self._servers.clear()
        self._global_tools.clear()
        self._initialized = False

        logger.info("MCP client manager shutdown complete")
