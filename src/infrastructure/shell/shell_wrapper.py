"""Shell wrapper for oh-my-pi/pi-mono integration.

Provides:
- oh-my-pi binary management
- pi-mono shell integration
- Native shell command execution
- Job control and piping
- Shell completion
"""

from __future__ import annotations

import asyncio
import os
import platform
import shutil
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, AsyncIterator


class ShellError(Exception):
    """Shell operation error."""
    pass


class ShellType(Enum):
    """Available shell types."""
    OMP = "oh-my-pi"  # oh-my-pi
    PI = "pi"  # pi-mono
    BASH = "bash"
    ZSH = "zsh"
    PWSH = "pwsh"  # PowerShell
    CMD = "cmd"


@dataclass
class ShellCommand:
    """A shell command with metadata."""
    command: str
    shell: ShellType = ShellType.OMP
    cwd: Path | None = None
    env: dict[str, str] = field(default_factory=dict)
    timeout: float = 30.0


@dataclass
class ShellResult:
    """Result of shell command execution."""
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: float


@dataclass
class Job:
    """A background job."""
    job_id: int
    pid: int
    command: str
    status: str  # running, stopped, done
    started_at: float = 0.0


class OMPBinaryManager:
    """Manages oh-my-pi binary installation and updates."""
    
    def __init__(self, install_dir: Path | None = None):
        self.install_dir = install_dir or self._get_default_install_dir()
        self._ensure_install_dir()
    
    def _get_default_install_dir(self) -> Path:
        """Get default installation directory."""
        if platform.system() == "Windows":
            return Path.home() / "AppData" / "Local" / "Programs" / "oh-my-pi"
        elif platform.system() == "Darwin":
            return Path.home() / "Library" / "Application Support" / "oh-my-pi"
        else:
            return Path.home() / ".local" / "bin"
    
    def _ensure_install_dir(self) -> None:
        """Ensure installation directory exists."""
        self.install_dir.mkdir(parents=True, exist_ok=True)
    
    def find_existing(self) -> Path | None:
        """Find existing oh-my-pi installation."""
        candidates = [
            # Path checking
            self.install_dir / "omp",
            Path.home() / ".local" / "bin" / "omp",
            Path("/usr/local/bin/omp"),
            Path("/usr/bin/omp"),
            Path.home() / "bin" / "omp",
            # Windows
            Path.home() / "AppData" / "Local" / "Programs" / "omp.exe",
            Path("C:/Program Files/omp.exe"),
        ]
        
        for candidate in candidates:
            if candidate.exists():
                return candidate
        
        # Check PATH
        if shutil.which("omp"):
            return Path(shutil.which("omp"))
        
        return None
    
    async def install(self, version: str = "latest") -> Path:
        """Install oh-my-pi binary."""
        system = platform.system().lower()
        arch = platform.machine().lower()
        
        # Determine URL
        base_url = "https://github.com/can1357/oh-my-pi/releases"
        
        if system == "windows":
            filename = f"omp-{arch}.exe"
        elif system == "darwin":
            filename = f"omp-{arch}"
        else:
            filename = f"omp-{arch}"
        
        binary_path = self.install_dir / filename
        
        # Download
        import httpx
        
        url = f"{base_url}/download/{version}/{filename}"
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            
            binary_path.write_bytes(response.content)
            binary_path.chmod(0o755)
        
        return binary_path
    
    async def update(self) -> bool:
        """Update oh-my-pi to latest version."""
        existing = self.find_existing()
        if not existing:
            await self.install()
            return True
        
        # Run self-update
        try:
            proc = await asyncio.create_subprocess_exec(
                str(existing), "self-update",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            return proc.returncode == 0
        except:
            return False


class ShellWrapper:
    """Wrapper for shell execution with oh-my-pi integration."""
    
    def __init__(
        self,
        shell_type: ShellType = ShellType.OMP,
        binary_path: Path | None = None,
    ):
        self.shell_type = shell_type
        self.binary_path = binary_path or self._find_shell()
        self._jobs: dict[int, Job] = {}
        self._next_job_id = 1
        self._current_cwd = Path.cwd()
    
    def _find_shell(self) -> Path | None:
        """Find shell binary."""
        if self.shell_type == ShellType.OMP:
            manager = OMPBinaryManager()
            return manager.find_existing()
        
        # Find system shell
        shell_map = {
            ShellType.BASH: ["bash"],
            ShellType.ZSH: ["zsh"],
            ShellType.PWSH: ["pwsh", "powershell"],
            ShellType.CMD: ["cmd"],
        }
        
        cmds = shell_map.get(self.shell_type, [])
        for cmd in cmds:
            if shutil.which(cmd):
                return Path(shutil.which(cmd))
        
        return None
    
    @property
    def is_available(self) -> bool:
        """Check if shell is available."""
        return self.binary_path is not None
    
    async def execute(
        self,
        command: str,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
        timeout: float = 30.0,
    ) -> ShellResult:
        """Execute a shell command."""
        import time
        start = time.time()
        
        cwd = cwd or self._current_cwd
        
        # Build environment
        full_env = {**os.environ, **(env or {})}
        
        # Determine shell
        if self.shell_type == ShellType.OMP and self.binary_path:
            cmd = [str(self.binary_path), "-c", command]
        else:
            shell_cmd = self._get_shell_command()
            cmd = shell_cmd + ["-c", command]
        
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(cwd),
                env=full_env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout
            )
            
            duration_ms = (time.time() - start) * 1000
            
            return ShellResult(
                stdout=stdout.decode() if stdout else "",
                stderr=stderr.decode() if stderr else "",
                exit_code=proc.returncode or 0,
                duration_ms=duration_ms,
            )
            
        except asyncio.TimeoutError:
            if proc:
                proc.kill()
                await proc.wait()
            
            return ShellResult(
                stdout="",
                stderr="Command timed out",
                exit_code=-1,
                duration_ms=timeout * 1000,
            )
    
    async def execute_streaming(
        self,
        command: str,
        callback,
        cwd: Path | None = None,
    ) -> int:
        """Execute command with streaming output."""
        cwd = cwd or self._current_cwd
        
        if self.shell_type == ShellType.OMP and self.binary_path:
            cmd = [str(self.binary_path), "-c", command]
        else:
            shell_cmd = self._get_shell_command()
            cmd = shell_cmd + ["-c", command]
        
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        
        async def stream_output(stream, is_stderr=False):
            while True:
                chunk = await stream.read(1024)
                if not chunk:
                    break
                await callback(chunk.decode(), is_stderr=is_stderr)
        
        await asyncio.gather(
            stream_output(proc.stdout),
            stream_output(proc.stderr, True),
        )
        
        await proc.wait()
        return proc.returncode or 0
    
    def _get_shell_command(self) -> list[str]:
        """Get shell command based on type."""
        if self.shell_type == ShellType.BASH:
            return ["bash"]
        elif self.shell_type == ShellType.ZSH:
            return ["zsh"]
        elif self.shell_type == ShellType.PWSH:
            return ["pwsh"]
        elif self.shell_type == ShellType.CMD:
            return ["cmd", "/c"]
        return ["sh", "-c"]
    
    # Job control
    
    async def run_background(self, command: str) -> Job:
        """Run command in background."""
        import time
        
        job_id = self._next_job_id
        self._next_job_id += 1
        
        if self.shell_type == ShellType.OMP and self.binary_path:
            cmd = [str(self.binary_path), "-c", command]
        else:
            shell_cmd = self._get_shell_command()
            cmd = shell_cmd + ["-c", f"{command} &"]
        
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(self._current_cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        
        job = Job(
            job_id=job_id,
            pid=proc.pid,
            command=command,
            status="running",
            started_at=time.time(),
        )
        
        self._jobs[job_id] = job
        
        return job
    
    async def bring_to_foreground(self, job_id: int) -> ShellResult:
        """Bring background job to foreground."""
        job = self._jobs.get(job_id)
        if not job:
            raise ShellError(f"Job {job_id} not found")
        
        # Wait for job
        try:
            proc = await asyncio.create_subprocess_exec(
                "wait", str(job.pid),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            
            job.status = "done"
            
            return ShellResult(
                stdout=stdout.decode() if stdout else "",
                stderr=stderr.decode() if stderr else "",
                exit_code=proc.returncode or 0,
                duration_ms=0,
            )
        except:
            return ShellResult("", "", -1, 0)
    
    async def list_jobs(self) -> list[Job]:
        """List background jobs."""
        return list(self._jobs.values())
    
    async def kill_job(self, job_id: int) -> bool:
        """Kill a background job."""
        job = self._jobs.get(job_id)
        if not job:
            return False
        
        try:
            # On Unix
            if platform.system() != "Windows":
                proc = await asyncio.create_subprocess_exec(
                    "kill", "-9", str(job.pid),
                )
                await proc.communicate()
            else:
                # On Windows
                proc = await asyncio.create_subprocess_exec(
                    "taskkill", "/F", "/PID", str(job.pid),
                )
                await proc.communicate()
            
            job.status = "done"
            return True
        except:
            return False
    
    # Directory operations
    
    async def cd(self, path: str | Path) -> None:
        """Change working directory."""
        path = Path(path)
        if not path.exists():
            raise ShellError(f"Directory not found: {path}")
        if not path.is_dir():
            raise ShellError(f"Not a directory: {path}")
        
        self._current_cwd = path
        os.chdir(path)
    
    def pwd(self) -> Path:
        """Get current working directory."""
        return self._current_cwd


class PipeHandler:
    """Handle shell piping between commands."""
    
    @staticmethod
    async def pipe(
        left_result: ShellResult,
        right_command: str,
        shell: ShellWrapper,
    ) -> ShellResult:
        """Pipe left_result.stdout into right_command."""
        return await shell.execute(
            f"echo {left_result.stdout.strip()!r} | {right_command}"
        )
    
    @staticmethod
    def split_pipeline(command: str) -> list[str]:
        """Split a pipeline into individual commands."""
        # Simple split by |
        commands = []
        current = []
        in_quote = False
        quote_char = None
        
        for char in command:
            if char in "'\"" and not in_quote:
                in_quote = True
                quote_char = char
            elif char == quote_char and in_quote:
                in_quote = False
                quote_char = None
            elif char == "|" and not in_quote:
                commands.append("".join(current).strip())
                current = []
                continue
            
            current.append(char)
        
        if current:
            commands.append("".join(current).strip())
        
        return commands


class ShellCompletion:
    """Shell completion handler."""
    
    def __init__(self, shell: ShellWrapper):
        self.shell = shell
    
    async def complete_command(self, partial: str) -> list[str]:
        """Get command completions."""
        # Common commands
        common_commands = [
            "ls", "cd", "pwd", "mkdir", "rm", "cp", "mv", "cat", "grep",
            "find", "echo", "printf", "head", "tail", "sort", "uniq",
            "wc", "awk", "sed", "cut", "tr", "tee", "xargs",
            "git", "npm", "pip", "python", "node", "cargo",
        ]
        
        # Filter by partial
        if partial:
            return [c for c in common_commands if c.startswith(partial)]
        
        return common_commands
    
    async def complete_path(self, partial: str) -> list[str]:
        """Get path completions."""
        import glob as glob_module
        
        # Handle ~ expansion
        if partial.startswith("~"):
            partial = str(Path.home()) + partial[1:]
        
        # Get directory part
        if "/" in partial or "\\" in partial:
            # Complete file in directory
            dir_path = str(Path(partial).parent)
            if not dir_path:
                dir_path = "."
            prefix = Path(partial).name
            
            pattern = f"{dir_path}/{prefix}*"
            matches = glob_module.glob(pattern)
            
            return [str(Path(m).name) for m in matches]
        else:
            # Complete in current directory
            pattern = f"{partial}*"
            matches = glob_module.glob(pattern)
            
            return [str(Path(m).name) for m in matches]


class InteractiveShell:
    """Interactive shell session."""
    
    def __init__(self, shell: ShellWrapper):
        self.shell = shell
        self.completion = ShellCompletion(shell)
        self._history: list[str] = []
        self._history_index = -1
    
    async def run(self) -> None:
        """Run interactive shell."""
        print(f"Interactive shell ({self.shell.shell_type.value})")
        print("Type 'exit' to quit\n")
        
        while True:
            try:
                cwd = self.shell.pwd()
                prompt = f"{cwd}> "
                
                # Get input
                user_input = await self._get_input(prompt)
                
                if not user_input.strip():
                    continue
                
                # Add to history
                self._history.append(user_input)
                self._history_index = len(self._history)
                
                # Handle commands
                if user_input.strip() in ("exit", "quit", "q"):
                    break
                
                if user_input.strip() == "cd":
                    await self.shell.cd(Path.home())
                    continue
                
                if user_input.startswith("cd "):
                    path = user_input[3:].strip()
                    try:
                        await self.shell.cd(path)
                    except ShellError as e:
                        print(f"Error: {e}")
                    continue
                
                if user_input.startswith("jobs"):
                    jobs = await self.shell.list_jobs()
                    for job in jobs:
                        print(f"[{job.job_id}] {job.status}: {job.command}")
                    continue
                
                # Execute
                result = await self.shell.execute(user_input)
                
                if result.stdout:
                    print(result.stdout, end="")
                if result.stderr:
                    print(result.stderr, end="", file=sys.stderr)
                
            except KeyboardInterrupt:
                print("\nUse 'exit' to quit")
                continue
            except EOFError:
                break
    
    async def _get_input(self, prompt: str) -> str:
        """Get input with history navigation."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: input(prompt)
        )
    
    def get_history(self) -> list[str]:
        """Get command history."""
        return self._history.copy()
    
    def save_history(self, path: Path) -> None:
        """Save history to file."""
        path.write_text("\n".join(self._history))
    
    def load_history(self, path: Path) -> None:
        """Load history from file."""
        if path.exists():
            self._history = path.read_text().strip().split("\n")
            self._history_index = len(self._history)


# Convenience functions

async def quick_shell(command: str) -> ShellResult:
    """Quick shell execution."""
    shell = ShellWrapper()
    return await shell.execute(command)


async def install_omp() -> Path:
    """Install oh-my-pi binary."""
    manager = OMPBinaryManager()
    return await manager.install()


def is_omp_available() -> bool:
    """Check if oh-my-pi is available."""
    manager = OMPBinaryManager()
    return manager.find_existing() is not None
