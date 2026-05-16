"""
Tool Schema Definitions

Core data structures for tools.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union
from uuid import uuid4


class ParameterType(Enum):
    """Parameter type definitions."""

    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"
    FILE_PATH = "file_path"
    DIRECTORY_PATH = "directory_path"
    CHOICE = "choice"


class ToolCategory(Enum):
    """Tool category definitions."""

    FILE = "file"
    SHELL = "shell"
    GIT = "git"
    SEARCH = "search"
    MEMORY = "memory"
    LLM = "llm"
    RETRIEVAL = "retrieval"
    BUILD = "build"
    FLASH = "flash"
    MONITORING = "monitoring"
    CUSTOM = "custom"


class ToolPermission(Enum):
    """Tool permission levels."""

    READ = "read"  # Read-only operations
    WRITE = "write"  # Write operations
    EXECUTE = "execute"  # Execute commands
    NETWORK = "network"  # Network operations
    FILESYSTEM = "filesystem"  # Full filesystem access
    FLASH = "flash"  # Hardware flash/programming operations
    DANGEROUS = "dangerous"  # Potentially destructive operations
    SYSTEM = "system"  # System-level operations (admin)


@dataclass
class ToolParameter:
    """
    Tool parameter definition.

    Attributes:
        name: Parameter name
        type: Parameter type
        description: Human-readable description
        required: Whether parameter is required
        default: Default value if optional
        choices: Valid choices for CHOICE type
        pattern: Regex pattern for STRING type
        min_value: Minimum value for NUMBER types
        max_value: Maximum value for NUMBER types
    """

    name: str
    type: ParameterType
    description: str = ""
    required: bool = True
    default: Any = None
    choices: Optional[List[str]] = None
    pattern: Optional[str] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None

    def validate(self, value: Any) -> tuple[bool, Optional[str]]:
        """
        Validate a parameter value.

        Args:
            value: Value to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        if value is None:
            if self.required:
                return False, f"Parameter '{self.name}' is required"
            return True, None

        # Type validation
        if self.type == ParameterType.STRING:
            if not isinstance(value, str):
                return False, f"Parameter '{self.name}' must be a string"
            if self.pattern:
                import re
                if not re.match(self.pattern, value):
                    return False, f"Parameter '{self.name}' does not match pattern {self.pattern}"

        elif self.type == ParameterType.INTEGER:
            if not isinstance(value, int) or isinstance(value, bool):
                return False, f"Parameter '{self.name}' must be an integer"
            if self.min_value is not None and value < self.min_value:
                return False, f"Parameter '{self.name}' must be >= {self.min_value}"
            if self.max_value is not None and value > self.max_value:
                return False, f"Parameter '{self.name}' must be <= {self.max_value}"

        elif self.type == ParameterType.FLOAT:
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                return False, f"Parameter '{self.name}' must be a number"
            if self.min_value is not None and value < self.min_value:
                return False, f"Parameter '{self.name}' must be >= {self.min_value}"
            if self.max_value is not None and value > self.max_value:
                return False, f"Parameter '{self.name}' must be <= {self.max_value}"

        elif self.type == ParameterType.BOOLEAN:
            if not isinstance(value, bool):
                return False, f"Parameter '{self.name}' must be a boolean"

        elif self.type == ParameterType.CHOICE:
            if self.choices and value not in self.choices:
                return False, f"Parameter '{self.name}' must be one of {self.choices}"

        elif self.type == ParameterType.ARRAY:
            if not isinstance(value, list):
                return False, f"Parameter '{self.name}' must be an array"

        elif self.type == ParameterType.OBJECT:
            if not isinstance(value, dict):
                return False, f"Parameter '{self.name}' must be an object"

        elif self.type in (ParameterType.FILE_PATH, ParameterType.DIRECTORY_PATH):
            if not isinstance(value, str):
                return False, f"Parameter '{self.name}' must be a path string"

        return True, None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "type": self.type.value,
            "description": self.description,
            "required": self.required,
            "default": self.default,
            "choices": self.choices,
        }


@dataclass
class Tool:
    """
    Tool definition.

    Attributes:
        name: Tool name (unique identifier)
        description: Human-readable description
        category: Tool category
        parameters: List of parameter definitions
        returns: Return type description
        permissions: Required permissions
        timeout: Execution timeout in seconds
        cacheable: Whether results can be cached
        retryable: Whether tool can be retried on failure
        handler: The actual function to execute
        tags: Additional tags for categorization
        examples: Example usage
    """

    name: str
    description: str
    category: ToolCategory = ToolCategory.CUSTOM
    parameters: List[ToolParameter] = field(default_factory=list)
    returns: str = ""
    permissions: List[ToolPermission] = field(default_factory=list)
    timeout: int = 30
    cacheable: bool = True
    retryable: bool = True
    handler: Optional[Callable] = None
    tags: List[str] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)
    version: str = "1.0.0"
    author: str = ""

    def __post_init__(self):
        """Validate tool after initialization."""
        if not self.name:
            raise ValueError("Tool name is required")
        if not self.description:
            raise ValueError("Tool description is required")

    def get_parameter(self, name: str) -> Optional[ToolParameter]:
        """Get parameter by name."""
        for param in self.parameters:
            if param.name == name:
                return param
        return None

    def validate_params(self, params: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """
        Validate all parameters.

        Args:
            params: Parameters to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check for unknown parameters
        valid_names = {p.name for p in self.parameters}
        for key in params:
            if key not in valid_names:
                return False, f"Unknown parameter: '{key}'"

        # Validate each parameter
        for param in self.parameters:
            value = params.get(param.name, param.default)
            is_valid, error = param.validate(value)
            if not is_valid:
                return False, error

        return True, None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category.value,
            "parameters": [p.to_dict() for p in self.parameters],
            "returns": self.returns,
            "permissions": [p.value for p in self.permissions],
            "timeout": self.timeout,
            "cacheable": self.cacheable,
            "retryable": self.retryable,
            "tags": self.tags,
            "examples": self.examples,
            "version": self.version,
        }


@dataclass
class ToolResult:
    """
    Tool execution result.

    Attributes:
        tool_name: Name of the tool that was executed
        success: Whether execution was successful
        output: Tool output (if successful)
        error: Error message (if failed)
        error_type: Type of error
        execution_time_ms: Execution time in milliseconds
        cached: Whether result was from cache
        timestamp: When execution completed
        metadata: Additional metadata
    """

    tool_name: str
    success: bool
    output: Any = None
    error: Optional[str] = None
    error_type: Optional[str] = None
    execution_time_ms: float = 0.0
    cached: bool = False
    timestamp: datetime = field(default_factory=datetime.now)
    id: str = field(default_factory=lambda: str(uuid4()))
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "tool_name": self.tool_name,
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "error_type": self.error_type,
            "execution_time_ms": self.execution_time_ms,
            "cached": self.cached,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolResult":
        """Create from dictionary."""
        return cls(
            id=data.get("id", str(uuid4())),
            tool_name=data["tool_name"],
            success=data["success"],
            output=data.get("output"),
            error=data.get("error"),
            error_type=data.get("error_type"),
            execution_time_ms=data.get("execution_time_ms", 0.0),
            cached=data.get("cached", False),
            timestamp=datetime.fromisoformat(data["timestamp"])
            if "timestamp" in data
            else datetime.now(),
            metadata=data.get("metadata", {}),
        )


@dataclass
class ToolExecutionRequest:
    """Request to execute a tool."""

    tool_name: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    context: Optional[Dict[str, Any]] = None
    use_cache: bool = True
    timeout: Optional[int] = None

    def get_cache_key(self) -> str:
        """Generate cache key for this request."""
        import hashlib
        import json

        key_data = {
            "tool": self.tool_name,
            "params": self.parameters,
        }
        key_str = json.dumps(key_data, sort_keys=True, default=str)
        return hashlib.sha256(key_str.encode()).hexdigest()[:32]


# Decorators for defining tools
def tool(
    name: str,
    description: str,
    category: ToolCategory = ToolCategory.CUSTOM,
    parameters: Optional[List[ToolParameter]] = None,
    returns: str = "",
    permissions: Optional[List[ToolPermission]] = None,
    timeout: int = 30,
    cacheable: bool = True,
    tags: Optional[List[str]] = None,
):
    """
    Decorator to define a tool.

    Usage:
        @tool(
            name="read_file",
            description="Read contents of a file",
            category=ToolCategory.FILE,
            parameters=[
                ToolParameter(name="path", type=ParameterType.FILE_PATH, description="File path"),
            ],
            permissions=[ToolPermission.READ],
        )
        def read_file(params):
            with open(params["path"]) as f:
                return f.read()
    """

    def decorator(func: Callable) -> Tool:
        tool_def = Tool(
            name=name,
            description=description,
            category=category,
            parameters=parameters or [],
            returns=returns,
            permissions=permissions or [],
            timeout=timeout,
            cacheable=cacheable,
            handler=func,
            tags=tags or [],
        )
        return tool_def

    return decorator


def register_tool(tool_def: Tool, registry: "ToolRegistry" = None):
    """
    Register a tool with the global registry.

    Args:
        tool_def: Tool definition
        registry: Optional specific registry, else uses global
    """
    if registry is None:
        from src.core.tools.registry import get_tool_registry

        registry = get_tool_registry()

    registry.register(tool_def)
