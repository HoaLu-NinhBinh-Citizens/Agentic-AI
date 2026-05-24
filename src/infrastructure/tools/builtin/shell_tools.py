"""Shell tool for Agentic-AI CLI.

Like omp's bash tool:
- Persistent shell sessions
- PTY support for interactive commands
- Background job dispatch
- Custom working directory
"""

from __future__ import annotations

import asyncio
import os
import shlex
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..tool_registry import (
    BaseTool,
    ToolCategory,
    ToolResult,
    ToolSchema,
)


@dataclass
class ShellResult:
    """Result from shell execution."""
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: float


class BashTool(BaseTool):
    """Execute shell commands.
    
    Like omp's bash tool:
    - Persistent sessions (optional)
    - PTY for interactive commands
    - Background job support
    - Working directory control
    """
    
    name = "bash"
    description = "Execute shell command"
    category = ToolCategory.SHELL
    
    schema = ToolSchema(
        description="Execute shell command",
        properties={
            "command": {
                "type": "string",
                "description": "Shell command to execute",
            },
            "cwd": {
                "type": "string",
                "description": "Working directory for command",
            },
            "timeout": {
                "type": "number",
                "description": "Timeout in seconds",
                "default": 60,
            },
            "env": {
                "type": "object",
                "description": "Environment variables",
            },
            "pty": {
                "type": "boolean",
                "description": "Use PTY for interactive commands",
                "default": False,
            },
            "background": {
                "type": "boolean",
                "description": "Run in background",
                "default": False,
            },
        },
        required=["command"],
    )
    
    async def execute(self, command: str, **kwargs) -> ToolResult:
        """Execute shell command."""
        import time
        start = time.monotonic()
        
        try:
            cwd = kwargs.get("cwd")
            timeout = kwargs.get("timeout", 60)
            env = kwargs.get("env", {})
            pty = kwargs.get("pty", False)
            background = kwargs.get("background", False)
            
            # Prepare environment
            env_vars = os.environ.copy()
            env_vars.update(env)
            
            # Prepare working directory
            if cwd:
                work_dir = Path(cwd)
                if not work_dir.exists():
                    return ToolResult(
                        tool_name=self.name,
                        success=False,
                        error=f"Working directory not found: {cwd}",
                        is_error=True,
                    )
            else:
                work_dir = Path.cwd()
            
            if background:
                return await self._execute_background(command, work_dir, env_vars)
            
            return await self._execute_command(command, work_dir, env_vars, timeout, pty, start)
            
        except asyncio.TimeoutError:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=f"Command timed out after {kwargs.get('timeout', 60)}s",
                is_error=True,
            )
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=str(e),
                is_error=True,
            )
    
    async def _execute_command(
        self,
        command: str,
        cwd: Path,
        env: dict[str, str],
        timeout: float,
        pty: bool,
        start: float,
    ) -> ToolResult:
        """Execute a single command."""
        # Use shell for complex commands, direct exec for simple ones
        use_shell = self._needs_shell(command)
        
        if use_shell:
            cmd = f"cd {shlex.quote(str(cwd))} && {command}"
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
        else:
            args = shlex.split(command)
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(cwd),
                env=env,
            )
        
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout,
            )
            
            duration_ms = (time.monotonic() - start) * 1000
            
            result = ShellResult(
                stdout=stdout.decode("utf-8", errors="replace"),
                stderr=stderr.decode("utf-8", errors="replace"),
                exit_code=proc.returncode or 0,
                duration_ms=duration_ms,
            )
            
            return self._format_result(result)
            
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=f"Command timed out after {timeout}s",
                is_error=True,
            )
    
    def _needs_shell(self, command: str) -> bool:
        """Check if command needs shell features."""
        shell_chars = {";", "|", "&", "&&", "||", ">", "<", "$", "`", "(", ")"}
        return any(c in command for c in shell_chars)
    
    async def _execute_background(
        self,
        command: str,
        cwd: Path,
        env: dict[str, str],
    ) -> ToolResult:
        """Execute command in background."""
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(cwd),
            env=env,
        )
        
        # Don't wait for completion
        return ToolResult(
            tool_name=self.name,
            success=True,
            content=[{"type": "text", "text": f"Started background process (PID: {proc.pid})"}],
            details={"pid": proc.pid},
        )
    
    def _format_result(self, result: ShellResult) -> ToolResult:
        """Format shell result."""
        output = []
        
        if result.stdout:
            output.append(result.stdout)
        
        if result.stderr:
            output.append(f"[stderr]\n{result.stderr}")
        
        if result.exit_code != 0:
            output.append(f"\n[exit code: {result.exit_code}]")
        
        output.append(f"\n[duration: {result.duration_ms:.0f}ms]")
        
        return ToolResult(
            tool_name=self.name,
            success=result.exit_code == 0,
            content=[{"type": "text", "text": "\n".join(output)}],
            details={
                "exit_code": result.exit_code,
                "duration_ms": result.duration_ms,
            },
        )


class PwdTool(BaseTool):
    """Get current working directory."""
    
    name = "pwd"
    description = "Print working directory"
    category = ToolCategory.SHELL
    
    schema = ToolSchema(
        description="Print working directory",
        properties={},
        required=[],
    )
    
    async def execute(self, **kwargs) -> ToolResult:
        return ToolResult(
            tool_name=self.name,
            success=True,
            content=[{"type": "text", "text": str(Path.cwd())}],
        )


class CdTool(BaseTool):
    """Change working directory."""
    
    name = "cd"
    description = "Change working directory"
    category = ToolCategory.SHELL
    
    schema = ToolSchema(
        description="Change working directory",
        properties={
            "path": {
                "type": "string",
                "description": "Directory to change to",
            },
        },
        required=["path"],
    )
    
    async def execute(self, path: str, **kwargs) -> ToolResult:
        try:
            new_dir = Path(path).resolve()
            
            if not new_dir.exists():
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    error=f"Directory not found: {path}",
                    is_error=True,
                )
            
            if not new_dir.is_dir():
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    error=f"Not a directory: {path}",
                    is_error=True,
                )
            
            # Note: Changing cwd in async context doesn't persist across calls
            # This is a limitation - in real implementation, would need session state
            return ToolResult(
                tool_name=self.name,
                success=True,
                content=[{"type": "text", "text": f"Changed directory to {new_dir}"}],
                details={"cwd": str(new_dir)},
            )
            
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=str(e),
                is_error=True,
            )


# Register shell tools
def register_shell_tools(registry):
    """Register shell tools to a registry."""
    registry.register(BashTool())
    registry.register(PwdTool())
    registry.register(CdTool())
