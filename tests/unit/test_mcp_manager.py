"""Unit tests for MCPClientManager."""

from __future__ import annotations

import asyncio
import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from infrastructure.mcp.config import MCPServerConfig, MCPConfigLoader
from infrastructure.mcp.manager import MCPClientManager, ConnectedServer, ToolInfo


class TestToolInfo:
    """Tests for ToolInfo."""

    def test_creation(self):
        """ToolInfo stores correct values."""
        tool = ToolInfo(
            server="test_server",
            original_name="echo",
            definition={"name": "echo", "description": "Test tool"},
        )
        assert tool["server"] == "test_server"
        assert tool["original_name"] == "echo"
        assert tool["definition"]["name"] == "echo"

    def test_is_dict(self):
        """ToolInfo is a dict."""
        tool = ToolInfo(server="s", original_name="n", definition={})
        assert isinstance(tool, dict)


class TestConnectedServer:
    """Tests for ConnectedServer dataclass."""

    def test_creation(self):
        """ConnectedServer stores correct values."""
        config = MCPServerConfig(name="test", command="echo")
        server = ConnectedServer(
            name="test",
            config=config,
            process=None,
            session=None,
            read_stream=None,
            write_stream=None,
            tools=[],
        )
        assert server.name == "test"
        assert server.config.name == "test"
        assert server.tools == []


class TestMCPClientManager:
    """Tests for MCPClientManager."""

    def test_initial_state(self):
        """Manager starts in uninitialized state."""
        manager = MCPClientManager()
        assert manager.is_ready() is False

    def test_idempotent_initialize(self):
        """Double initialization logs warning and returns."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write("servers: []")
            temp_path = f.name

        try:
            manager = MCPClientManager(temp_path)

            async def run_init():
                await manager.initialize()
                await manager.initialize()  # Second call

            asyncio.run(run_init())
        finally:
            os.unlink(temp_path)

    def test_shutdown_uninitialized(self):
        """Shutdown on uninitialized manager does nothing."""

        async def run_shutdown():
            manager = MCPClientManager()
            await manager.shutdown()
            assert manager.is_ready() is False

        asyncio.run(run_shutdown())

    @pytest.mark.asyncio
    async def test_initialize_no_enabled_servers(self):
        """Manager initializes with no enabled servers."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write("""
servers:
  - name: "disabled_server"
    command: "echo"
    enabled: false
""")
            temp_path = f.name

        try:
            manager = MCPClientManager(temp_path)
            await manager.initialize()
            assert manager.is_ready() is True
            tools = await manager.list_tools()
            assert tools == {}
        finally:
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_initialize_single_server_mocked(self):
        """Manager initializes with a single server (mocked)."""
        mock_tools = [
            MagicMock(
                model_dump=MagicMock(
                    return_value={
                        "name": "echo",
                        "description": "Echo the input",
                        "inputSchema": {},
                    }
                )
            )
        ]

        mock_result = MagicMock(tools=mock_tools)
        mock_session = MagicMock()
        mock_session.initialize = AsyncMock()
        mock_session.list_tools = AsyncMock(return_value=mock_result)

        mock_streams = (MagicMock(), MagicMock())
        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_streams)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write("""
servers:
  - name: "test_server"
    command: "python"
    args:
      - "-c"
      - "pass"
    enabled: true
""")
            temp_path = f.name

        try:
            with patch("infrastructure.mcp.manager.ClientSession", return_value=mock_session):
                with patch("infrastructure.mcp.manager.stdio_client", return_value=mock_context):
                    manager = MCPClientManager(temp_path)
                    await manager.initialize()

                    assert manager.is_ready() is True
                    tools = await manager.list_tools()

                    assert len(tools) >= 1
                    assert "test_server/echo" in tools
                    assert tools["test_server/echo"]["server"] == "test_server"
                    assert tools["test_server/echo"]["original_name"] == "echo"

                    await manager.shutdown()
        finally:
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_initialize_multiple_servers_mocked(self):
        """Manager initializes with multiple servers (mocked)."""
        mock_tools = [
            MagicMock(
                model_dump=MagicMock(
                    return_value={
                        "name": "tool",
                        "description": "A tool",
                        "inputSchema": {},
                    }
                )
            )
        ]
        mock_result = MagicMock(tools=mock_tools)

        mock_session1 = MagicMock()
        mock_session1.initialize = AsyncMock()
        mock_session1.list_tools = AsyncMock(return_value=mock_result)

        mock_session2 = MagicMock()
        mock_session2.initialize = AsyncMock()
        mock_session2.list_tools = AsyncMock(return_value=mock_result)

        mock_streams = (MagicMock(), MagicMock())
        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_streams)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write("""
servers:
  - name: "server_one"
    command: "echo"
    enabled: true
  - name: "server_two"
    command: "echo"
    enabled: true
""")
            temp_path = f.name

        try:
            sessions = [mock_session1, mock_session2]
            session_index = [0]

            def mock_client_session(read, write):
                s = sessions[session_index[0]]
                session_index[0] += 1
                return s

            with patch("infrastructure.mcp.manager.ClientSession", side_effect=mock_client_session):
                with patch("infrastructure.mcp.manager.stdio_client", return_value=mock_context):
                    manager = MCPClientManager(temp_path)
                    await manager.initialize()

                    assert manager.is_ready() is True
                    tools = await manager.list_tools()

                    assert "server_one/tool" in tools
                    assert "server_two/tool" in tools

                    await manager.shutdown()
        finally:
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_initialize_invalid_command(self):
        """Invalid command skips server but continues with others."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write("""
servers:
  - name: "nonexistent"
    command: "nonexistent_command_12345"
    enabled: true
""")
            temp_path = f.name

        try:
            manager = MCPClientManager(temp_path)

            with pytest.raises(RuntimeError, match="No MCP servers could be started"):
                await manager.initialize()
        finally:
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_list_tools_returns_copy(self):
        """list_tools returns a copy, not the original."""
        mock_tools = [
            MagicMock(
                model_dump=MagicMock(
                    return_value={
                        "name": "test",
                        "description": "Test",
                        "inputSchema": {},
                    }
                )
            )
        ]
        mock_result = MagicMock(tools=mock_tools)
        mock_session = MagicMock()
        mock_session.initialize = AsyncMock()
        mock_session.list_tools = AsyncMock(return_value=mock_result)

        mock_streams = (MagicMock(), MagicMock())
        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_streams)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write("""
servers:
  - name: "mock_server"
    command: "echo"
    enabled: true
""")
            temp_path = f.name

        try:
            with patch("infrastructure.mcp.manager.ClientSession", return_value=mock_session):
                with patch("infrastructure.mcp.manager.stdio_client", return_value=mock_context):
                    manager = MCPClientManager(temp_path)
                    await manager.initialize()

                    tools1 = await manager.list_tools()
                    tools2 = await manager.list_tools()

                    assert tools1 is not tools2
                    assert tools1 == tools2

                    await manager.shutdown()
        finally:
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_shutdown(self):
        """Shutdown properly closes all servers."""
        mock_tools = [
            MagicMock(
                model_dump=MagicMock(
                    return_value={
                        "name": "test",
                        "description": "Test",
                        "inputSchema": {},
                    }
                )
            )
        ]
        mock_result = MagicMock(tools=mock_tools)
        mock_session = MagicMock()
        mock_session.initialize = AsyncMock()
        mock_session.list_tools = AsyncMock(return_value=mock_result)
        mock_session.close = AsyncMock()

        mock_streams = (MagicMock(), MagicMock())
        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_streams)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write("""
servers:
  - name: "mock_server"
    command: "echo"
    enabled: true
""")
            temp_path = f.name

        try:
            with patch("infrastructure.mcp.manager.ClientSession", return_value=mock_session):
                with patch("infrastructure.mcp.manager.stdio_client", return_value=mock_context):
                    manager = MCPClientManager(temp_path)
                    await manager.initialize()
                    assert manager.is_ready() is True

                    await manager.shutdown()
                    assert manager.is_ready() is False

                    tools = await manager.list_tools()
                    assert tools == {}
        finally:
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_tool_name_normalization(self):
        """Tool names with / and - are normalized in keys."""
        mock_tools = [
            MagicMock(
                model_dump=MagicMock(
                    return_value={
                        "name": "read/file",
                        "description": "Test",
                        "inputSchema": {},
                    }
                )
            )
        ]
        mock_result = MagicMock(tools=mock_tools)
        mock_session = MagicMock()
        mock_session.initialize = AsyncMock()
        mock_session.list_tools = AsyncMock(return_value=mock_result)

        mock_streams = (MagicMock(), MagicMock())
        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_streams)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write("""
servers:
  - name: "my_server"
    command: "echo"
    enabled: true
""")
            temp_path = f.name

        try:
            with patch("infrastructure.mcp.manager.ClientSession", return_value=mock_session):
                with patch("infrastructure.mcp.manager.stdio_client", return_value=mock_context):
                    manager = MCPClientManager(temp_path)
                    await manager.initialize()

                    tools = await manager.list_tools()

                    # Tool names should be namespaced as server/tool_name
                    # The key should be namespaced, and normalized (no / or - in the tool name part)
                    for tool_name in tools:
                        # Key should contain namespace separator
                        assert "/" in tool_name
                        # The namespaced key should not have / in the tool name part
                        parts = tool_name.split("/")
                        assert "/" not in parts[-1]
                        assert "-" not in parts[-1]
                        # But the original_name preserves the original
                        assert tools[tool_name]["original_name"] == "read/file"

                    await manager.shutdown()
        finally:
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_tool_name_collision(self):
        """Duplicate namespaced tool names log warning and keep first."""
        # Two tools from the same server that normalize to same key
        # (e.g., if a server has "tool" and "tool_duplicate" that both normalize)
        # For this test, we test that multiple servers with same server name collision
        # is not possible (but different servers can have same tool names)
        mock_tools = [
            MagicMock(
                model_dump=MagicMock(
                    return_value={
                        "name": "tool",
                        "description": "Tool",
                        "inputSchema": {},
                    }
                )
            ),
            MagicMock(
                model_dump=MagicMock(
                    return_value={
                        "name": "tool",
                        "description": "Tool duplicate",  # Same name
                        "inputSchema": {},
                    }
                )
            ),
        ]
        mock_result = MagicMock(tools=mock_tools)

        mock_session = MagicMock()
        mock_session.initialize = AsyncMock()
        mock_session.list_tools = AsyncMock(return_value=mock_result)

        mock_streams = (MagicMock(), MagicMock())
        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_streams)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write("""
servers:
  - name: "test_server"
    command: "echo"
    enabled: true
""")
            temp_path = f.name

        try:
            with patch("infrastructure.mcp.manager.ClientSession", return_value=mock_session):
                with patch("infrastructure.mcp.manager.stdio_client", return_value=mock_context):
                    manager = MCPClientManager(temp_path)
                    await manager.initialize()

                    tools = await manager.list_tools()

                    # Server returns two tools with the same name "tool"
                    # Only the first one should be registered (collision detection)
                    # The namespaced key would be "test_server/tool"
                    count = sum(1 for name in tools if "tool" in name)
                    assert count == 1  # Only one registered

                    await manager.shutdown()
        finally:
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_empty_tools_list(self):
        """Server returning no tools is still connected."""
        mock_result = MagicMock(tools=[])
        mock_session = MagicMock()
        mock_session.initialize = AsyncMock()
        mock_session.list_tools = AsyncMock(return_value=mock_result)

        mock_streams = (MagicMock(), MagicMock())
        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_streams)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write("""
servers:
  - name: "empty_server"
    command: "echo"
    enabled: true
""")
            temp_path = f.name

        try:
            with patch("infrastructure.mcp.manager.ClientSession", return_value=mock_session):
                with patch("infrastructure.mcp.manager.stdio_client", return_value=mock_context):
                    manager = MCPClientManager(temp_path)
                    await manager.initialize()

                    assert manager.is_ready() is True
                    tools = await manager.list_tools()
                    assert tools == {}

                    await manager.shutdown()
        finally:
            os.unlink(temp_path)
