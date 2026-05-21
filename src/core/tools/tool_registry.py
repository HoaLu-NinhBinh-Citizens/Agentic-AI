"""Tool definitions and schemas for the Cursor-like agent.

Each tool has:
- name: unique identifier
- description: what the tool does
- parameters: JSON schema for arguments
- execute: async function
"""

from __future__ import annotations

import asyncio
import json
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from src.core.tools.build_tools import BuildTools
from src.core.tools.file_tools import FileTools


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: Dict[str, Any]
    execute: Any = field(default=None, repr=False)


@dataclass
class ToolResult:
    """Result from a tool execution."""
    tool: str
    success: bool
    output: str
    error: Optional[str] = None
    duration_ms: float = 0.0


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def _make_tools(
    file_tools: FileTools,
    build_tools: BuildTools,
    project_root: Path,
) -> Dict[str, ToolDefinition]:
    """Build the full tool registry."""

    tools: Dict[str, ToolDefinition] = {}

    # ---- File tools ----

    def do_read_file(args: Dict) -> ToolResult:
        import time
        t0 = time.monotonic()
        path = args.get("path", "")
        limit = args.get("limit", 0)
        try:
            content = file_tools.read_file(path)
            if limit > 0:
                lines = content.splitlines()
                content = "\n".join(lines[:limit])
                if len(lines) > limit:
                    content += f"\n... (+{len(lines) - limit} more lines)"
            return ToolResult(tool="read_file", success=True, output=content, duration_ms=(time.monotonic() - t0) * 1000)
        except Exception as exc:
            return ToolResult(tool="read_file", success=False, output="", error=str(exc), duration_ms=(time.monotonic() - t0) * 1000)

    tools["read_file"] = ToolDefinition(
        name="read_file",
        description="Read the full content of a file. Use this before editing, searching, or understanding code.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative or absolute path to the file."},
                "limit": {"type": "integer", "description": "Optional: limit output to first N lines.", "default": 0},
            },
            "required": ["path"],
        },
        execute=do_read_file,
    )

    def do_write_file(args: Dict) -> ToolResult:
        import time
        t0 = time.monotonic()
        path = args.get("path", "")
        content = args.get("content", "")
        if not path or not content:
            return ToolResult(tool="write_file", success=False, output="", error="path and content are required")
        try:
            file_tools.write_file(path, content)
            return ToolResult(
                tool="write_file", success=True,
                output=f"Wrote {len(content)} chars to {path}",
                duration_ms=(time.monotonic() - t0) * 1000,
            )
        except Exception as exc:
            return ToolResult(tool="write_file", success=False, output="", error=str(exc), duration_ms=(time.monotonic() - t0) * 1000)

    tools["write_file"] = ToolDefinition(
        name="write_file",
        description="Write or overwrite a file with new content. Use this to create or replace source files, configs, or scripts.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path (relative to project root)."},
                "content": {"type": "string", "description": "Full file content to write."},
            },
            "required": ["path", "content"],
        },
        execute=do_write_file,
    )

    def do_edit_file(args: Dict) -> ToolResult:
        import time
        t0 = time.monotonic()
        path = args.get("path", "")
        old_text = args.get("old_text", "")
        new_text = args.get("new_text", "")
        if not path or not old_text:
            return ToolResult(tool="edit_file", success=False, output="", error="path and old_text are required")
        try:
            if file_tools.edit_file(path, old_text, new_text):
                return ToolResult(
                    tool="edit_file", success=True,
                    output=f"Edited {path}: replaced {len(old_text)} chars with {len(new_text)} chars",
                    duration_ms=(time.monotonic() - t0) * 1000,
                )
            return ToolResult(tool="edit_file", success=False, output="", error=f"Could not find old_text in {path}", duration_ms=(time.monotonic() - t0) * 1000)
        except Exception as exc:
            return ToolResult(tool="edit_file", success=False, output="", error=str(exc), duration_ms=(time.monotonic() - t0) * 1000)

    tools["edit_file"] = ToolDefinition(
        name="edit_file",
        description="Replace a specific text block within a file. Use this for surgical edits — specify the exact old_text to replace.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path."},
                "old_text": {"type": "string", "description": "Exact text block to replace. Must match the file content."},
                "new_text": {"type": "string", "description": "Replacement text."},
            },
            "required": ["path", "old_text", "new_text"],
        },
        execute=do_edit_file,
    )

    def do_search_code(args: Dict) -> ToolResult:
        import time
        t0 = time.monotonic()
        pattern = args.get("pattern", "")
        file_pattern = args.get("file_pattern", "*.c")
        if not pattern:
            return ToolResult(tool="search_code", success=False, output="", error="pattern required")
        results = file_tools.search_code(pattern, file_pattern)
        lines = []
        for fpath, matches in results.items():
            lines.append(f"--- {fpath} ---")
            for lineno, line_text in matches[:10]:
                lines.append(f"  {lineno}: {line_text}")
            if len(matches) > 10:
                lines.append(f"  ... ({len(matches) - 10} more matches)")
        output = "\n".join(lines) if lines else f"No matches for '{pattern}' in {file_pattern}"
        return ToolResult(tool="search_code", success=True, output=output, duration_ms=(time.monotonic() - t0) * 1000)

    tools["search_code"] = ToolDefinition(
        name="search_code",
        description="Search for a text pattern across source files. Returns file:line:matches.",
        parameters={
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Text pattern to search for (case-insensitive)."},
                "file_pattern": {"type": "string", "description": "Glob pattern for files to search, e.g. '*.c', '*.h', '*.py'.", "default": "*.c"},
            },
            "required": ["pattern"],
        },
        execute=do_search_code,
    )

    def do_list_files(args: Dict) -> ToolResult:
        import time
        t0 = time.monotonic()
        pattern = args.get("pattern", "*")
        subdir = args.get("subdir", "")
        if subdir:
            full_pattern = f"{subdir}/{pattern}"
        else:
            full_pattern = f"**/{pattern}"
        root = project_root / subdir if subdir else project_root
        try:
            files = [str(p.relative_to(project_root)) for p in root.glob(full_pattern) if p.is_file()]
            files = sorted(files)[:100]
            output = f"{len(files)} file(s) matching '{pattern}':\n" + "\n".join(files)
            return ToolResult(tool="list_files", success=True, output=output, duration_ms=(time.monotonic() - t0) * 1000)
        except Exception as exc:
            return ToolResult(tool="list_files", success=False, output="", error=str(exc), duration_ms=(time.monotonic() - t0) * 1000)

    tools["list_files"] = ToolDefinition(
        name="list_files",
        description="List files matching a glob pattern under the project.",
        parameters={
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Glob pattern, e.g. '*.c', '*.h', 'main/**/*'.", "default": "*"},
                "subdir": {"type": "string", "description": "Optional subdirectory to search within."},
            },
        },
        execute=do_list_files,
    )

    def do_get_context(args: Dict) -> ToolResult:
        import time
        t0 = time.monotonic()
        ctx = file_tools.get_project_context()
        output = json.dumps(ctx, indent=2)
        return ToolResult(tool="get_context", success=True, output=output, duration_ms=(time.monotonic() - t0) * 1000)

    tools["get_context"] = ToolDefinition(
        name="get_context",
        description="Get overall project structure: source files, headers, and project root.",
        parameters={"type": "object", "properties": {}},
        execute=do_get_context,
    )

    # ---- Build tools ----

    async def do_build(args: Dict) -> ToolResult:
        import time
        t0 = time.monotonic()
        try:
            result = await build_tools.run_build()
            lines = [f"Build status: {result.status}"]
            if result.errors:
                lines.append(f"Errors ({len(result.errors)}):")
                for err in result.errors[:10]:
                    lines.append(f"  {err.file}:{err.line}: {err.message}")
            if result.stdout:
                lines.append("\n--- stdout ---")
                lines.append(result.stdout[-1000:])
            output = "\n".join(lines)
            return ToolResult(
                tool="build", success=(result.status == "success"),
                output=output,
                duration_ms=(time.monotonic() - t0) * 1000,
            )
        except Exception as exc:
            return ToolResult(tool="build", success=False, output="", error=str(exc), duration_ms=(time.monotonic() - t0) * 1000)

    tools["build"] = ToolDefinition(
        name="build",
        description="Run the project build (auto-detects cmake/make/python/ps1). Returns build status and errors.",
        parameters={
            "type": "object",
            "properties": {},
        },
        execute=lambda a: asyncio.create_task(do_build(a)),
    )

    async def do_run_command(args: Dict) -> ToolResult:
        import time
        t0 = time.monotonic()
        command = args.get("command", "")
        cwd = args.get("cwd", str(project_root))
        timeout = args.get("timeout", 60)
        if not command:
            return ToolResult(tool="run_command", success=False, output="", error="command required")
        try:
            # FIX: Use shell=False with shlex.split() to prevent command injection
            # This is safe because commands are constructed from validated tool parameters
            cmd_list = shlex.split(command) if command else []
            
            result = await asyncio.to_thread(subprocess.run,
                cmd_list,
                shell=False,  # FIX: Disable shell to prevent injection
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=min(timeout, 300),
            )
            output = f"[exit {result.returncode}]\n{result.stdout}\n{result.stderr}".strip()
            return ToolResult(
                tool="run_command",
                success=(result.returncode == 0),
                output=output,
                duration_ms=(time.monotonic() - t0) * 1000,
            )
        except subprocess.TimeoutExpired:
            return ToolResult(tool="run_command", success=False, output="", error=f"Command timed out after {timeout}s", duration_ms=(time.monotonic() - t0) * 1000)
        except Exception as exc:
            return ToolResult(tool="run_command", success=False, output="", error=str(exc), duration_ms=(time.monotonic() - t0) * 1000)

    tools["run_command"] = ToolDefinition(
        name="run_command",
        description="Run a shell command. Use for git, pytest, scripts, etc.",
        parameters={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to run."},
                "cwd": {"type": "string", "description": "Working directory (defaults to project root)."},
                "timeout": {"type": "integer", "description": "Timeout in seconds.", "default": 60},
            },
            "required": ["command"],
        },
        execute=lambda a: asyncio.create_task(do_run_command(a)),
    )

    async def do_git_status(args: Dict) -> ToolResult:
        import time
        t0 = time.monotonic()
        try:
            result = await asyncio.to_thread(subprocess.run,
                ["git", "status", "--porcelain"],
                cwd=str(project_root),
                capture_output=True,
                text=True,
                timeout=10,
            )
            output = result.stdout.strip() or "(clean)"
            return ToolResult(tool="git_status", success=True, output=output, duration_ms=(time.monotonic() - t0) * 1000)
        except Exception as exc:
            return ToolResult(tool="git_status", success=False, output="", error=str(exc), duration_ms=(time.monotonic() - t0) * 1000)

    tools["git_status"] = ToolDefinition(
        name="git_status",
        description="Show git working tree status (modified, staged, untracked files).",
        parameters={"type": "object", "properties": {}},
        execute=do_git_status,
    )

    async def do_git_diff(args: Dict) -> ToolResult:
        import time
        t0 = time.monotonic()
        file_path = args.get("path", "")
        try:
            cmd = ["git", "diff", "--stat"]
            if file_path:
                cmd.append("--")
                cmd.append(file_path)
            result = await asyncio.to_thread(subprocess.run, cmd, cwd=str(project_root), capture_output=True, text=True, timeout=10)
            return ToolResult(tool="git_diff", success=True, output=result.stdout.strip(), duration_ms=(time.monotonic() - t0) * 1000)
        except Exception as exc:
            return ToolResult(tool="git_diff", success=False, output="", error=str(exc), duration_ms=(time.monotonic() - t0) * 1000)

    tools["git_diff"] = ToolDefinition(
        name="git_diff",
        description="Show git diff statistics for modified files.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Optional specific file path."},
            },
        },
        execute=do_git_diff,
    )

    async def do_grep(args: Dict) -> ToolResult:
        import time
        t0 = time.monotonic()
        pattern = args.get("pattern", "")
        path_arg = args.get("path", str(project_root))
        if not pattern:
            return ToolResult(tool="grep", success=False, output="", error="pattern required")
        try:
            cmd = ["git", "grep", "--no-color", "-n", pattern, "--", path_arg] if Path(path_arg).is_dir() else ["git", "grep", "--no-color", "-n", pattern, str(path_arg)]
            result = await asyncio.to_thread(subprocess.run, cmd, cwd=str(project_root), capture_output=True, text=True, timeout=15)
            output = result.stdout.strip() or f"No matches for '{pattern}'"
            return ToolResult(tool="grep", success=True, output=output, duration_ms=(time.monotonic() - t0) * 1000)
        except Exception as exc:
            return ToolResult(tool="grep", success=False, output="", error=str(exc), duration_ms=(time.monotonic() - t0) * 1000)

    tools["grep"] = ToolDefinition(
        name="grep",
        description="Fast grep using git grep for pattern matching across the codebase.",
        parameters={
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Regex or literal pattern to search."},
                "path": {"type": "string", "description": "Directory or file path to search in.", "default": "."},
            },
            "required": ["pattern"],
        },
        execute=do_grep,
    )

    return tools


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class ToolRegistry:
    """Central registry for all agent tools."""

    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}
        self._initialized = False

    def register(self, tools: Dict[str, ToolDefinition]):
        for name, tool in tools.items():
            self._tools[name] = tool
        self._initialized = True

    def get(self, name: str) -> Optional[ToolDefinition]:
        return self._tools.get(name)

    def list_names(self) -> List[str]:
        return sorted(self._tools.keys())

    def get_schemas(self) -> List[Dict]:
        """Return OpenAI-style tool schemas for LLM function calling."""
        schemas = []
        for name, tool in sorted(self._tools.items()):
            schemas.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            })
        return schemas

    def get_tools_md(self) -> str:
        """Return a markdown description of all tools for prompts without function calling."""
        lines = ["Available tools:"]
        for name, tool in sorted(self._tools.items()):
            lines.append(f"\n## {tool.name}")
            lines.append(f"{tool.description}")
            props = tool.parameters.get("properties", {})
            if props:
                lines.append("Parameters:")
                for pname, pinfo in props.items():
                    required = pname in tool.parameters.get("required", [])
                    req_str = "(required)" if required else "(optional)"
                    lines.append(f"  - {pname} {req_str}: {pinfo.get('description', '')}")
        return "\n".join(lines)
