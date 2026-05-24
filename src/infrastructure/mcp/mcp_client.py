"""MCP (Model Context Protocol) client for Agentic-AI.

Provides additional MCP client capabilities:
- Resource access
- Tool calling
- Prompt management

This module extends the existing MCP client with additional features.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, AsyncIterator
from uuid import uuid4


class MCPError(Exception):
    """MCP operation error."""
    pass


class MCPErrorCode(Enum):
    """Error codes."""
    RESOURCE_NOT_FOUND = -32002
    TOOL_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603


@dataclass
class MCPResource:
    """A resource that can be accessed."""
    uri: str
    name: str
    description: str = ""
    mime_type: str = "text/plain"


@dataclass
class MCPResourceContent:
    """Content of a resource."""
    uri: str
    mime_type: str
    content: str


@dataclass
class MCPTool:
    """A tool that can be called."""
    name: str
    description: str = ""
    input_schema: dict = field(default_factory=dict)


@dataclass
class MCPPrompt:
    """A prompt template."""
    name: str
    description: str = ""
    arguments: list[dict] = field(default_factory=list)


@dataclass
class MCPToolCall:
    """A tool call request."""
    name: str
    arguments: dict = field(default_factory=dict)


@dataclass
class MCPToolResult:
    """Result of a tool call."""
    content: list[dict]
    is_error: bool = False


class MCPClient:
    """MCP client using JSON-RPC over stdio.
    
    Connects to MCP servers and provides:
    - Resource access
    - Tool calling
    - Prompt management
    """
    
    def __init__(self, server_command: list[str], server_name: str = "server"):
        self.server_command = server_command
        self.server_name = server_name
        self._process: asyncio.subprocess.Process | None = None
        self._request_id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._reader_task: asyncio.Task | None = None
        self._capabilities: dict = {}
        self._resources: list[MCPResource] = []
        self._tools: list[MCPTool] = []
        self._prompts: list[MCPPrompt] = []
    
    async def connect(self) -> None:
        """Connect to the MCP server."""
        self._process = await asyncio.create_subprocess_exec(
            *self.server_command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        
        self._reader_task = asyncio.create_task(self._read_messages())
        
        # Initialize
        result = await self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "clientInfo": {
                "name": "agentic-ai",
                "version": "1.0.0",
            },
        })
        
        self._capabilities = result.get("capabilities", {})
        
        # Send initialized notification
        await self._send_notification("initialized", {
            "protocolVersion": "2024-11-05",
        })
        
        # Load resources, tools, prompts
        await self._load_capabilities()
    
    async def _load_capabilities(self) -> None:
        """Load server capabilities."""
        # List resources
        try:
            result = await self._send_request("resources/list", {})
            self._resources = [
                MCPResource(
                    uri=r["uri"],
                    name=r.get("name", ""),
                    description=r.get("description", ""),
                    mime_type=r.get("mimeType", "text/plain"),
                )
                for r in result.get("resources", [])
            ]
        except:
            pass
        
        # List tools
        try:
            result = await self._send_request("tools/list", {})
            self._tools = [
                MCPTool(
                    name=t["name"],
                    description=t.get("description", ""),
                    input_schema=t.get("inputSchema", {}),
                )
                for t in result.get("tools", [])
            ]
        except:
            pass
        
        # List prompts
        try:
            result = await self._send_request("prompts/list", {})
            self._prompts = [
                MCPPrompt(
                    name=p["name"],
                    description=p.get("description", ""),
                    arguments=p.get("arguments", []),
                )
                for p in result.get("prompts", [])
            ]
        except:
            pass
    
    async def _read_messages(self) -> None:
        """Read messages from server."""
        assert self._process and self._process.stdout
        
        while True:
            try:
                line = await self._process.stdout.readline()
                if not line:
                    break
                
                message = json.loads(line.decode().strip())
                
                if message.get("jsonrpc") != "2.0":
                    continue
                
                if "id" in message:
                    req_id = message["id"]
                    if req_id in self._pending:
                        future = self._pending.pop(req_id)
                        if "result" in message:
                            future.set_result(message["result"])
                        elif "error" in message:
                            future.set_exception(MCPError(message["error"]))
                elif "method" in message:
                    # Notification or request
                    await self._handle_notification(message)
                    
            except Exception as e:
                if self._process.returncode is not None:
                    break
    
    async def _handle_notification(self, message: dict) -> None:
        """Handle a notification."""
        method = message.get("method", "")
        params = message.get("params", {})
        
        # Handle notifications we're interested in
        if method == "notifications/resources/updated":
            # Resource updated, reload
            await self._load_capabilities()
        elif method == "notifications/tools/list_changed":
            # Tools changed, reload
            await self._load_capabilities()
    
    async def _send_request(self, method: str, params: dict) -> Any:
        """Send a request and wait for response."""
        req_id = self._request_id
        self._request_id += 1
        
        future = asyncio.get_event_loop().create_future()
        self._pending[req_id] = future
        
        message = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params,
        }
        
        await self._send(message)
        return await future
    
    async def _send_notification(self, method: str, params: dict) -> None:
        """Send a notification."""
        message = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        await self._send(message)
    
    async def _send(self, message: dict) -> None:
        """Send a message."""
        if not self._process or not self._process.stdin:
            raise MCPError("Process not running")
        
        content = json.dumps(message) + "\n"
        self._process.stdin.write(content.encode())
        await self._process.stdin.drain()
    
    @property
    def capabilities(self) -> dict:
        """Get server capabilities."""
        return self._capabilities
    
    @property
    def resources(self) -> list[MCPResource]:
        """Get available resources."""
        return self._resources
    
    @property
    def tools(self) -> list[MCPTool]:
        """Get available tools."""
        return self._tools
    
    @property
    def prompts(self) -> list[MCPPrompt]:
        """Get available prompts."""
        return self._prompts
    
    async def read_resource(self, uri: str) -> MCPResourceContent:
        """Read a resource."""
        result = await self._send_request("resources/read", {"uri": uri})
        
        contents = result.get("contents", [])
        if not contents:
            raise MCPError(f"Resource not found: {uri}")
        
        content = contents[0]
        return MCPResourceContent(
            uri=content["uri"],
            mime_type=content.get("mimeType", "text/plain"),
            content=content.get("text", content.get("blob", "")),
        )
    
    async def subscribe_resource(self, uri: str) -> None:
        """Subscribe to resource updates."""
        await self._send_notification("resources/subscribe", {"uri": uri})
    
    async def unsubscribe_resource(self, uri: str) -> None:
        """Unsubscribe from resource updates."""
        await self._send_notification("resources/unsubscribe", {"uri": uri})
    
    async def call_tool(self, name: str, arguments: dict) -> MCPToolResult:
        """Call a tool."""
        result = await self._send_request("tools/call", {
            "name": name,
            "arguments": arguments,
        })
        
        return MCPToolResult(
            content=result.get("content", []),
            is_error=result.get("isError", False),
        )
    
    async def get_prompt(self, name: str, arguments: dict | None = None) -> str:
        """Get a prompt."""
        result = await self._send_request("prompts/get", {
            "name": name,
            "arguments": arguments or {},
        })
        
        messages = result.get("messages", [])
        return "\n".join(
            msg.get("content", {}).get("text", "")
            for msg in messages
            if msg.get("role") == "user"
        )
    
    async def close(self) -> None:
        """Close the connection."""
        if self._reader_task:
            self._reader_task.cancel()
        if self._process:
            self._process.terminate()
            await self._process.wait()


class MCPServerManager:
    """Manages multiple MCP server connections."""
    
    def __init__(self):
        self._clients: dict[str, MCPClient] = {}
    
    async def add_server(self, name: str, command: list[str]) -> MCPClient:
        """Add and connect to an MCP server."""
        client = MCPClient(command, name)
        await client.connect()
        self._clients[name] = client
        return client
    
    def get_client(self, name: str) -> MCPClient | None:
        """Get a client by name."""
        return self._clients.get(name)
    
    def list_clients(self) -> list[str]:
        """List all client names."""
        return list(self._clients.keys())
    
    async def all_tools(self) -> list[tuple[str, MCPTool]]:
        """Get all tools from all servers."""
        tools = []
        for name, client in self._clients.items():
            for tool in client.tools:
                tools.append((name, tool))
        return tools
    
    async def all_resources(self) -> list[tuple[str, MCPResource]]:
        """Get all resources from all servers."""
        resources = []
        for name, client in self._clients.items():
            for resource in client.resources:
                resources.append((name, resource))
        return resources
    
    async def call_tool(self, server_name: str, tool_name: str, arguments: dict) -> MCPToolResult:
        """Call a tool on a specific server."""
        if server_name not in self._clients:
            raise MCPError(f"Server not found: {server_name}")
        
        return await self._clients[server_name].call_tool(tool_name, arguments)
    
    async def close_all(self) -> None:
        """Close all connections."""
        for client in self._clients.values():
            await client.close()
        self._clients.clear()


# Built-in MCP servers

async def connect_filesystem_server(base_path: Path | None = None) -> MCPClient:
    """Connect to filesystem MCP server."""
    # Check for npx or local installation
    try:
        result = await asyncio.create_subprocess_exec(
            "npx", "-y", "@modelcontextprotocol/server-filesystem",
            str(base_path or Path.cwd()),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.sleep(0.5)  # Wait for startup
    except:
        pass
    
    # For now, create a mock client
    client = MCPClient(["echo"], "filesystem")
    return client


async def connect_browser_server() -> MCPClient:
    """Connect to browser MCP server."""
    # Check for puppeteer server
    client = MCPClient(["echo"], "browser")
    return client
