"""MCP servers for Agentic-AI.

Provides MCP server implementations:
- Filesystem server
- Git server
- Memory server
- Search server
"""

from __future__ import annotations

import asyncio
import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator


class MCPServerError(Exception):
    """MCP server error."""
    pass


@dataclass
class MCPResource:
    """A resource that can be exposed via MCP."""
    uri: str
    name: str
    description: str = ""
    mime_type: str = "text/plain"
    content: str | None = None


@dataclass
class MCPTool:
    """A tool that can be called."""
    name: str
    description: str = ""
    input_schema: dict = field(default_factory=dict)


@dataclass
class MCPToolInput:
    """Input for a tool call."""
    name: str
    arguments: dict = field(default_factory=dict)


@dataclass
class MCPToolResult:
    """Result from a tool call."""
    content: list[dict]
    is_error: bool = False


class FilesystemMCPServer:
    """MCP server for filesystem operations.
    
    Implements the MCP protocol for file system access.
    """
    
    def __init__(self, root: Path | None = None):
        self.root = root or Path.cwd()
        self._resources: list[MCPResource] = []
        self._tools: list[MCPTool] = []
        self._update_tools()
    
    def _update_tools(self) -> None:
        """Update available tools."""
        self._tools = [
            MCPTool(
                name="read_file",
                description="Read contents of a file",
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Path to file"},
                    },
                    "required": ["path"],
                },
            ),
            MCPTool(
                name="write_file",
                description="Write content to a file",
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Path to file"},
                        "content": {"type": "string", "description": "Content to write"},
                    },
                    "required": ["path", "content"],
                },
            ),
            MCPTool(
                name="list_directory",
                description="List files in a directory",
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Directory path"},
                    },
                },
            ),
            MCPTool(
                name="glob",
                description="Find files matching pattern",
                input_schema={
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string", "description": "Glob pattern"},
                        "root": {"type": "string", "description": "Root directory"},
                    },
                    "required": ["pattern"],
                },
            ),
            MCPTool(
                name="file_exists",
                description="Check if file exists",
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Path to check"},
                    },
                    "required": ["path"],
                },
            ),
        ]
    
    @property
    def tools(self) -> list[MCPTool]:
        """Get available tools."""
        return self._tools
    
    async def call_tool(self, input: MCPToolInput) -> MCPToolResult:
        """Call a tool."""
        name = input.name
        args = input.arguments
        
        try:
            if name == "read_file":
                return await self._read_file(args)
            elif name == "write_file":
                return await self._write_file(args)
            elif name == "list_directory":
                return await self._list_directory(args)
            elif name == "glob":
                return await self._glob(args)
            elif name == "file_exists":
                return await self._file_exists(args)
            else:
                return MCPToolResult(
                    content=[{"type": "text", "text": f"Unknown tool: {name}"}],
                    is_error=True,
                )
        except Exception as e:
            return MCPToolResult(
                content=[{"type": "text", "text": str(e)}],
                is_error=True,
            )
    
    async def _read_file(self, args: dict) -> MCPToolResult:
        """Read a file."""
        path = Path(args["path"])
        if not path.is_absolute():
            path = self.root / path
        
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        
        content = path.read_text(errors="replace")
        
        return MCPToolResult(
            content=[{
                "type": "text",
                "text": content[:100000],  # Limit size
            }],
        )
    
    async def _write_file(self, args: dict) -> MCPToolResult:
        """Write a file."""
        path = Path(args["path"])
        if not path.is_absolute():
            path = self.root / path
        
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(args["content"])
        
        return MCPToolResult(
            content=[{"type": "text", "text": f"Written to {path}"}],
        )
    
    async def _list_directory(self, args: dict) -> MCPToolResult:
        """List directory contents."""
        path = Path(args.get("path", "."))
        if not path.is_absolute():
            path = self.root / path
        
        if not path.is_dir():
            raise NotADirectoryError(f"Not a directory: {path}")
        
        items = []
        for item in path.iterdir():
            items.append({
                "name": item.name,
                "type": "dir" if item.is_dir() else "file",
                "size": item.stat().st_size if item.is_file() else 0,
            })
        
        return MCPToolResult(
            content=[{"type": "text", "text": json.dumps(items, indent=2)}],
        )
    
    async def _glob(self, args: dict) -> MCPToolResult:
        """Glob pattern matching."""
        pattern = args["pattern"]
        root = Path(args.get("root", "."))
        if not root.is_absolute():
            root = self.root / root
        
        matches = [str(p) for p in root.glob(pattern)]
        
        return MCPToolResult(
            content=[{"type": "text", "text": "\n".join(matches)}],
        )
    
    async def _file_exists(self, args: dict) -> MCPToolResult:
        """Check if file exists."""
        path = Path(args["path"])
        if not path.is_absolute():
            path = self.root / path
        
        return MCPToolResult(
            content=[{"type": "text", "text": str(path.exists())}],
        )


class GitMCPServer:
    """MCP server for Git operations.
    
    Provides Git functionality via MCP protocol.
    """
    
    def __init__(self, repo_path: Path | None = None):
        self.repo_path = repo_path or Path.cwd()
        self._tools = self._setup_tools()
    
    def _setup_tools(self) -> list[MCPTool]:
        """Setup available tools."""
        return [
            MCPTool(
                name="git_status",
                description="Get git status",
                input_schema={"type": "object", "properties": {}},
            ),
            MCPTool(
                name="git_log",
                description="Get commit history",
                input_schema={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "default": 10},
                        "path": {"type": "string"},
                    },
                },
            ),
            MCPTool(
                name="git_diff",
                description="Get diff of changes",
                input_schema={
                    "type": "object",
                    "properties": {
                        "ref": {"type": "string"},
                    },
                },
            ),
            MCPTool(
                name="git_branch",
                description="List branches",
                input_schema={"type": "object", "properties": {}},
            ),
            MCPTool(
                name="git_show",
                description="Show commit details",
                input_schema={
                    "type": "object",
                    "properties": {
                        "ref": {"type": "string"},
                    },
                    "required": ["ref"],
                },
            ),
            MCPTool(
                name="git_blame",
                description="Get blame for file",
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                    },
                    "required": ["path"],
                },
            ),
            MCPTool(
                name="git_grep",
                description="Search for pattern in repo",
                input_schema={
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string"},
                        "path": {"type": "string"},
                    },
                    "required": ["pattern"],
                },
            ),
        ]
    
    @property
    def tools(self) -> list[MCPTool]:
        """Get available tools."""
        return self._tools
    
    async def call_tool(self, input: MCPToolInput) -> MCPToolResult:
        """Call a tool."""
        name = input.name
        args = input.arguments
        
        try:
            if name == "git_status":
                return await self._git_status()
            elif name == "git_log":
                return await self._git_log(args)
            elif name == "git_diff":
                return await self._git_diff(args)
            elif name == "git_branch":
                return await self._git_branch()
            elif name == "git_show":
                return await self._git_show(args)
            elif name == "git_blame":
                return await self._git_blame(args)
            elif name == "git_grep":
                return await self._git_grep(args)
            else:
                return MCPToolResult(
                    content=[{"type": "text", "text": f"Unknown tool: {name}"}],
                    is_error=True,
                )
        except Exception as e:
            return MCPToolResult(
                content=[{"type": "text", "text": str(e)}],
                is_error=True,
            )
    
    async def _run_git(self, *args) -> str:
        """Run git command."""
        proc = await asyncio.create_subprocess_exec(
            "git", *args,
            cwd=str(self.repo_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        
        if proc.returncode != 0 and stderr:
            raise RuntimeError(stderr.decode())
        
        return stdout.decode()
    
    async def _git_status(self) -> MCPToolResult:
        """Get git status."""
        output = await self._run_git("status", "--porcelain")
        return MCPToolResult(
            content=[{"type": "text", "text": output}],
        )
    
    async def _git_log(self, args: dict) -> MCPToolResult:
        """Get commit log."""
        limit = args.get("limit", 10)
        path = args.get("path")
        
        cmd = ["log", f"-{limit}", "--pretty=format:%H|%s|%an|%ad"]
        if path:
            cmd.append("--")
            cmd.append(path)
        
        output = await self._run_git(*cmd)
        
        commits = []
        for line in output.strip().split("\n"):
            if "|" in line:
                parts = line.split("|")
                if len(parts) >= 4:
                    commits.append({
                        "hash": parts[0],
                        "message": parts[1],
                        "author": parts[2],
                        "date": parts[3],
                    })
        
        return MCPToolResult(
            content=[{"type": "text", "text": json.dumps(commits, indent=2)}],
        )
    
    async def _git_diff(self, args: dict) -> MCPToolResult:
        """Get diff."""
        ref = args.get("ref", "HEAD")
        output = await self._run_git("diff", ref)
        return MCPToolResult(
            content=[{"type": "text", "text": output}],
        )
    
    async def _git_branch(self) -> MCPToolResult:
        """List branches."""
        output = await self._run_git("branch", "-a")
        return MCPToolResult(
            content=[{"type": "text", "text": output}],
        )
    
    async def _git_show(self, args: dict) -> MCPToolResult:
        """Show commit."""
        ref = args["ref"]
        output = await self._run_git("show", "--stat", ref)
        return MCPToolResult(
            content=[{"type": "text", "text": output}],
        )
    
    async def _git_blame(self, args: dict) -> MCPToolResult:
        """Get blame."""
        path = args["path"]
        output = await self._run_git("blame", path)
        return MCPToolResult(
            content=[{"type": "text", "text": output[:50000]}],
        )
    
    async def _git_grep(self, args: dict) -> MCPToolResult:
        """Grep in repo."""
        pattern = args["pattern"]
        path = args.get("path", ".")
        
        output = await self._run_git("grep", "--line-number", pattern, "--", path)
        return MCPToolResult(
            content=[{"type": "text", "text": output}],
        )


class MemoryMCPServer:
    """MCP server for memory operations."""
    
    def __init__(self):
        self._memory: dict[str, str] = {}
        self._tools = [
            MCPTool(
                name="memory_set",
                description="Store a value in memory",
                input_schema={
                    "type": "object",
                    "properties": {
                        "key": {"type": "string"},
                        "value": {"type": "string"},
                    },
                    "required": ["key", "value"],
                },
            ),
            MCPTool(
                name="memory_get",
                description="Retrieve a value from memory",
                input_schema={
                    "type": "object",
                    "properties": {
                        "key": {"type": "string"},
                    },
                    "required": ["key"],
                },
            ),
            MCPTool(
                name="memory_keys",
                description="List all memory keys",
                input_schema={"type": "object", "properties": {}},
            ),
            MCPTool(
                name="memory_delete",
                description="Delete a memory entry",
                input_schema={
                    "type": "object",
                    "properties": {
                        "key": {"type": "string"},
                    },
                    "required": ["key"],
                },
            ),
        ]
    
    @property
    def tools(self) -> list[MCPTool]:
        return self._tools
    
    async def call_tool(self, input: MCPToolInput) -> MCPToolResult:
        """Call a tool."""
        name = input.name
        args = input.arguments
        
        try:
            if name == "memory_set":
                self._memory[args["key"]] = args["value"]
                return MCPToolResult(
                    content=[{"type": "text", "text": f"Set {args['key']}"}],
                )
            elif name == "memory_get":
                value = self._memory.get(args["key"], "")
                return MCPToolResult(
                    content=[{"type": "text", "text": value}],
                )
            elif name == "memory_keys":
                keys = "\n".join(self._memory.keys())
                return MCPToolResult(
                    content=[{"type": "text", "text": keys}],
                )
            elif name == "memory_delete":
                if args["key"] in self._memory:
                    del self._memory[args["key"]]
                return MCPToolResult(
                    content=[{"type": "text", "text": f"Deleted {args['key']}"}],
                )
            else:
                return MCPToolResult(
                    content=[{"type": "text", "text": f"Unknown tool: {name}"}],
                    is_error=True,
                )
        except Exception as e:
            return MCPToolResult(
                content=[{"type": "text", "text": str(e)}],
                is_error=True,
            )


class SearchMCPServer:
    """MCP server for web search."""
    
    def __init__(self, web_search_manager=None):
        self._search = web_search_manager
        self._tools = [
            MCPTool(
                name="web_search",
                description="Search the web",
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "num_results": {"type": "integer", "default": 5},
                    },
                    "required": ["query"],
                },
            ),
            MCPTool(
                name="web_scrape",
                description="Scrape a webpage",
                input_schema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string"},
                    },
                    "required": ["url"],
                },
            ),
        ]
    
    @property
    def tools(self) -> list[MCPTool]:
        return self._tools
    
    async def call_tool(self, input: MCPToolInput) -> MCPToolResult:
        """Call a tool."""
        name = input.name
        args = input.arguments
        
        try:
            if name == "web_search":
                from src.infrastructure.web.web_search import DuckDuckGoSearch
                
                search = DuckDuckGoSearch()
                results = await search.search(args["query"], args.get("num_results", 5))
                
                output = "\n".join(
                    f"- {r.title}\n  {r.url}\n  {r.snippet}"
                    for r in results
                )
                
                return MCPToolResult(
                    content=[{"type": "text", "text": output}],
                )
            elif name == "web_scrape":
                from src.infrastructure.web.web_search import WebScraper
                
                scraper = WebScraper()
                content = await scraper.scrape(args["url"])
                
                return MCPToolResult(
                    content=[{"type": "text", "text": content[:100000]}],
                )
            else:
                return MCPToolResult(
                    content=[{"type": "text", "text": f"Unknown tool: {name}"}],
                    is_error=True,
                )
        except Exception as e:
            return MCPToolResult(
                content=[{"type": "text", "text": str(e)}],
                is_error=True,
            )


class MCPServerManager:
    """Manages multiple MCP servers."""
    
    def __init__(self):
        self._servers: dict[str, Any] = {}
    
    def register(self, name: str, server: Any) -> None:
        """Register an MCP server."""
        self._servers[name] = server
    
    def get_tools(self) -> list[tuple[str, MCPTool]]:
        """Get all tools from all servers."""
        tools = []
        for name, server in self._servers.items():
            for tool in server.tools:
                tools.append((name, tool))
        return tools
    
    async def call_tool(self, server_name: str, tool_name: str, arguments: dict) -> MCPToolResult:
        """Call a tool on a specific server."""
        if server_name not in self._servers:
            raise MCPServerError(f"Server not found: {server_name}")
        
        server = self._servers[server_name]
        return await server.call_tool(MCPToolInput(name=tool_name, arguments=arguments))
    
    def list_servers(self) -> list[str]:
        """List all server names."""
        return list(self._servers.keys())
