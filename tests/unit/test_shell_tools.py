"""Unit tests for Shell Tools.

Tests for:
- BashTool: command execution
- PwdTool: print working directory
- CdTool: change directory
"""

from __future__ import annotations

import asyncio
import pytest
import os
from pathlib import Path

from src.infrastructure.tools.builtin.shell_tools import (
    BashTool,
    PwdTool,
    CdTool,
    register_shell_tools,
)
from src.infrastructure.tools.tool_registry import ToolRegistry


class TestBashTool:
    """Tests for BashTool."""

    @pytest.fixture
    def tool(self):
        """Create BashTool instance."""
        return BashTool()

    def test_tool_properties(self, tool):
        """Test tool name and description."""
        assert tool.name == "bash"
        assert len(tool.description) > 0


class TestPwdTool:
    """Tests for PwdTool."""

    @pytest.fixture
    def tool(self):
        """Create PwdTool instance."""
        return PwdTool()

    @pytest.mark.asyncio
    async def test_pwd_basic(self, tool):
        """Test basic pwd."""
        result = await tool.execute()
        
        assert result.success is True
        content = result.content[0]["text"]
        assert len(content.strip()) > 0

    def test_tool_properties(self, tool):
        """Test tool name."""
        assert tool.name == "pwd"


class TestCdTool:
    """Tests for CdTool."""

    @pytest.fixture
    def tool(self):
        """Create CdTool instance."""
        return CdTool()

    def test_tool_properties(self, tool):
        """Test tool name."""
        assert tool.name == "cd"


class TestRegisterShellTools:
    """Tests for register_shell_tools function."""

    def test_register_all_tools(self):
        """Test registering all shell tools."""
        registry = ToolRegistry()
        
        register_shell_tools(registry)
        
        tool_names = [t.name for t in registry.list_tools()]
        assert "bash" in tool_names
        assert "pwd" in tool_names
        assert "cd" in tool_names
