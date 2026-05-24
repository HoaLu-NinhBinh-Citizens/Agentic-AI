"""Builtin file tools for Agentic-AI CLI.

Tools:
- read: Summarized file reading with selectors
- write: Create or overwrite files
- edit: Hashline-based editing
- find: Glob-based path lookup
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

from .hashline import HashlineEditor, HashlinePatch, edit_file, preview_edit
from .tool_registry import (
    BaseTool,
    ToolCategory,
    ToolResult,
    ToolSchema,
)


class ReadTool(BaseTool):
    """Read files with summarization and selectors.
    
    Like omp's read tool:
    - Summarized snippets
    - Ideal defaults
    - Selector hit rate optimization
    """
    
    name = "read"
    description = "Read file content with optional line range or content selector"
    category = ToolCategory.FILES
    
    schema = ToolSchema(
        description="Read file content",
        properties={
            "path": {
                "type": "string",
                "description": "File path to read",
            },
            "start": {
                "type": "integer",
                "description": "Start line number (1-indexed)",
            },
            "end": {
                "type": "integer", 
                "description": "End line number (inclusive)",
            },
            "selector": {
                "type": "string",
                "description": "Content selector (regex or text snippet)",
            },
            "limit": {
                "type": "integer",
                "description": "Max lines to return",
                "default": 100,
            },
            "summarize": {
                "type": "boolean",
                "description": "Summarize long files instead of dumping content",
                "default": False,
            },
        },
        required=["path"],
    )
    
    async def execute(self, path: str, **kwargs) -> ToolResult:
        """Execute read."""
        try:
            file_path = Path(path)
            
            if not file_path.exists():
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    error=f"File not found: {path}",
                    is_error=True,
                )
            
            if file_path.is_dir():
                return await self._read_directory(file_path, **kwargs)
            
            return await self._read_file(file_path, **kwargs)
            
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=str(e),
                is_error=True,
            )
    
    async def _read_file(self, path: Path, **kwargs) -> ToolResult:
        """Read a file."""
        try:
            content = path.read_text(encoding="utf-8")
            lines = content.splitlines()
            
            start = kwargs.get("start", 1) - 1  # Convert to 0-indexed
            end = kwargs.get("end", len(lines))
            limit = kwargs.get("limit", 100)
            selector = kwargs.get("selector")
            summarize = kwargs.get("summarize", False)
            
            # Apply selector
            if selector:
                matched_lines = []
                for i, line in enumerate(lines):
                    if re.search(selector, line):
                        matched_lines.append((i, line))
                
                if not matched_lines:
                    return ToolResult(
                        tool_name=self.name,
                        success=True,
                        content=[{"type": "text", "text": f"No matches for selector: {selector}"}],
                    )
                
                # Return context around matches
                result_lines = []
                for idx, line_num in matched_lines[:limit]:
                    context_start = max(0, idx - 2)
                    context_end = min(len(lines), idx + 3)
                    
                    if result_lines and context_start <= result_lines[-1][0]:
                        result_lines[-1] = (context_start, lines[context_start:context_end])
                    else:
                        result_lines.append((context_start, lines[context_start:context_end]))
                
                output = []
                for start_idx, context in result_lines:
                    output.append(f"... (line {start_idx + 1}) ...")
                    output.extend(context)
                
                return ToolResult(
                    tool_name=self.name,
                    success=True,
                    content=[{"type": "text", "text": "\n".join(output)}],
                )
            
            # Apply line range
            if start is not None and end is not None:
                selected_lines = lines[start:end]
            else:
                selected_lines = lines[:limit] if limit else lines
            
            # Summarize if too long
            if summarize and len(selected_lines) > limit:
                summary = self._summarize(selected_lines)
                return ToolResult(
                    tool_name=self.name,
                    success=True,
                    content=[{"type": "text", "text": summary}],
                )
            
            text = "\n".join(selected_lines)
            return ToolResult(
                tool_name=self.name,
                success=True,
                content=[{"type": "text", "text": text}],
            )
            
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=f"Error reading {path}: {e}",
                is_error=True,
            )
    
    async def _read_directory(self, path: Path, **kwargs) -> ToolResult:
        """Read directory listing."""
        try:
            entries = []
            for item in sorted(path.iterdir()):
                entry_type = "dir" if item.is_dir() else "file"
                size = ""
                if item.is_file():
                    try:
                        size = f" ({item.stat().st_size} bytes)"
                    except:
                        pass
                entries.append(f"{'[D] ' if entry_type == 'dir' else ''}{item.name}{size}")
            
            text = "\n".join(entries)
            return ToolResult(
                tool_name=self.name,
                success=True,
                content=[{"type": "text", "text": text}],
            )
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=str(e),
                is_error=True,
            )
    
    def _summarize(self, lines: list[str]) -> str:
        """Summarize file content."""
        # Simple summarization - show structure and key lines
        summary = [f"[File summary: {len(lines)} lines total]"]
        
        # Show first 20 lines
        summary.append("\n--- First 20 lines ---")
        summary.extend(lines[:20])
        
        if len(lines) > 40:
            summary.append(f"\n... ({len(lines) - 40} lines omitted) ...\n")
            summary.append("--- Last 20 lines ---")
            summary.extend(lines[-20:])
        
        return "\n".join(summary)


class WriteTool(BaseTool):
    """Write/create files."""
    
    name = "write"
    description = "Create or overwrite a file with content"
    category = ToolCategory.FILES
    
    schema = ToolSchema(
        description="Write file content",
        properties={
            "path": {
                "type": "string",
                "description": "File path to write",
            },
            "content": {
                "type": "string",
                "description": "Content to write",
            },
            "append": {
                "type": "boolean",
                "description": "Append to existing file instead of overwriting",
                "default": False,
            },
        },
        required=["path", "content"],
    )
    
    async def execute(self, path: str, content: str, **kwargs) -> ToolResult:
        """Execute write."""
        try:
            file_path = Path(path)
            
            # Create parent directories
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            mode = "a" if kwargs.get("append") else "w"
            
            with open(file_path, mode, encoding="utf-8") as f:
                f.write(content)
            
            action = "Appended to" if kwargs.get("append") else "Wrote"
            return ToolResult(
                tool_name=self.name,
                success=True,
                content=[{"type": "text", "text": f"{action} {path} ({len(content)} bytes)"}],
            )
            
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=str(e),
                is_error=True,
            )


class EditTool(BaseTool):
    """Edit files using hashline approach."""
    
    name = "edit"
    description = "Edit file content using hashline anchors for reliability"
    category = ToolCategory.EDIT
    
    schema = ToolSchema(
        description="Edit file content",
        properties={
            "path": {
                "type": "string",
                "description": "File path to edit",
            },
            "old": {
                "type": "string",
                "description": "Content to replace (exact text or regex)",
            },
            "new": {
                "type": "string",
                "description": "Replacement content",
            },
            "preview": {
                "type": "boolean",
                "description": "Preview edit without applying",
                "default": False,
            },
        },
        required=["path", "old", "new"],
    )
    
    async def execute(self, path: str, old: str, new: str, **kwargs) -> ToolResult:
        """Execute edit."""
        try:
            file_path = Path(path)
            
            if kwargs.get("preview"):
                output = preview_edit(file_path, old, new)
                return ToolResult(
                    tool_name=self.name,
                    success=True,
                    content=[{"type": "text", "text": output}],
                    details={"preview": True},
                )
            
            result = edit_file(file_path, old, new)
            
            if result.success:
                return ToolResult(
                    tool_name=self.name,
                    success=True,
                    content=[{"type": "text", "text": f"Edited {path}: {result.lines_changed:+d} lines"}],
                    details={"lines_changed": result.lines_changed},
                )
            else:
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    error=result.error or "Edit failed",
                    is_error=True,
                )
                
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=str(e),
                is_error=True,
            )


class FindTool(BaseTool):
    """Find files using glob patterns."""
    
    name = "find"
    description = "Find files using glob patterns"
    category = ToolCategory.FILES
    
    schema = ToolSchema(
        description="Find files by glob pattern",
        properties={
            "path": {
                "type": "string",
                "description": "Root path to search",
            },
            "pattern": {
                "type": "string",
                "description": "Glob pattern (e.g., '**/*.py')",
            },
            "type": {
                "type": "string",
                "enum": ["file", "dir", "all"],
                "description": "Filter by type",
                "default": "file",
            },
        },
        required=["path", "pattern"],
    )
    
    async def execute(self, path: str, pattern: str, **kwargs) -> ToolResult:
        """Execute find."""
        try:
            root = Path(path)
            file_type = kwargs.get("type", "file")
            
            if not root.exists():
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    error=f"Path not found: {path}",
                    is_error=True,
                )
            
            matches = list(root.glob(pattern))
            
            # Filter by type
            if file_type == "file":
                matches = [m for m in matches if m.is_file()]
            elif file_type == "dir":
                matches = [m for m in matches if m.is_dir()]
            
            # Limit results
            max_results = kwargs.get("limit", 100)
            matches = matches[:max_results]
            
            if not matches:
                return ToolResult(
                    tool_name=self.name,
                    success=True,
                    content=[{"type": "text", "text": f"No files found matching {pattern}"}],
                )
            
            output = [f"[{len(matches)} matches]"]
            for m in matches:
                rel = m.relative_to(root) if m.is_relative_to(root) else m
                output.append(str(rel))
            
            return ToolResult(
                tool_name=self.name,
                success=True,
                content=[{"type": "text", "text": "\n".join(output)}],
            )
            
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=str(e),
                is_error=True,
            )


# Register all file tools
def register_file_tools(registry):
    """Register all file tools to a registry."""
    registry.register(ReadTool())
    registry.register(WriteTool())
    registry.register(EditTool())
    registry.register(FindTool())
