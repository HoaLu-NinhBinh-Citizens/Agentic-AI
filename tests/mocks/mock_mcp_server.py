"""Mock MCP Server for testing.

A minimal MCP-compliant server that responds to initialize and list_tools requests.
Used in unit tests to avoid external dependencies.

Tools provided:
- echo: Echoes the input message
- add: Adds two numbers
- sleep: Sleeps for N seconds (for timeout testing)
"""

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

app = Server("mock-mcp-server")


@app.list_tools()
async def list_tools():
    """Return the list of available tools."""
    return [
        Tool(
            name="echo",
            description="Echoes the input message back",
            inputSchema={
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "Message to echo"},
                },
                "required": ["message"],
            },
        ),
        Tool(
            name="add",
            description="Adds two numbers",
            inputSchema={
                "type": "object",
                "properties": {
                    "a": {"type": "number", "description": "First number"},
                    "b": {"type": "number", "description": "Second number"},
                },
                "required": ["a", "b"],
            },
        ),
        Tool(
            name="sleep",
            description="Sleeps for a specified number of seconds",
            inputSchema={
                "type": "object",
                "properties": {
                    "seconds": {"type": "number", "description": "Seconds to sleep"},
                },
                "required": ["seconds"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict):
    """Handle tool calls (not used in Phase 2A but needed for protocol completeness)."""
    if name == "echo":
        return [TextContent(type="text", text=arguments.get("message", ""))]
    elif name == "add":
        result = arguments.get("a", 0) + arguments.get("b", 0)
        return [TextContent(type="text", text=str(result))]
    elif name == "sleep":
        import asyncio
        await asyncio.sleep(arguments.get("seconds", 0))
        return [TextContent(type="text", text="done")]
    return []


if __name__ == "__main__":
    stdio_server(app)
