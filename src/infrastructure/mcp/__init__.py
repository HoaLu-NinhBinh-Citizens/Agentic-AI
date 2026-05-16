"""MCP (Model Context Protocol) infrastructure.

Phase 2A provides:
- MCP server configuration loading
- MCP client lifecycle management
- Global tool registry
"""

from infrastructure.mcp.config import MCPServerConfig, MCPConfig, MCPConfigLoader
from infrastructure.mcp.manager import MCPClientManager, ConnectedServer, ToolInfo

__all__ = [
    "MCPServerConfig",
    "MCPConfig",
    "MCPConfigLoader",
    "MCPClientManager",
    "ConnectedServer",
    "ToolInfo",
]
