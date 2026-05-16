"""Unit tests for tool schema normalizer."""

import pytest

from infrastructure.llm.tool_schema import (
    UNIFIED_TOOL_SCHEMA_VERSION,
    get_schema_version,
    is_schema_compatible,
    validate_mcp_tool,
    convert_mcp_to_unified,
    normalize_tools,
    convert_unified_to_openai,
    convert_unified_to_anthropic,
    convert_unified_to_groq,
    ToolSchemaError,
)


class TestToolSchemaVersion:
    """Tests for schema versioning."""

    def test_get_schema_version(self):
        """Test getting schema version."""
        assert get_schema_version() == UNIFIED_TOOL_SCHEMA_VERSION

    def test_schema_compatible_same_version(self):
        """Test schema compatibility with same version."""
        assert is_schema_compatible("1.0")

    def test_schema_compatible_different_major(self):
        """Test schema incompatibility with different major version."""
        assert not is_schema_compatible("2.0")

    def test_schema_compatible_empty(self):
        """Test schema incompatibility with empty version."""
        assert not is_schema_compatible("")


class TestValidateMcpTool:
    """Tests for MCP tool validation."""

    def test_valid_tool(self):
        """Test validating a valid tool."""
        tool = {
            "name": "read_file",
            "description": "Read a file",
            "inputSchema": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        }
        assert validate_mcp_tool(tool)

    def test_missing_name(self):
        """Test validation fails for missing name."""
        tool = {
            "description": "Read a file",
            "inputSchema": {"type": "object"},
        }
        with pytest.raises(ToolSchemaError, match="name"):
            validate_mcp_tool(tool)

    def test_missing_description(self):
        """Test validation fails for missing description."""
        tool = {
            "name": "read_file",
            "inputSchema": {"type": "object"},
        }
        with pytest.raises(ToolSchemaError, match="description"):
            validate_mcp_tool(tool)

    def test_missing_input_schema(self):
        """Test validation fails for missing inputSchema."""
        tool = {
            "name": "read_file",
            "description": "Read a file",
        }
        with pytest.raises(ToolSchemaError, match="inputSchema"):
            validate_mcp_tool(tool)


class TestConvertMcpToUnified:
    """Tests for MCP to unified conversion."""

    def test_basic_conversion(self):
        """Test basic MCP to unified conversion."""
        mcp_tool = {
            "name": "read_file",
            "description": "Read a file from the filesystem",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path"},
                },
                "required": ["path"],
            },
        }

        unified = convert_mcp_to_unified(mcp_tool)

        assert unified is not None
        assert unified["type"] == "function"
        assert unified["function"]["name"] == "read_file"
        assert unified["function"]["description"] == "Read a file from the filesystem"
        assert unified["function"]["parameters"]["type"] == "object"
        assert "path" in unified["function"]["parameters"]["properties"]
        assert "path" in unified["function"]["parameters"]["required"]

    def test_conversion_with_invalid_tool(self):
        """Test conversion returns None for invalid tool."""
        result = convert_mcp_to_unified({"name": "test"})
        assert result is None

    def test_conversion_preserves_schema_version(self):
        """Test conversion includes schema version."""
        mcp_tool = {
            "name": "read_file",
            "description": "Read a file",
            "inputSchema": {"type": "object", "properties": {}},
        }

        unified = convert_mcp_to_unified(mcp_tool)
        assert unified["schema_version"] == UNIFIED_TOOL_SCHEMA_VERSION


class TestNormalizeTools:
    """Tests for tool normalization."""

    def test_normalize_for_openai(self):
        """Test normalizing tools for OpenAI."""
        mcp_tools = [
            {
                "name": "read_file",
                "description": "Read a file",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "write_file",
                "description": "Write a file",
                "inputSchema": {"type": "object", "properties": {}},
            },
        ]

        tools = normalize_tools(mcp_tools, "openai")

        assert len(tools) == 2
        assert tools[0]["type"] == "function"
        assert "parameters" in tools[0]["function"]

    def test_normalize_for_anthropic(self):
        """Test normalizing tools for Anthropic."""
        mcp_tools = [
            {
                "name": "read_file",
                "description": "Read a file",
                "inputSchema": {"type": "object", "properties": {}},
            },
        ]

        tools = normalize_tools(mcp_tools, "anthropic")

        assert len(tools) == 1
        assert "name" in tools[0]
        assert "input_schema" in tools[0]

    def test_normalize_filters_invalid(self):
        """Test that invalid tools are filtered out."""
        mcp_tools = [
            {
                "name": "read_file",
                "description": "Read a file",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {"name": "invalid"},  # Missing required fields
        ]

        tools = normalize_tools(mcp_tools, "openai")
        assert len(tools) == 1
        assert tools[0]["function"]["name"] == "read_file"


class TestProviderConversions:
    """Tests for provider-specific conversions."""

    def test_convert_to_openai(self):
        """Test converting to OpenAI format."""
        unified = {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read a file",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                },
            },
        }

        openai = convert_unified_to_openai(unified)

        assert openai["type"] == "function"
        assert openai["function"]["name"] == "read_file"

    def test_convert_to_anthropic(self):
        """Test converting to Anthropic format."""
        unified = {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read a file",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                },
            },
        }

        anthropic = convert_unified_to_anthropic(unified)

        assert anthropic["name"] == "read_file"
        assert "input_schema" in anthropic

    def test_convert_to_groq(self):
        """Test converting to Groq format (same as OpenAI)."""
        unified = {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read a file",
                "parameters": {"type": "object", "properties": {}},
            },
        }

        groq = convert_unified_to_groq(unified)

        assert groq["type"] == "function"
        assert groq["function"]["name"] == "read_file"
