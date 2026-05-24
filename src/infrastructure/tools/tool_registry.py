"""Tool registry for Agentic-AI CLI.

Inspired by oh-my-pi's unified tool system:
- Single namespace for all tools
- Tool discovery
- Permission system
- Streaming support
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Generic, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class ToolCategory(Enum):
    """Tool categories like omp."""
    FILES = "files"
    SEARCH = "search"
    EDIT = "edit"
    SHELL = "shell"
    CODE = "code"
    WEB = "web"
    GIT = "git"
    MEMORY = "memory"
    DEBUG = "debug"
    HARDWARE = "hardware"  # Agentic-AI specific
    CUSTOM = "custom"


@dataclass
class ToolSchema:
    """JSON Schema for tool arguments."""
    type: str = "object"
    properties: dict[str, Any] = field(default_factory=dict)
    required: list[str] = field(default_factory=list)
    description: str = ""


@dataclass
class ToolDefinition:
    """Definition of a tool."""
    name: str
    description: str
    category: ToolCategory
    schema: ToolSchema
    enabled: bool = True
    hidden: bool = False  # Hidden from default tool list
    setting_gated: str | None = None  # Setting name that gates this tool
    
    # For permission system
    requires_permission: str | None = None
    
    # For tool calling
    execute: Callable[..., Any] | None = None
    
    # Metadata
    version: str = "1.0"
    examples: list[str] = field(default_factory=list)


@dataclass
class ToolResult:
    """Result from tool execution."""
    tool_name: str
    success: bool
    content: list[dict[str, Any]] = field(default_factory=list)
    
    # Error info
    error: str | None = None
    is_error: bool = False
    
    # Metadata
    duration_ms: float | None = None
    call_id: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


class BaseTool(ABC):
    """Base class for all tools."""
    
    name: str = ""
    description: str = ""
    category: ToolCategory = ToolCategory.CUSTOM
    schema: ToolSchema = field(default_factory=ToolSchema)
    setting_gated: str | None = None
    requires_permission: str | None = None
    
    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """Execute the tool."""
        pass
    
    def to_definition(self) -> ToolDefinition:
        """Convert to tool definition."""
        return ToolDefinition(
            name=self.name,
            description=self.description,
            category=self.category,
            schema=self.schema,
            setting_gated=self.setting_gated,
            requires_permission=self.requires_permission,
            execute=self.execute,
        )


@dataclass
class ToolCallRequest:
    """Request to call a tool."""
    name: str
    arguments: dict[str, Any]
    call_id: str | None = None
    timeout_seconds: float | None = None


@dataclass 
class ToolCallResponse:
    """Response from tool execution."""
    request: ToolCallRequest
    result: ToolResult
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None
    
    @property
    def duration_ms(self) -> float:
        if self.completed_at:
            return (self.completed_at - self.started_at).total_seconds() * 1000
        return 0


class ToolRegistry:
    """Registry for all available tools.
    
    Inspired by omp's unified tool system:
    - Single namespace
    - Discovery and listing
    - Permission checking
    - Timeout handling
    """
    
    def __init__(self):
        self._tools: dict[str, ToolDefinition] = {}
        self._tool_instances: dict[str, BaseTool] = {}
        self._semaphore = asyncio.Semaphore(5)  # Max concurrent tools
        self._max_timeout = 60.0  # Default timeout
        self._settings: dict[str, bool] = {}  # Tool enable/disable
    
    def register(self, tool: BaseTool) -> None:
        """Register a tool."""
        defn = tool.to_definition()
        self._tools[defn.name] = defn
        self._tool_instances[defn.name] = tool
        logger.debug(f"Registered tool: {defn.name}")
    
    def register_function(
        self,
        name: str,
        description: str,
        category: ToolCategory,
        schema: ToolSchema,
        func: Callable[..., Any],
        **kwargs,
    ) -> None:
        """Register a function as a tool."""
        defn = ToolDefinition(
            name=name,
            description=description,
            category=category,
            schema=schema,
            execute=func,
            **kwargs,
        )
        self._tools[name] = defn
    
    def unregister(self, name: str) -> bool:
        """Unregister a tool."""
        if name in self._tools:
            del self._tools[name]
            self._tool_instances.pop(name, None)
            return True
        return False
    
    def get(self, name: str) -> ToolDefinition | None:
        """Get a tool definition."""
        return self._tools.get(name)
    
    def get_instance(self, name: str) -> BaseTool | None:
        """Get a tool instance."""
        return self._tool_instances.get(name)
    
    def list_tools(
        self,
        category: ToolCategory | None = None,
        include_hidden: bool = False,
        enabled_only: bool = True,
    ) -> list[ToolDefinition]:
        """List registered tools."""
        tools = []
        
        for tool in self._tools.values():
            # Filter by category
            if category and tool.category != category:
                continue
            
            # Filter hidden
            if tool.hidden and not include_hidden:
                continue
            
            # Filter disabled
            if enabled_only:
                if tool.setting_gated and not self._settings.get(tool.setting_gated, False):
                    continue
                if not tool.enabled:
                    continue
            
            tools.append(tool)
        
        return sorted(tools, key=lambda t: t.name)
    
    def list_categories(self) -> list[ToolCategory]:
        """List all categories with registered tools."""
        categories = set()
        for tool in self._tools.values():
            categories.add(tool.category)
        return sorted(categories, key=lambda c: c.value)
    
    def check_permission(self, tool_name: str, user_permissions: set[str]) -> bool:
        """Check if user has permission to use tool."""
        tool = self._tools.get(tool_name)
        if not tool or not tool.requires_permission:
            return True
        return tool.requires_permission in user_permissions
    
    def update_settings(self, settings: dict[str, bool]) -> None:
        """Update tool settings."""
        self._settings.update(settings)
    
    async def execute(
        self,
        request: ToolCallRequest,
    ) -> ToolCallResponse:
        """Execute a tool call with timeout and concurrency control."""
        started = datetime.now()
        timeout = request.timeout_seconds or self._max_timeout
        
        try:
            async with self._semaphore:
                tool = self._tool_instances.get(request.name)
                if not tool:
                    return ToolCallResponse(
                        request=request,
                        result=ToolResult(
                            tool_name=request.name,
                            success=False,
                            error=f"Tool not found: {request.name}",
                            is_error=True,
                        ),
                        started_at=started,
                        completed_at=datetime.now(),
                    )
                
                # Execute with timeout
                result = await asyncio.wait_for(
                    tool.execute(**request.arguments),
                    timeout=timeout,
                )
                
                # Ensure result is ToolResult
                if not isinstance(result, ToolResult):
                    result = ToolResult(
                        tool_name=request.name,
                        success=True,
                        content=[{"type": "text", "text": str(result)}],
                    )
                
                return ToolCallResponse(
                    request=request,
                    result=result,
                    started_at=started,
                    completed_at=datetime.now(),
                )
                
        except asyncio.TimeoutError:
            return ToolCallResponse(
                request=request,
                result=ToolResult(
                    tool_name=request.name,
                    success=False,
                    error=f"Tool execution timed out after {timeout}s",
                    is_error=True,
                ),
                started_at=started,
                completed_at=datetime.now(),
            )
        except Exception as e:
            logger.exception(f"Tool execution failed: {request.name}")
            return ToolCallResponse(
                request=request,
                result=ToolResult(
                    tool_name=request.name,
                    success=False,
                    error=str(e),
                    is_error=True,
                ),
                started_at=started,
                completed_at=datetime.now(),
            )
    
    def to_openai_format(self) -> list[dict[str, Any]]:
        """Convert to OpenAI function calling format."""
        tools = []
        for tool in self.list_tools():
            func = {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": {
                        "type": tool.schema.type,
                        "properties": tool.schema.properties,
                        "required": tool.schema.required,
                    },
                },
            }
            tools.append(func)
        return tools


# Global registry
_registry: ToolRegistry | None = None


def get_registry() -> ToolRegistry:
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry


def register_tool(tool: BaseTool) -> None:
    """Register a tool globally."""
    get_registry().register(tool)


def list_tools(**kwargs) -> list[ToolDefinition]:
    """List all registered tools."""
    return get_registry().list_tools(**kwargs)


def execute_tool(request: ToolCallRequest) -> ToolCallResponse:
    """Execute a tool globally."""
    return asyncio.run(get_registry().execute(request))
