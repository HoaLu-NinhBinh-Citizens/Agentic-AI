"""Tool schema normalizer with versioning support.

Converts MCP tool schemas to a unified format that all LLM providers can use.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

UNIFIED_TOOL_SCHEMA_VERSION = "1.0"


class ToolSchemaError(Exception):
    """Error during tool schema validation or conversion."""

    pass


def get_schema_version() -> str:
    """Get the current unified tool schema version.

    Returns:
        Schema version string.
    """
    return UNIFIED_TOOL_SCHEMA_VERSION


def is_schema_compatible(schema_version: str) -> bool:
    """Check if a schema version is compatible with current version.

    Args:
        schema_version: Version to check.

    Returns:
        True if compatible.
    """
    if not schema_version:
        return False
    current = UNIFIED_TOOL_SCHEMA_VERSION.split(".")
    requested = schema_version.split(".")
    return current[0] == requested[0]


def validate_mcp_tool(mcp_tool: dict[str, Any]) -> bool:
    """Validate that an MCP tool has required fields.

    Args:
        mcp_tool: MCP tool definition.

    Returns:
        True if valid.

    Raises:
        ToolSchemaError: If validation fails.
    """
    required_fields = ["name", "description", "inputSchema"]

    for field in required_fields:
        if field not in mcp_tool:
            raise ToolSchemaError(f"MCP tool missing required field: {field}")

    if "type" in mcp_tool and mcp_tool["type"] != "function":
        raise ToolSchemaError(f"Invalid tool type: {mcp_tool['type']}")

    input_schema = mcp_tool.get("inputSchema", {})
    if "type" in input_schema and input_schema["type"] != "object":
        raise ToolSchemaError(f"inputSchema must be type 'object', got: {input_schema['type']}")

    return True


def convert_mcp_to_unified(mcp_tool: dict[str, Any]) -> dict[str, Any] | None:
    """Convert an MCP tool definition to unified format.

    Args:
        mcp_tool: MCP tool definition with name, description, inputSchema.

    Returns:
        Unified tool definition, or None if conversion fails.
    """
    try:
        validate_mcp_tool(mcp_tool)

        input_schema = mcp_tool.get("inputSchema", {})

        required: list[str] = []
        properties: dict[str, Any] = {}

        if "required" in input_schema:
            required = input_schema["required"]
        if "properties" in input_schema:
            properties = input_schema["properties"]

        return {
            "type": "function",
            "function": {
                "name": mcp_tool["name"],
                "description": mcp_tool.get("description", ""),
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
            "schema_version": UNIFIED_TOOL_SCHEMA_VERSION,
        }

    except ToolSchemaError as e:
        logger.warning("Failed to convert MCP tool: %s", str(e))
        return None
    except Exception as e:
        logger.error("Unexpected error converting MCP tool: %s", str(e))
        return None


def convert_unified_to_openai(unified_tool: dict[str, Any]) -> dict[str, Any]:
    """Convert unified tool format to OpenAI tool format.

    Args:
        unified_tool: Unified tool definition.

    Returns:
        OpenAI-compatible tool definition.
    """
    func = unified_tool.get("function", {})
    return {
        "type": "function",
        "function": {
            "name": func.get("name", ""),
            "description": func.get("description", ""),
            "parameters": func.get("parameters", {}),
        },
    }


def convert_unified_to_anthropic(unified_tool: dict[str, Any]) -> dict[str, Any]:
    """Convert unified tool format to Anthropic tool format.

    Args:
        unified_tool: Unified tool definition.

    Returns:
        Anthropic-compatible tool definition.
    """
    func = unified_tool.get("function", {})
    params = func.get("parameters", {})

    return {
        "name": func.get("name", ""),
        "description": func.get("description", ""),
        "input_schema": params,
    }


def convert_unified_to_ollama(unified_tool: dict[str, Any]) -> dict[str, Any]:
    """Convert unified tool format to Ollama tool format.

    Args:
        unified_tool: Unified tool definition.

    Returns:
        Ollama-compatible tool definition.
    """
    func = unified_tool.get("function", {})
    params = func.get("parameters", {})

    return {
        "type": "function",
        "function": {
            "name": func.get("name", ""),
            "description": func.get("description", ""),
            "parameters": params,
        },
    }


def convert_unified_to_groq(unified_tool: dict[str, Any]) -> dict[str, Any]:
    """Convert unified tool format to Groq-compatible format.

    Groq uses OpenAI-compatible tool format.

    Args:
        unified_tool: Unified tool definition.

    Returns:
        Groq-compatible tool definition.
    """
    return convert_unified_to_openai(unified_tool)


def normalize_tools(
    mcp_tools: list[dict[str, Any]],
    provider_type: str = "openai",
) -> list[dict[str, Any]]:
    """Normalize a list of MCP tools for a specific provider.

    Args:
        mcp_tools: List of MCP tool definitions.
        provider_type: Target provider type (openai, anthropic, ollama, groq).

    Returns:
        List of provider-compatible tool definitions.
    """
    unified = []

    for mcp_tool in mcp_tools:
        converted = convert_mcp_to_unified(mcp_tool)
        if converted:
            unified.append(converted)

    converters = {
        "openai": convert_unified_to_openai,
        "anthropic": convert_unified_to_anthropic,
        "ollama": convert_unified_to_ollama,
        "groq": convert_unified_to_groq,
    }

    converter = converters.get(provider_type, convert_unified_to_openai)
    return [converter(tool) for tool in unified]


def add_tool_metadata(
    tool: dict[str, Any],
    provider_name: str,
    provider_version: str | None = None,
) -> dict[str, Any]:
    """Add metadata to a tool definition.

    Args:
        tool: Tool definition.
        provider_name: Name of the provider.
        provider_version: Optional version of the provider.

    Returns:
        Tool with added metadata.
    """
    metadata = {
        "provider": provider_name,
        "schema_version": UNIFIED_TOOL_SCHEMA_VERSION,
    }
    if provider_version:
        metadata["provider_version"] = provider_version

    return {
        **tool,
        "_metadata": metadata,
    }
