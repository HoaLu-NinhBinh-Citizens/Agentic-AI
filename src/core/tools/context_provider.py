"""Real-time context provider — collect IDE state for the agent."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

# Import Cursor IDE MCP tools if available
try:
    from src.core.tools.cursor_mcp_client import list_open_files, get_diagnostics, get_terminal_output
    CURSOR_MCP_AVAILABLE = True
except ImportError:
    CURSOR_MCP_AVAILABLE = False


@dataclass
class AgentContext:
    """All context gathered for the agent."""
    open_files: List[str] = field(default_factory=list)
    open_file_contents: Dict[str, str] = field(default_factory=dict)
    cursor_position: Dict[str, Any] = field(default_factory=dict)
    diagnostics: List[Dict] = field(default_factory=list)
    git_status: str = ""
    git_diff: str = ""
    recent_files: List[str] = field(default_factory=list)
    terminal_output: str = ""
    project_type: str = ""


class ContextProvider:
    """Gather real-time context from the development environment."""

    def __init__(self, project_root: str = "."):
        self.project_root = Path(project_root).resolve()
        self._cache: Dict[str, Any] = {}
        self._cache_ttl: float = 2.0  # seconds

    async def gather(self, include_terminal: bool = False) -> AgentContext:
        """Gather all available context."""
        ctx = AgentContext()

        # Try Cursor MCP for IDE state
        if CURSOR_MCP_AVAILABLE:
            ctx = await self._gather_cursor_mcp(ctx, include_terminal)
        else:
            ctx = await self._gather_fallback(ctx)

        # Always gather git and project info
        ctx.git_status = self._git_status()
        ctx.git_diff = self._git_diff()
        ctx.project_type = self._detect_project_type()

        return ctx

    async def _gather_cursor_mcp(self, ctx: AgentContext, include_terminal: bool) -> AgentContext:
        """Gather context via Cursor MCP tools."""
        try:
            # Get open files
            files = list_open_files()
            ctx.open_files = files

            # Get file contents
            for fpath in files[:10]:  # Limit to 10 open files
                try:
                    content = Path(fpath).read_text(encoding="utf-8", errors="ignore")
                    ctx.open_file_contents[fpath] = content
                except Exception:
                    pass

            # Get diagnostics
            ctx.diagnostics = get_diagnostics()

            # Get terminal output if requested
            if include_terminal:
                ctx.terminal_output = get_terminal_output()
        except Exception:
            pass  # MCP not available or errored
        return ctx

    async def _gather_fallback(self, ctx: AgentContext) -> AgentContext:
        """Fallback: gather what we can without MCP."""
        # Find recently modified files
        ctx.recent_files = await self._recent_files_async()

        # Check for build output errors
        build_output_dir = self.project_root / "main" / "software" / "output"
        if build_output_dir.exists():
            for log_file in ["build_error.log", "build.log"]:
                log_path = build_output_dir / log_file
                if log_path.exists():
                    try:
                        content = log_path.read_text(encoding="utf-8", errors="ignore")
                        if "error" in content.lower():
                            ctx.terminal_output += f"\n--- {log_file} ---\n{content[-2000:]}"
                    except Exception:
                        pass
        return ctx

    def _git_status(self) -> str:
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain", "-uall"],
                cwd=str(self.project_root),
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.stdout.strip()
        except Exception:
            return ""

    def _git_diff(self) -> str:
        try:
            result = subprocess.run(
                ["git", "diff", "--stat"],
                cwd=str(self.project_root),
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.stdout.strip()
        except Exception:
            return ""

    async def _recent_files_async(self) -> List[str]:
        """Find recently modified source files (runs in thread to avoid blocking)."""
        def _sync():
            extensions = [".c", ".h", ".cpp", ".py", ".yaml", ".json", ".md"]
            files: List[tuple] = []
            cutoff = 86400  # 24 hours
            import time
            now = time.time()
            skip_dirs = {".venv", "venv", ".venv", "__pycache__", "build", "output", "node_modules", ".git"}

            for ext in extensions:
                for path in self.project_root.rglob(f"*{ext}"):
                    if any(part.startswith(".") or part in skip_dirs for part in path.parts):
                        continue
                    try:
                        mtime = path.stat().st_mtime
                        if now - mtime < cutoff:
                            files.append((mtime, str(path.relative_to(self.project_root))))
                    except Exception:
                        continue

            files.sort(reverse=True)
            return [f[1] for f in files[:20]]

        return await asyncio.to_thread(_sync)

    def _detect_project_type(self) -> str:
        """Detect what kind of project this is."""
        markers = {
            "STM32 Firmware": ["main/software/Core", "main/software/STM32F4", "main/software/Drivers"],
            "Python Project": ["AI_support/__init__.py", "setup.py", "pyproject.toml"],
            "Frontend": ["AI_support/frontend/package.json"],
            "Hardware Design": ["main/hardware/kicad"],
        }
        for name, patterns in markers.items():
            if any((self.project_root / p).exists() for p in patterns):
                return name
        return "Mixed Project"

    def format_for_prompt(self, ctx: AgentContext) -> str:
        """Format context into a string for LLM system prompt."""
        lines = []
        lines.append("\n\n## DEVELOPMENT CONTEXT\n")

        # Project type
        lines.append(f"Project type: {ctx.project_type}")
        lines.append(f"Project root: {self.project_root}")

        # Git status
        if ctx.git_status:
            lines.append(f"\nGit status ({len(ctx.git_status.splitlines())} changed files):")
            for line in ctx.git_status.splitlines()[:20]:
                lines.append(f"  {line}")
            if ctx.git_diff:
                lines.append(f"\nGit diff summary:\n{ctx.git_diff}")

        # Open files (from Cursor MCP)
        if ctx.open_files:
            lines.append(f"\nOpen files ({len(ctx.open_files)}):")
            for fpath in ctx.open_files[:15]:
                lines.append(f"  - {fpath}")
                if fpath in ctx.open_file_contents:
                    content = ctx.open_file_contents[fpath]
                    lines.append(f"    ```")
                    preview = "\n".join(content.splitlines()[:50])
                    lines.append(preview)
                    if len(content.splitlines()) > 50:
                        lines.append(f"    ... ({len(content.splitlines()) - 50} more lines)")
                    lines.append(f"    ```")

        # Recent files
        elif ctx.recent_files:
            lines.append(f"\nRecently modified files (last 24h):")
            for fpath in ctx.recent_files[:15]:
                lines.append(f"  - {fpath}")

        # Diagnostics
        if ctx.diagnostics:
            lines.append(f"\nLinter/compiler diagnostics ({len(ctx.diagnostics)} issues):")
            for diag in ctx.diagnostics[:20]:
                loc = diag.get("location", {})
                fname = loc.get("file", "unknown")
                lnum = loc.get("line", 0)
                sev = diag.get("severity", "warning")
                msg = diag.get("message", "")
                lines.append(f"  [{sev.upper()}] {fname}:{lnum}: {msg}")

        # Terminal output
        if ctx.terminal_output:
            lines.append(f"\nRecent terminal output:")
            for line in ctx.terminal_output.splitlines()[-50:]:
                lines.append(f"  {line}")

        lines.append("\n## END CONTEXT\n")
        return "\n".join(lines)
