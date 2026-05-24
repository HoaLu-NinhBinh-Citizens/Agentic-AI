"""Unit tests for MCP client."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from src.infrastructure.mcp.mcp_client import (
    MCPClient,
    MCPServerManager,
    MCPError,
    MCPResource,
    MCPTool,
    MCPPrompt,
    MCPToolCall,
    MCPToolResult,
    MCPResourceContent,
)


class TestMCPResource:
    """Tests for MCPResource."""

    def test_create_resource(self):
        """Test creating resource."""
        resource = MCPResource(
            uri="file:///test.txt",
            name="Test File",
            description="A test file",
        )
        
        assert resource.uri == "file:///test.txt"
        assert resource.name == "Test File"


class TestMCPTool:
    """Tests for MCPTool."""

    def test_create_tool(self):
        """Test creating tool."""
        tool = MCPTool(
            name="read_file",
            description="Read a file",
            input_schema={"type": "object"},
        )
        
        assert tool.name == "read_file"
        assert tool.input_schema == {"type": "object"}


class TestMCPPrompt:
    """Tests for MCPPrompt."""

    def test_create_prompt(self):
        """Test creating prompt."""
        prompt = MCPPrompt(
            name="explain_code",
            description="Explain code",
            arguments=[{"name": "code", "type": "string"}],
        )
        
        assert prompt.name == "explain_code"
        assert len(prompt.arguments) == 1


class TestMCPClient:
    """Tests for MCPClient."""

    def test_create_client(self):
        """Test creating client."""
        client = MCPClient(["echo"], "test-server")
        
        assert client.server_command == ["echo"]
        assert client.server_name == "test-server"
        assert len(client._resources) == 0
        assert len(client._tools) == 0


class TestMCPServerManager:
    """Tests for MCPServerManager."""

    def test_create_manager(self):
        """Test creating manager."""
        manager = MCPServerManager()
        
        assert len(manager._clients) == 0

    def test_list_clients(self):
        """Test listing clients."""
        manager = MCPServerManager()
        
        assert manager.list_clients() == []

    def test_get_client(self):
        """Test getting non-existent client."""
        manager = MCPServerManager()
        
        assert manager.get_client("nonexistent") is None
