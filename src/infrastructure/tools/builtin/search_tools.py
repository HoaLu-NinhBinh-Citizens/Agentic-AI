"""Search tools for Agentic-AI CLI.

Tools:
- search: Regex search over files (like ripgrep)
- grep: Alias for search
"""

from __future__ import annotations

import asyncio
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .tool_registry import (
    BaseTool,
    ToolCategory,
    ToolResult,
    ToolSchema,
)


@dataclass
class SearchMatch:
    """A search match result."""
    file: str
    line: int
    column: int
    content: str
    context_before: list[str] | None = None
    context_after: list[str] | None = None


class SearchTool(BaseTool):
    """Regex search over files.
    
    Like omp's search tool:
    - Uses ripgrep when available (fastest)
    - Falls back to Python regex
    - JSON output for structured results
    - Context lines support
    """
    
    name = "search"
    description = "Search for regex pattern in files"
    category = ToolCategory.SEARCH
    
    schema = ToolSchema(
        description="Search for regex pattern",
        properties={
            "pattern": {
                "type": "string",
                "description": "Regex pattern to search for",
            },
            "paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "File or directory paths to search",
            },
            "glob": {
                "type": "string",
                "description": "File glob pattern to filter (e.g., '*.py')",
            },
            "case_sensitive": {
                "type": "boolean",
                "description": "Case sensitive search",
                "default": False,
            },
            "regex": {
                "type": "boolean",
                "description": "Treat pattern as regex (default: True)",
                "default": True,
            },
            "whole_word": {
                "type": "boolean",
                "description": "Match whole words only",
                "default": False,
            },
            "context_before": {
                "type": "integer",
                "description": "Lines of context before match",
                "default": 0,
            },
            "context_after": {
                "type": "integer",
                "description": "Lines of context after match",
                "default": 0,
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of matches",
                "default": 100,
            },
            "include_binary": {
                "type": "boolean",
                "description": "Include binary files",
                "default": False,
            },
            "json_output": {
                "type": "boolean",
                "description": "Output as JSON",
                "default": False,
            },
        },
        required=["pattern", "paths"],
    )
    
    async def execute(self, pattern: str, paths: list[str], **kwargs) -> ToolResult:
        """Execute search."""
        try:
            # Try ripgrep first
            result = await self._search_ripgrep(pattern, paths, **kwargs)
            if result is not None:
                return result
            
            # Fall back to Python implementation
            return await self._search_python(pattern, paths, **kwargs)
            
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=str(e),
                is_error=True,
            )
    
    async def _search_ripgrep(self, pattern: str, paths: list[str], **kwargs) -> ToolResult | None:
        """Search using ripgrep if available."""
        try:
            cmd = ["rg", "--json"]
            
            # Add flags
            if not kwargs.get("case_sensitive", False):
                cmd.append("--ignore-case")
            
            if kwargs.get("whole_word", False):
                cmd.append("-w")
            
            if not kwargs.get("include_binary", False):
                cmd.append("--binary-files=without-match")
            
            # Context
            context_before = kwargs.get("context_before", 0)
            context_after = kwargs.get("context_after", 0)
            if context_before:
                cmd.extend(["-B", str(context_before)])
            if context_after:
                cmd.extend(["-A", str(context_after)])
            
            # Limit
            max_results = kwargs.get("max_results", 100)
            cmd.extend(["--max-count", str(max_results)])
            
            # Glob filter
            if kwargs.get("glob"):
                cmd.extend(["-g", kwargs["glob"]])
            
            # Pattern
            cmd.append(pattern)
            
            # Paths
            cmd.extend(paths)
            
            # Run ripgrep
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=30.0,
            )
            
            if proc.returncode not in (0, 1):  # 0 = match, 1 = no match
                return None  # Fall back to Python
            
            return self._parse_rg_output(stdout, kwargs.get("json_output", False))
            
        except FileNotFoundError:
            return None  # ripgrep not installed
        except asyncio.TimeoutError:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error="Search timed out",
                is_error=True,
            )
        except Exception:
            return None  # Fall back to Python
    
    def _parse_rg_output(self, stdout: bytes, json_output: bool) -> ToolResult:
        """Parse ripgrep JSON output."""
        matches = []
        
        for line in stdout.decode("utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            
            try:
                obj = json.loads(line)
                
                if obj.get("type") == "match":
                    data = obj["data"]
                    matches.append(SearchMatch(
                        file=data["path"]["text"],
                        line=data["line_number"],
                        column=data["submatches"][0]["start"]["col"] if data.get("submatches") else 0,
                        content=data["lines"]["text"].rstrip(),
                        context_before=None,
                        context_after=None,
                    ))
            except (json.JSONDecodeError, KeyError):
                continue
        
        return self._format_results(matches, json_output)
    
    async def _search_python(self, pattern: str, paths: list[str], **kwargs) -> ToolResult:
        """Search using Python regex."""
        import fnmatch
        
        regex = kwargs.get("regex", True)
        case_sensitive = kwargs.get("case_sensitive", False)
        whole_word = kwargs.get("whole_word", False)
        glob = kwargs.get("glob")
        context_before = kwargs.get("context_before", 0)
        context_after = kwargs.get("context_after", 0)
        max_results = kwargs.get("max_results", 100)
        include_binary = kwargs.get("include_binary", False)
        
        # Compile pattern
        flags = 0 if case_sensitive else re.IGNORECASE
        if regex:
            if whole_word:
                pattern = rf"\b{re.escape(pattern)}\b"
            compiled = re.compile(pattern, flags)
        else:
            if whole_word:
                pattern = rf"\b{re.escape(pattern)}\b"
            compiled = re.compile(pattern, flags)
        
        matches = []
        
        for path_str in paths:
            path = Path(path_str)
            
            if not path.exists():
                continue
            
            if path.is_file():
                files_to_search = [path]
            else:
                files_to_search = []
                glob_pattern = glob or "*"
                for f in path.rglob(glob_pattern):
                    if f.is_file():
                        files_to_search.append(f)
            
            for file_path in files_to_search:
                try:
                    content = file_path.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue
                
                lines = content.splitlines()
                
                for i, line in enumerate(lines, 1):
                    if compiled.search(line):
                        # Get context
                        before = lines[max(0, i - context_before - 1):i - 1]
                        after = lines[i:i + context_after]
                        
                        matches.append(SearchMatch(
                            file=str(file_path),
                            line=i,
                            column=0,
                            content=line.rstrip(),
                            context_before=before,
                            context_after=after,
                        ))
                        
                        if len(matches) >= max_results:
                            return self._format_results(matches, kwargs.get("json_output", False))
        
        return self._format_results(matches, kwargs.get("json_output", False))
    
    def _format_results(self, matches: list[SearchMatch], json_output: bool) -> ToolResult:
        """Format search results."""
        if not matches:
            return ToolResult(
                tool_name=self.name,
                success=True,
                content=[{"type": "text", "text": "No matches found"}],
            )
        
        if json_output:
            return ToolResult(
                tool_name=self.name,
                success=True,
                content=[{"type": "text", "text": json.dumps([{
                    "file": m.file,
                    "line": m.line,
                    "column": m.column,
                    "content": m.content,
                } for m in matches], indent=2)}],
            )
        
        # Human-readable format
        output = [f"[{len(matches)} matches]"]
        
        # Group by file
        by_file: dict[str, list[SearchMatch]] = {}
        for m in matches:
            by_file.setdefault(m.file, []).append(m)
        
        for file_path, file_matches in by_file.items():
            output.append(f"\n{file_path}:")
            for m in file_matches:
                if m.context_before:
                    for ctx in m.context_before:
                        output.append(f"    | {ctx}")
                output.append(f"    {m.line}: {m.content}")
                if m.context_after:
                    for ctx in m.context_after:
                        output.append(f"    | {ctx}")
        
        return ToolResult(
            tool_name=self.name,
            success=True,
            content=[{"type": "text", "text": "\n".join(output)}],
        )


class GrepTool(SearchTool):
    """Alias for search tool."""
    
    name = "grep"
    description = "Alias for search - grep pattern in files"
    
    async def execute(self, pattern: str, paths: list[str], **kwargs) -> ToolResult:
        # Delegate to search tool
        return await SearchTool().execute(pattern, paths, **kwargs)


# Register search tools
def register_search_tools(registry):
    """Register search tools to a registry."""
    registry.register(SearchTool())
    registry.register(GrepTool())
