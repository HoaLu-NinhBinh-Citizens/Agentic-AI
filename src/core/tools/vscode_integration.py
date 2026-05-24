"""VS Code Integration - Full Codex-like editor control.

Provides:
- File editing
- Terminal commands
- Git operations
- Debugging
- LSP (Language Server Protocol) support
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import structlog

logger = structlog.get_logger(__name__)


class TerminalState(Enum):
    """Terminal state."""
    IDLE = "idle"
    RUNNING = "running"
    OUTPUT = "output"
    ERROR = "error"


@dataclass
class Terminal:
    """A terminal session."""
    id: str
    cwd: str
    state: TerminalState = TerminalState.IDLE
    command: Optional[str] = None
    exit_code: Optional[int] = None
    output: str = ""
    error: str = ""
    start_time: float = 0
    end_time: float = 0


@dataclass
class FileChange:
    """A file modification."""
    path: str
    old_content: str
    new_content: str
    timestamp: datetime = field(default_factory=datetime.now)


class VSCodeIntegration:
    """
    VS Code editor integration for full Codex experience.
    
    Features:
    - Read/write files
    - Execute terminal commands
    - Git operations
    - Debugging
    - LSP integration
    
    Usage:
        vscode = VSCodeIntegration()
        
        # Edit files
        await vscode.edit_file("main.c", "new content")
        
        # Run terminal
        result = await vscode.run_terminal("make build")
        
        # Git operations
        await vscode.git("commit", "-m", "Update")
    """
    
    def __init__(self, workspace_root: str):
        self.workspace_root = Path(workspace_root)
        self._terminals: dict[str, Terminal] = {}
        self._file_changes: list[FileChange] = []
        self._term_counter = 0
    
    # ============================================
    # File Operations
    # ============================================
    
    async def read_file(self, path: str) -> str:
        """Read a file."""
        file_path = self.workspace_root / path
        return file_path.read_text(encoding="utf-8")
    
    async def write_file(self, path: str, content: str) -> bool:
        """Write a file."""
        file_path = self.workspace_root / path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        logger.info(f"File written: {path}")
        return True
    
    async def edit_file(
        self,
        path: str,
        new_content: str,
        create_backup: bool = True,
    ) -> FileChange:
        """Edit a file with change tracking."""
        file_path = self.workspace_root / path
        
        old_content = ""
        if file_path.exists():
            old_content = file_path.read_text(encoding="utf-8")
        
        change = FileChange(
            path=path,
            old_content=old_content,
            new_content=new_content,
        )
        self._file_changes.append(change)
        
        if create_backup and old_content:
            backup_path = f"{path}.backup"
            (self.workspace_root / backup_path).write_text(old_content)
        
        await self.write_file(path, new_content)
        return change
    
    async def delete_file(self, path: str) -> bool:
        """Delete a file."""
        file_path = self.workspace_root / path
        if file_path.exists():
            file_path.unlink()
            logger.info(f"File deleted: {path}")
            return True
        return False
    
    async def create_directory(self, path: str) -> bool:
        """Create a directory."""
        dir_path = self.workspace_root / path
        dir_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Directory created: {path}")
        return True
    
    async def list_files(self, path: str = ".", pattern: str = "*") -> list[str]:
        """List files in directory."""
        dir_path = self.workspace_root / path
        files = []
        for f in dir_path.glob(pattern):
            rel_path = f.relative_to(self.workspace_root)
            files.append(str(rel_path))
        return files
    
    # ============================================
    # Terminal Operations
    # ============================================
    
    async def create_terminal(self, cwd: Optional[str] = None) -> Terminal:
        """Create a new terminal session."""
        self._term_counter += 1
        term_id = f"term_{self._term_counter}"
        
        terminal = Terminal(
            id=term_id,
            cwd=cwd or str(self.workspace_root),
            start_time=datetime.now().timestamp(),
        )
        self._terminals[term_id] = terminal
        return terminal
    
    async def run_command(
        self,
        command: str,
        cwd: Optional[str] = None,
        timeout: float = 30.0,
        env: Optional[dict[str, str]] = None,
    ) -> tuple[int, str, str]:
        """
        Run a shell command synchronously.
        
        Returns: (exit_code, stdout, stderr)
        """
        cwd = cwd or str(self.workspace_root)
        
        # Use cmd.exe on Windows
        shell = "cmd.exe"
        cmd_args = ["/c", command]
        
        logger.info(f"Running command: {command} (cwd: {cwd})")
        
        try:
            proc = await asyncio.create_subprocess_exec(
                shell,
                *cmd_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=env,
            )
            
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout,
            )
            
            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")
            exit_code = proc.returncode
            
            logger.info(f"Command completed: exit_code={exit_code}")
            return exit_code, stdout, stderr
            
        except asyncio.TimeoutError:
            logger.error(f"Command timeout: {command}")
            proc.kill()
            return -1, "", "Command timed out"
        except Exception as e:
            logger.error(f"Command failed: {e}")
            return -1, "", str(e)
    
    async def run_terminal(
        self,
        command: str,
        cwd: Optional[str] = None,
    ) -> Terminal:
        """
        Run command in a tracked terminal session.
        
        Returns Terminal with output.
        """
        terminal = await self.create_terminal(cwd)
        terminal.state = TerminalState.RUNNING
        terminal.command = command
        
        exit_code, stdout, stderr = await self.run_command(command, cwd)
        
        terminal.exit_code = exit_code
        terminal.output = stdout
        terminal.error = stderr
        terminal.end_time = datetime.now().timestamp()
        terminal.state = TerminalState.ERROR if exit_code != 0 else TerminalState.IDLE
        
        return terminal
    
    async def stream_output(
        self,
        command: str,
        cwd: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """Stream command output line by line."""
        cwd = cwd or str(self.workspace_root)
        
        proc = await asyncio.create_subprocess_exec(
            "cmd.exe", "/c", command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=cwd,
        )
        
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            yield line.decode("utf-8", errors="replace").rstrip()
        
        await proc.wait()
    
    # ============================================
    # Git Operations
    # ============================================
    
    async def git_status(self) -> str:
        """Get git status."""
        exit_code, stdout, stderr = await self.run_command("git status")
        return stdout if exit_code == 0 else stderr
    
    async def git_diff(self, file: Optional[str] = None) -> str:
        """Get git diff."""
        cmd = f"git diff {file}" if file else "git diff"
        exit_code, stdout, stderr = await self.run_command(cmd)
        return stdout if exit_code == 0 else stderr
    
    async def git_log(self, n: int = 10) -> str:
        """Get git log."""
        exit_code, stdout, stderr = await self.run_command(f"git log -n {n} --oneline")
        return stdout if exit_code == 0 else stderr
    
    async def git_add(self, path: str = ".") -> bool:
        """Git add files."""
        exit_code, _, _ = await self.run_command(f"git add {path}")
        return exit_code == 0
    
    async def git_commit(self, message: str) -> bool:
        """Git commit."""
        # Escape message for shell
        msg = message.replace('"', '\\"')
        exit_code, stdout, stderr = await self.run_command(f'git commit -m "{msg}"')
        return exit_code == 0
    
    async def git_branch(self) -> str:
        """Get current branch."""
        exit_code, stdout, stderr = await self.run_command("git branch --show-current")
        return stdout.strip() if exit_code == 0 else ""
    
    async def git_push(self, remote: str = "origin", branch: Optional[str] = None) -> bool:
        """Git push."""
        branch = branch or await self.git_branch()
        exit_code, _, stderr = await self.run_command(f"git push {remote} {branch}")
        return exit_code == 0
    
    async def git_pull(self, remote: str = "origin", branch: Optional[str] = None) -> bool:
        """Git pull."""
        branch = branch or await self.git_branch()
        exit_code, _, stderr = await self.run_command(f"git pull {remote} {branch}")
        return exit_code == 0
    
    async def git_checkout(self, branch: str) -> bool:
        """Git checkout."""
        exit_code, _, stderr = await self.run_command(f"git checkout {branch}")
        return exit_code == 0
    
    async def git_stash(self) -> bool:
        """Git stash."""
        exit_code, _, _ = await self.run_command("git stash")
        return exit_code == 0
    
    async def git_stash_pop(self) -> bool:
        """Git stash pop."""
        exit_code, _, _ = await self.run_command("git stash pop")
        return exit_code == 0
    
    # ============================================
    # Build Operations
    # ============================================
    
    async def run_build(self, target: Optional[str] = None) -> dict[str, Any]:
        """Run build command."""
        command = f"cmake --build build {target}" if target else "cmake --build build"
        
        terminal = await self.run_terminal(command)
        
        return {
            "success": terminal.exit_code == 0,
            "output": terminal.output,
            "error": terminal.error,
            "exit_code": terminal.exit_code,
        }
    
    async def run_test(self, test_name: Optional[str] = None) -> dict[str, Any]:
        """Run tests."""
        command = f"ctest -R {test_name}" if test_name else "ctest"
        
        terminal = await self.run_terminal(command)
        
        return {
            "success": terminal.exit_code == 0,
            "output": terminal.output,
            "error": terminal.error,
            "exit_code": terminal.exit_code,
        }
    
    # ============================================
    # Search Operations
    # ============================================
    
    async def search_files(
        self,
        pattern: str,
        path: str = ".",
        file_pattern: str = "*",
    ) -> list[dict[str, Any]]:
        """Search for pattern in files."""
        results = []
        
        dir_path = self.workspace_root / path
        
        for file_path in dir_path.glob(f"**/{file_pattern}"):
            if not file_path.is_file():
                continue
            
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                
                for i, line in enumerate(content.split("\n"), 1):
                    if pattern.lower() in line.lower():
                        results.append({
                            "file": str(file_path.relative_to(self.workspace_root)),
                            "line": i,
                            "content": line.strip(),
                        })
            except Exception:
                pass
        
        return results
    
    async def find_files(
        self,
        pattern: str = "*",
        path: str = ".",
    ) -> list[str]:
        """Find files matching pattern."""
        dir_path = self.workspace_root / path
        files = []
        
        for file_path in dir_path.glob(f"**/{pattern}"):
            if file_path.is_file():
                files.append(str(file_path.relative_to(self.workspace_root)))
        
        return files
    
    # ============================================
    # History & Undo
    # ============================================
    
    def get_file_changes(self) -> list[FileChange]:
        """Get all file changes in this session."""
        return self._file_changes.copy()
    
    async def undo_last_change(self) -> bool:
        """Undo the last file change."""
        if not self._file_changes:
            return False
        
        change = self._file_changes.pop()
        await self.write_file(change.path, change.old_content)
        logger.info(f"Undid change to: {change.path}")
        return True
    
    def get_terminals(self) -> list[Terminal]:
        """Get all terminal sessions."""
        return list(self._terminals.values())


# Global instance
_vscode: Optional[VSCodeIntegration] = None


def get_vscode_integration(workspace: Optional[str] = None) -> VSCodeIntegration:
    """Get global VSCode integration."""
    global _vscode
    if _vscode is None:
        _vscode = VSCodeIntegration(workspace or os.getcwd())
    return _vscode


if __name__ == "__main__":
    import asyncio
    
    async def demo():
        vscode = VSCodeIntegration(".")
        
        print("VSCode Integration Demo")
        print("=" * 40)
        
        # List files
        files = await vscode.list_files(".", "*.py")
        print(f"Python files: {len(files)}")
        
        # Git status
        status = await vscode.git_status()
        print(f"\nGit status:\n{status[:500]}")
        
        # Run command
        exit_code, stdout, stderr = await vscode.run_command("echo Hello from VSCode!")
        print(f"\nCommand output: {stdout}")
        
        # Search
        results = await vscode.search_files("class", file_pattern="*.py")
        print(f"\nFound {len(results)} matches for 'class'")
    
    asyncio.run(demo())
