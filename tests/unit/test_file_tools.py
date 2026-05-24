"""Unit tests for File Tools.

Tests for:
- ReadTool: read files, directories, with selectors
- WriteTool: create and overwrite files
- EditTool: hashline-based editing
- FindTool: glob-based file finding
"""

from __future__ import annotations

import pytest
from pathlib import Path

from src.infrastructure.tools.builtin.file_tools import (
    ReadTool,
    WriteTool,
    EditTool,
    FindTool,
    register_file_tools,
)
from src.infrastructure.tools.tool_registry import ToolRegistry


class TestReadTool:
    """Tests for ReadTool."""

    @pytest.fixture
    def tool(self):
        """Create ReadTool instance."""
        return ReadTool()

    @pytest.fixture
    def test_file(self, tmp_path):
        """Create test file."""
        file_path = tmp_path / "test.txt"
        file_path.write_text("line1\nline2\nline3\nline4\nline5")
        return file_path

    @pytest.mark.asyncio
    async def test_read_file(self, tool, test_file):
        """Test reading entire file."""
        result = await tool.execute(path=str(test_file))
        
        assert result.success is True
        content = result.content[0]["text"]
        assert "line1" in content

    @pytest.mark.asyncio
    async def test_read_nonexistent_file(self, tool, tmp_path):
        """Test reading nonexistent file."""
        result = await tool.execute(path=str(tmp_path / "missing.txt"))
        
        assert result.success is False

    def test_tool_properties(self, tool):
        """Test ReadTool name and description."""
        assert tool.name == "read"
        assert len(tool.description) > 0


class TestWriteTool:
    """Tests for WriteTool."""

    @pytest.fixture
    def tool(self):
        """Create WriteTool instance."""
        return WriteTool()

    @pytest.mark.asyncio
    async def test_write_new_file(self, tool, tmp_path):
        """Test creating new file."""
        file_path = tmp_path / "new.txt"
        
        result = await tool.execute(path=str(file_path), content="Hello, World!")
        
        assert result.success is True
        assert file_path.exists()

    def test_tool_properties(self, tool):
        """Test WriteTool name and description."""
        assert tool.name == "write"
        assert len(tool.description) > 0


class TestEditTool:
    """Tests for EditTool."""

    @pytest.fixture
    def tool(self):
        """Create EditTool instance."""
        return EditTool()

    @pytest.fixture
    def test_file(self, tmp_path):
        """Create test file."""
        file_path = tmp_path / "editable.txt"
        file_path.write_text("line1\nline2\nline3")
        return file_path

    @pytest.mark.asyncio
    async def test_edit_success(self, tool, test_file):
        """Test successful edit."""
        result = await tool.execute(
            path=str(test_file),
            old="line2",
            new="modified_line2",
        )
        
        assert result.success is True

    def test_tool_properties(self, tool):
        """Test EditTool name and description."""
        assert tool.name == "edit"
        assert len(tool.description) > 0


class TestFindTool:
    """Tests for FindTool."""

    @pytest.fixture
    def tool(self):
        """Create FindTool instance."""
        return FindTool()

    @pytest.fixture
    def test_dir(self, tmp_path):
        """Create test directory structure."""
        (tmp_path / "file1.py").write_text("code")
        (tmp_path / "file2.txt").write_text("text")
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "file3.py").write_text("more code")
        return tmp_path

    @pytest.mark.asyncio
    async def test_find_by_extension(self, tool, test_dir):
        """Test finding files by extension."""
        result = await tool.execute(
            path=str(test_dir),
            pattern="**/*.py",
        )
        
        assert result.success is True
        content = result.content[0]["text"]
        assert "file1.py" in content or "file3.py" in content

    def test_tool_properties(self, tool):
        """Test FindTool name and description."""
        assert tool.name == "find"
        assert len(tool.description) > 0


class TestRegisterFileTools:
    """Tests for register_file_tools function."""

    def test_register_all_tools(self):
        """Test registering all file tools."""
        registry = ToolRegistry()
        
        register_file_tools(registry)
        
        tool_names = [t.name for t in registry.list_tools()]
        assert "read" in tool_names
        assert "write" in tool_names
        assert "edit" in tool_names
        assert "find" in tool_names
