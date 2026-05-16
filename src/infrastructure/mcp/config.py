"""MCP configuration models and loader.

Phase 2A loads server configurations from YAML and validates them using Pydantic.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import List

import yaml
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)


class MCPServerConfig(BaseModel):
    """Configuration for a single MCP server.

    Attributes:
        name: Unique identifier for the server (lowercase, alphanumeric + underscore).
        command: Executable command to spawn (e.g., 'npx', 'uvx', 'python').
        args: Command-line arguments passed to the executable.
        transport: Transport protocol (only 'stdio' supported in Phase 2A).
        enabled: Whether the server should be started on initialization.
    """

    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    command: str
    args: List[str] = Field(default_factory=list)
    transport: str = "stdio"
    enabled: bool = True

    @field_validator("transport")
    @classmethod
    def validate_transport(cls, value: str) -> str:
        """Ensure only stdio transport is used in Phase 2A."""
        if value != "stdio":
            raise ValueError("Only 'stdio' transport is supported in Phase 2A")
        return value


class MCPConfig(BaseModel):
    """Configuration for all MCP servers.

    Attributes:
        servers: List of server configurations.
    """

    servers: List[MCPServerConfig] = Field(default_factory=list)


class MCPConfigLoader:
    """Loads and parses MCP server configurations from YAML.

    Args:
        config_path: Path to the servers.yaml configuration file.

    Example:
        >>> loader = MCPConfigLoader("configs/mcp/servers.yaml")
        >>> config = loader.load()
        >>> for server in config.servers:
        ...     print(f"{server.name}: {server.command}")
    """

    DEFAULT_CONFIG = MCPConfig(
        servers=[
            MCPServerConfig(
                name="filesystem",
                command="npx",
                args=["-y", "@modelcontextprotocol/server-filesystem", str(Path.home())],
                enabled=True,
            )
        ]
    )

    def __init__(self, config_path: str = "configs/mcp/servers.yaml") -> None:
        """Initialize the loader with a config path.

        Args:
            config_path: Path to YAML configuration file.
        """
        self.config_path = Path(config_path)

    def load(self) -> MCPConfig:
        """Load MCP configuration from file.

        If the config file doesn't exist, returns a default configuration
        with only the filesystem server enabled.

        Returns:
            MCPConfig with server configurations.

        Raises:
            RuntimeError: If YAML parsing fails.
        """
        if not self.config_path.exists():
            logger.warning(
                "MCP config not found at %s, using default configuration",
                self.config_path,
            )
            return self.DEFAULT_CONFIG

        try:
            with open(self.config_path) as f:
                data = yaml.safe_load(f)

            if data is None:
                logger.warning(
                    "MCP config is empty at %s, using default configuration",
                    self.config_path,
                )
                return self.DEFAULT_CONFIG

            return MCPConfig(**data)

        except yaml.YAMLError as e:
            raise RuntimeError(f"Invalid YAML in {self.config_path}: {e}") from e
        except Exception as e:
            raise RuntimeError(f"Failed to load MCP config: {e}") from e
