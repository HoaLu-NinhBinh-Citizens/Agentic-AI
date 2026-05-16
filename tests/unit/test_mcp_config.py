"""Unit tests for MCP configuration loading and validation."""

from __future__ import annotations

import pytest
import tempfile
import os
from pathlib import Path

from infrastructure.mcp.config import MCPServerConfig, MCPConfig, MCPConfigLoader


class TestMCPServerConfig:
    """Tests for MCPServerConfig validation."""

    def test_valid_config(self):
        """Valid configuration should pass validation."""
        config = MCPServerConfig(
            name="filesystem",
            command="npx",
            args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
            transport="stdio",
            enabled=True,
        )
        assert config.name == "filesystem"
        assert config.command == "npx"
        assert config.args == ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
        assert config.transport == "stdio"
        assert config.enabled is True

    def test_default_values(self):
        """Test default values for optional fields."""
        config = MCPServerConfig(
            name="test_server",
            command="python",
        )
        assert config.args == []
        assert config.transport == "stdio"
        assert config.enabled is True

    def test_name_pattern_lowercase(self):
        """Name must start with lowercase letter."""
        config = MCPServerConfig(name="valid_name", command="echo")
        assert config.name == "valid_name"

    def test_name_pattern_with_numbers(self):
        """Name can contain numbers."""
        config = MCPServerConfig(name="server2", command="echo")
        assert config.name == "server2"

    def test_name_pattern_with_underscore(self):
        """Name can contain underscores."""
        config = MCPServerConfig(name="my_server", command="echo")
        assert config.name == "my_server"

    def test_invalid_name_starts_with_number(self):
        """Name cannot start with a number."""
        with pytest.raises(Exception):
            MCPServerConfig(name="2server", command="echo")

    def test_invalid_transport(self):
        """Only stdio transport is supported."""
        with pytest.raises(ValueError, match="Only 'stdio' transport is supported"):
            MCPServerConfig(
                name="test",
                command="echo",
                transport="http",
            )


class TestMCPConfig:
    """Tests for MCPConfig."""

    def test_empty_servers(self):
        """Config can have no servers."""
        config = MCPConfig()
        assert config.servers == []

    def test_multiple_servers(self):
        """Config can have multiple servers."""
        config = MCPConfig(
            servers=[
                MCPServerConfig(name="server1", command="echo"),
                MCPServerConfig(name="server2", command="ls"),
            ]
        )
        assert len(config.servers) == 2


class TestMCPConfigLoader:
    """Tests for MCPConfigLoader."""

    def test_default_config(self):
        """Missing config file returns default configuration."""
        loader = MCPConfigLoader("nonexistent/path/servers.yaml")
        config = loader.load()

        assert len(config.servers) == 1
        assert config.servers[0].name == "filesystem"
        assert config.servers[0].command == "npx"
        assert config.servers[0].enabled is True

    def test_custom_config(self):
        """Valid YAML configuration loads correctly."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write("""
servers:
  - name: "custom_server"
    command: "python"
    args: ["-m", "my_server"]
    transport: "stdio"
    enabled: true
  - name: "disabled_server"
    command: "echo"
    enabled: false
""")
            temp_path = f.name

        try:
            loader = MCPConfigLoader(temp_path)
            config = loader.load()

            assert len(config.servers) == 2
            assert config.servers[0].name == "custom_server"
            assert config.servers[0].command == "python"
            assert config.servers[0].args == ["-m", "my_server"]
            assert config.servers[0].enabled is True

            assert config.servers[1].name == "disabled_server"
            assert config.servers[1].enabled is False
        finally:
            os.unlink(temp_path)

    def test_invalid_yaml(self):
        """Invalid YAML raises exception."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write("servers:\n  - name: [invalid yaml")
            temp_path = f.name

        try:
            loader = MCPConfigLoader(temp_path)
            with pytest.raises(RuntimeError, match="Invalid YAML"):
                loader.load()
        finally:
            os.unlink(temp_path)

    def test_empty_yaml(self):
        """Empty YAML file returns default config."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write("")
            temp_path = f.name

        try:
            loader = MCPConfigLoader(temp_path)
            config = loader.load()
            assert len(config.servers) == 1
            assert config.servers[0].name == "filesystem"
        finally:
            os.unlink(temp_path)

    def test_config_path_property(self):
        """Config path is stored correctly."""
        loader = MCPConfigLoader("custom/path/servers.yaml")
        assert loader.config_path == Path("custom/path/servers.yaml")
