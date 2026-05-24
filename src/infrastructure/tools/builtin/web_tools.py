"""Web search tools for Agentic-AI CLI.

Tools:
- web_search: Multi-provider search
- extract_url: Extract content from URL
"""

from __future__ import annotations

from typing import Any

from ..tool_registry import (
    BaseTool,
    ToolCategory,
    ToolResult,
    ToolSchema,
)


class WebSearchTool(BaseTool):
    """Search the web using multiple providers.
    
    Like omp's web_search tool:
    - auto mode chains through providers
    - Returns ranked results with citations
    - Specialized scrapers for code hosts, docs
    """
    
    name = "web_search"
    description = "Search the web using multiple providers"
    category = ToolCategory.WEB
    setting_gated = "tools.web_search"  # Requires explicit enable
    
    schema = ToolSchema(
        description="Search the web",
        properties={
            "query": {
                "type": "string",
                "description": "Search query",
            },
            "provider": {
                "type": "string",
                "description": "Provider: auto, ddg, jina, brave, tavily, exa",
                "default": "auto",
            },
            "limit": {
                "type": "integer",
                "description": "Max results",
                "default": 10,
            },
        },
        required=["query"],
    )
    
    async def execute(self, query: str, provider: str = "auto", limit: int = 10, **kwargs) -> ToolResult:
        """Execute web search."""
        try:
            from .web_search import web_search
            
            response = await web_search(query, provider, limit)
            
            if not response.results:
                return ToolResult(
                    tool_name=self.name,
                    success=True,
                    content=[{"type": "text", "text": "No results found"}],
                )
            
            lines = [f"[{len(response.results)} results from {response.provider}]"]
            lines.append("")
            
            for i, result in enumerate(response.results, 1):
                lines.append(f"{i}. {result.title}")
                lines.append(f"   URL: {result.url}")
                if result.snippet:
                    snippet = result.snippet[:200] + "..." if len(result.snippet) > 200 else result.snippet
                    lines.append(f"   {snippet}")
                lines.append("")
            
            return ToolResult(
                tool_name=self.name,
                success=True,
                content=[{"type": "text", "text": "\n".join(lines)}],
            )
            
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=f"Search failed: {e}",
                is_error=True,
            )


class ExtractURLTool(BaseTool):
    """Extract content from a URL.
    
    Like omp's read tool for URLs:
    - Fetches and converts to markdown
    - Preserves links and structure
    """
    
    name = "extract_url"
    description = "Extract content from a URL"
    category = ToolCategory.WEB
    
    schema = ToolSchema(
        description="Extract content from URL",
        properties={
            "url": {
                "type": "string",
                "description": "URL to extract",
            },
            "max_length": {
                "type": "integer",
                "description": "Max content length",
                "default": 10000,
            },
        },
        required=["url"],
    )
    
    async def execute(self, url: str, max_length: int = 10000, **kwargs) -> ToolResult:
        """Execute URL extraction."""
        try:
            from .web_search import extract_url
            
            content = await extract_url(url)
            
            if not content:
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    error="Failed to extract content",
                    is_error=True,
                )
            
            # Truncate if needed
            if len(content) > max_length:
                content = content[:max_length] + f"\n... [{len(content) - max_length} more characters]"
            
            return ToolResult(
                tool_name=self.name,
                success=True,
                content=[{"type": "text", "text": content}],
            )
            
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=f"Extraction failed: {e}",
                is_error=True,
            )


class ReadTool(BaseTool):
    """Read tool that handles URLs, files, and internal schemes.
    
    Extends the basic read tool with URL support.
    """
    
    name = "read"
    description = "Read files, URLs, or internal schemes"
    category = ToolCategory.FILES
    
    schema = ToolSchema(
        description="Read content from file, URL, or internal scheme",
        properties={
            "path": {
                "type": "string",
                "description": "File path, URL, or internal scheme (pr://, issue://, etc.)",
            },
            "max_length": {
                "type": "integer",
                "description": "Max content length",
                "default": 5000,
            },
        },
        required=["path"],
    )
    
    async def execute(self, path: str, max_length: int = 5000, **kwargs) -> ToolResult:
        """Execute read."""
        try:
            # URL
            if path.startswith(("http://", "https://")):
                from .web_search import extract_url
                content = await extract_url(path)
                
                if not content:
                    return ToolResult(
                        tool_name=self.name,
                        success=False,
                        error="Failed to fetch URL",
                        is_error=True,
                    )
                
                if len(content) > max_length:
                    content = content[:max_length] + f"\n... [{len(content) - max_length} more chars]"
                
                return ToolResult(
                    tool_name=self.name,
                    success=True,
                    content=[{"type": "text", "text": content}],
                )
            
            # File
            from pathlib import Path
            
            file_path = Path(path)
            if not file_path.exists():
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    error=f"File not found: {path}",
                    is_error=True,
                )
            
            if file_path.is_dir():
                entries = []
                for item in sorted(file_path.iterdir())[:50]:
                    entries.append(f"{'[D] ' if item.is_dir() else ''}{item.name}")
                
                return ToolResult(
                    tool_name=self.name,
                    success=True,
                    content=[{"type": "text", "text": "\n".join(entries)}],
                )
            
            content = file_path.read_text(encoding="utf-8", errors="replace")
            
            if len(content) > max_length:
                content = content[:max_length] + f"\n... [{len(content) - max_length} more chars]"
            
            return ToolResult(
                tool_name=self.name,
                success=True,
                content=[{"type": "text", "text": content}],
            )
            
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=f"Read failed: {e}",
                is_error=True,
            )


# Register web search tools
def register_web_tools(registry):
    """Register web search tools to a registry."""
    registry.register(WebSearchTool())
    registry.register(ExtractURLTool())
    registry.register(ReadTool())
