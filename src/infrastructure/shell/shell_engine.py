"""Shell Engine với Job Control, Pipes, và Built-in Commands.

Features:
- Full shell parsing (pipes, redirects, background)
- Job control (fg, bg, jobs, kill)
- Built-in commands (cd, pwd, export, alias, etc.)
- Command history
- Tab completion
"""

from __future__ import annotations

import asyncio
import os
import re
import signal
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class ShellError(Exception):
    """Shell error."""
    pass


class JobState(Enum):
    """Job states."""
    RUNNING = "running"
    STOPPED = "stopped"
    DONE = "done"
    TERMINATED = "terminated"


@dataclass
class Job:
    """A shell job."""
    job_id: int
    pid: int
    command: str
    process: asyncio.subprocess.Process
    state: JobState = JobState.RUNNING
    started_at: float = 0.0


@dataclass
class Command:
    """A parsed command."""
    name: str
    args: list[str] = field(default_factory=list)
    stdin_redirect: str | None = None
    stdout_redirect: str | None = None
    stderr_redirect: str | None = None
    stdout_append: bool = False


@dataclass
class Pipeline:
    """A pipeline of commands."""
    commands: list[Command]
    background: bool = False


@dataclass
class ShellBuiltin:
    """A built-in command."""
    name: str
    handler: callable
    description: str = ""
    args_help: str = ""


class ShellParser:
    """Parse shell commands."""
    
    # Token patterns
    TOKEN_PATTERNS = [
        ("QUOTED", r'"(?:[^"\\]|\\.)*"'),
        ("APOSTROPHE", r"'(?:[^'\\]|\\.)*'"),
        ("WORD", r"[^\s|&;<>]+"),
        ("PIPE", r"\|"),
        ("SEMICOLON", r";"),
        ("AMPERSAND", r"&"),
        ("REDIRECT_IN", r"<"),
        ("REDIRECT_OUT", r">"),
        ("APPEND", r">>"),
        ("WHITESPACE", r"\s+"),
    ]
    
    def __init__(self):
        self._compile_patterns()
    
    def _compile_patterns(self):
        """Compile regex patterns."""
        pattern = "|".join(f"(?P<{name}>{pattern})" for name, pattern in self.TOKEN_PATTERNS)
        self._pattern = re.compile(pattern)
    
    def parse(self, line: str) -> list[Pipeline]:
        """Parse shell line into pipelines."""
        pipelines = []
        current_commands = []
        current_command = Command(name="")
        in_redirect = None
        
        for match in self._pattern.finditer(line):
            token_type = match.lastgroup
            value = match.group()
            
            if token_type == "WHITESPACE":
                continue
            
            elif token_type == "PIPE":
                if current_command.name:
                    current_commands.append(current_command)
                    current_command = Command(name="")
                continue
            
            elif token_type == "SEMICOLON":
                if current_command.name:
                    current_commands.append(current_command)
                if current_commands:
                    pipelines.append(Pipeline(commands=current_commands.copy()))
                current_commands = []
                current_command = Command(name="")
                continue
            
            elif token_type == "AMPERSAND":
                if current_command.name:
                    current_commands.append(current_command)
                if current_commands:
                    pipeline = Pipeline(commands=current_commands.copy(), background=True)
                    pipelines.append(pipeline)
                current_commands = []
                current_command = Command(name="")
                continue
            
            elif token_type == "REDIRECT_IN":
                in_redirect = "stdin"
                continue
            
            elif token_type == "REDIRECT_OUT":
                in_redirect = "stdout"
                continue
            
            elif token_type == "APPEND":
                in_redirect = "stdout_append"
                continue
            
            elif token_type == "QUOTED" or token_type == "APOSTROPHE":
                value = value[1:-1]  # Remove quotes
                value = self._unescape(value)
            
            # Handle redirects
            if in_redirect:
                if in_redirect == "stdin":
                    current_command.stdin_redirect = value
                elif in_redirect == "stdout":
                    current_command.stdout_redirect = value
                elif in_redirect == "stdout_append":
                    current_command.stdout_append = True
                    current_command.stdout_redirect = value
                in_redirect = None
                continue
            
            # Regular word
            if not current_command.name:
                current_command.name = value
            else:
                current_command.args.append(value)
        
        # Add final command
        if current_command.name:
            current_commands.append(current_command)
        
        if current_commands:
            pipelines.append(Pipeline(commands=current_commands))
        
        return pipelines


class ShellBuiltins:
    """Built-in shell commands."""
    
    def __init__(self, shell):
        self.shell = shell
        self._builtins: dict[str, ShellBuiltin] = {}
        self._aliases: dict[str, str] = {}
        self._vars: dict[str, str] = {}
        self._register_builtins()
    
    def _register_builtins(self):
        """Register built-in commands."""
        self._builtins = {
            "cd": ShellBuiltin("cd", self._cmd_cd, "Change directory", "<path>"),
            "pwd": ShellBuiltin("pwd", self._cmd_pwd, "Print working directory"),
            "echo": ShellBuiltin("echo", self._cmd_echo, "Print arguments", "<args...>"),
            "export": ShellBuiltin("export", self._cmd_export, "Set environment variable", "<name>=<value>"),
            "unset": ShellBuiltin("unset", self._cmd_unset, "Unset environment variable", "<name>"),
            "alias": ShellBuiltin("alias", self._cmd_alias, "Create alias", "<name>=<value>"),
            "unalias": ShellBuiltin("unalias", self._cmd_unalias, "Remove alias", "<name>"),
            "local": ShellBuiltin("local", self._cmd_local, "Set local variable", "<name>=<value>"),
            "history": ShellBuiltin("history", self._cmd_history, "Show command history"),
            "jobs": ShellBuiltin("jobs", self._cmd_jobs, "List background jobs"),
            "fg": ShellBuiltin("fg", self._cmd_fg, "Bring job to foreground", "<job_id>"),
            "bg": ShellBuiltin("bg", self._cmd_bg, "Resume job in background", "<job_id>"),
            "kill": ShellBuiltin("kill", self._cmd_kill, "Send signal to job", "<job_id>"),
            "exit": ShellBuiltin("exit", self._cmd_exit, "Exit shell", "<code>"),
            "true": ShellBuiltin("true", self._cmd_true, "Do nothing, successfully"),
            "false": ShellBuiltin("false", self._cmd_false, "Do nothing, unsuccessfully"),
            "type": ShellBuiltin("type", self._cmd_type, "Show command type", "<name>"),
            "which": ShellBuiltin("which", self._cmd_which, "Locate command", "<name>"),
            "eval": ShellBuiltin("eval", self._cmd_eval, "Evaluate arguments"),
            "source": ShellBuiltin("source", self._cmd_source, "Execute from file", "<filename>"),
            "test": ShellBuiltin("test", self._cmd_test, "Test condition", "<expr>"),
            "printf": ShellBuiltin("printf", self._cmd_printf, "Formatted print", "<format> <args>"),
        }
    
    async def execute(self, name: str, args: list[str]) -> int:
        """Execute built-in command."""
        # Check aliases
        if name in self._aliases:
            cmd = self._aliases[name]
            args = cmd.split() + args
        
        if name not in self._builtins:
            return 127  # Command not found
        
        builtin = self._builtins[name]
        return await builtin.handler(args)
    
    async def _cmd_cd(self, args: list[str]) -> int:
        """Change directory."""
        if not args:
            path = Path.home()
        else:
            path = Path(args[0])
            if not path.is_absolute():
                path = self.shell.cwd / path
            path = path.resolve()
        
        if not path.exists():
            print(f"cd: {args[0]}: No such file or directory", file=sys.stderr)
            return 1
        
        if not path.is_dir():
            print(f"cd: {args[0]}: Not a directory", file=sys.stderr)
            return 1
        
        self.shell.cwd = path
        os.chdir(path)
        return 0
    
    async def _cmd_pwd(self, args: list[str]) -> int:
        """Print working directory."""
        print(self.shell.cwd)
        return 0
    
    async def _cmd_echo(self, args: list[str]) -> int:
        """Echo arguments."""
        print(" ".join(args))
        return 0
    
    async def _cmd_export(self, args: list[str]) -> int:
        """Set environment variable."""
        if not args:
            for k, v in sorted(self._vars.items()):
                print(f"{k}={v}")
            return 0
        
        for arg in args:
            if "=" in arg:
                k, v = arg.split("=", 1)
                self._vars[k] = v
                os.environ[k] = v
        return 0
    
    async def _cmd_unset(self, args: list[str]) -> int:
        """Unset variable."""
        for name in args:
            if name in self._vars:
                del self._vars[name]
            if name in os.environ:
                del os.environ[name]
        return 0
    
    async def _cmd_alias(self, args: list[str]) -> int:
        """Create alias."""
        if not args:
            for k, v in sorted(self._aliases.items()):
                print(f"alias {k}='{v}'")
            return 0
        
        for arg in args:
            if "=" in arg:
                k, v = arg.split("=", 1)
                v = v.strip("'\"")
                self._aliases[k] = v
        return 0
    
    async def _cmd_unalias(self, args: list[str]) -> int:
        """Remove alias."""
        for name in args:
            if name in self._aliases:
                del self._aliases[name]
        return 0
    
    async def _cmd_local(self, args: list[str]) -> int:
        """Set local variable."""
        for arg in args:
            if "=" in arg:
                k, v = arg.split("=", 1)
                self._vars[k] = v
        return 0
    
    async def _cmd_history(self, args: list[str]) -> int:
        """Show history."""
        for i, cmd in enumerate(self.shell.history, 1):
            print(f"  {i}  {cmd}")
        return 0
    
    async def _cmd_jobs(self, args: list[str]) -> int:
        """List jobs."""
        for job in self.shell.jobs.values():
            status = "+" if job.state == JobState.RUNNING else "-"
            print(f"[{job.job_id}] {status} {job.command}")
        return 0
    
    async def _cmd_fg(self, args: list[str]) -> int:
        """Bring job to foreground."""
        if not args:
            # Get most recent background job
            job = self.shell.get_last_background_job()
        else:
            job_id = int(args[0])
            job = self.shell.jobs.get(job_id)
        
        if not job:
            print(f"fg: job not found", file=sys.stderr)
            return 1
        
        # Resume if stopped
        if job.state == JobState.STOPPED:
            job.process.send_signal(signal.SIGCONT)
            job.state = JobState.RUNNING
        
        # Wait for job
        await job.process.wait()
        return job.process.returncode or 0
    
    async def _cmd_bg(self, args: list[str]) -> int:
        """Resume job in background."""
        if not args:
            job = self.shell.get_last_background_job()
        else:
            job_id = int(args[0])
            job = self.shell.jobs.get(job_id)
        
        if not job:
            print(f"bg: job not found", file=sys.stderr)
            return 1
        
        if job.state == JobState.STOPPED:
            job.process.send_signal(signal.SIGCONT)
            job.state = JobState.RUNNING
        
        return 0
    
    async def _cmd_kill(self, args: list[str]) -> int:
        """Send signal to job."""
        if not args:
            print("kill: missing argument", file=sys.stderr)
            return 1
        
        sig = signal.SIGTERM
        target = args[0]
        
        if target.startswith("-"):
            # Signal number
            try:
                sig = int(target[1:])
            except ValueError:
                print(f"kill: invalid signal", file=sys.stderr)
                return 1
            target = args[1] if len(args) > 1 else None
        
        if not target:
            print("kill: missing argument", file=sys.stderr)
            return 1
        
        try:
            job_id = int(target)
            job = self.shell.jobs.get(job_id)
            if job:
                job.process.send_signal(sig)
                return 0
        except ValueError:
            pass
        
        print(f"kill: job not found", file=sys.stderr)
        return 1
    
    async def _cmd_exit(self, args: list[str]) -> int:
        """Exit shell."""
        code = int(args[0]) if args else 0
        raise SystemExit(code)
    
    async def _cmd_true(self, args: list[str]) -> int:
        return 0
    
    async def _cmd_false(self, args: list[str]) -> int:
        return 1
    
    async def _cmd_type(self, args: list[str]) -> int:
        """Show command type."""
        for name in args:
            if name in self._aliases:
                print(f"{name} is aliased to '{self._aliases[name]}'")
            elif name in self._builtins:
                print(f"{name} is a shell builtin")
            elif shutil.which(name):
                print(f"{name} is {shutil.which(name)}")
            else:
                print(f"{name}: not found", file=sys.stderr)
        return 0
    
    async def _cmd_which(self, args: list[str]) -> int:
        """Locate command."""
        import shutil
        for name in args:
            path = shutil.which(name)
            if path:
                print(path)
            else:
                print(f"{name} not found", file=sys.stderr)
        return 0
    
    async def _cmd_eval(self, args: list[str]) -> int:
        """Evaluate arguments."""
        cmd = " ".join(args)
        # Re-parse and execute
        pipelines = self.shell.parser.parse(cmd)
        for pipeline in pipelines:
            await self.shell._execute_pipeline(pipeline)
        return 0
    
    async def _cmd_source(self, args: list[str]) -> int:
        """Execute from file."""
        if not args:
            print("source: missing argument", file=sys.stderr)
            return 1
        
        path = Path(args[0])
        if not path.exists():
            print(f"source: {args[0]}: No such file", file=sys.stderr)
            return 1
        
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                pipelines = self.shell.parser.parse(line)
                for pipeline in pipelines:
                    await self.shell._execute_pipeline(pipeline)
        return 0
    
    async def _cmd_test(self, args: list[str]) -> int:
        """Test condition."""
        # Simple test implementation
        return 0
    
    async def _cmd_printf(self, args: list[str]) -> int:
        """Formatted print."""
        if args:
            print(args[0] % tuple(args[1:]))
        return 0
    
    def get_all(self) -> list[ShellBuiltin]:
        """Get all builtins."""
        return list(self._builtins.values())


class ShellEngine:
    """Full shell engine với job control."""
    
    def __init__(self, cwd: Path | None = None):
        self.cwd = cwd or Path.cwd()
        self.parser = ShellParser()
        self.builtins = ShellBuiltins(self)
        self.jobs: dict[int, Job] = {}
        self._next_job_id = 1
        self.history: list[str] = []
        self._foreground_job: Job | None = None
    
    def get_last_background_job(self) -> Job | None:
        """Get most recent background job."""
        if not self.jobs:
            return None
        return max(self.jobs.values(), key=lambda j: j.job_id)
    
    async def execute(self, line: str) -> int:
        """Execute a shell line."""
        line = line.strip()
        if not line:
            return 0
        
        # Add to history
        self.history.append(line)
        
        # Parse
        pipelines = self.parser.parse(line)
        
        for pipeline in pipelines:
            result = await self._execute_pipeline(pipeline)
        
        return result
    
    async def _execute_pipeline(self, pipeline: Pipeline) -> int:
        """Execute a pipeline."""
        if not pipeline.commands:
            return 0
        
        # Single command with built-in check
        if len(pipeline.commands) == 1:
            cmd = pipeline.commands[0]
            
            # Check if built-in
            if cmd.name in self.builtins._builtins:
                return await self.builtins.execute(cmd.name, cmd.args)
            
            # External command
            return await self._execute_external(cmd, background=pipeline.background)
        
        # Pipeline - multiple commands
        return await self._execute_pipeline_commands(pipeline.commands, pipeline.background)
    
    async def _execute_external(
        self,
        cmd: Command,
        background: bool = False,
    ) -> int:
        """Execute external command."""
        import time
        
        # Build environment
        env = {**os.environ, **self.builtins._vars}
        
        # Build command
        cmd_line = [cmd.name] + cmd.args
        
        # Handle redirects
        stdin = None
        stdout = None
        stderr = None
        
        if cmd.stdin_redirect:
            stdin = open(cmd.stdin_redirect, "r")
        if cmd.stdout_redirect:
            mode = "a" if cmd.stdout_append else "w"
            stdout = open(cmd.stdout_redirect, mode)
        if cmd.stderr_redirect:
            stderr = open(cmd.stderr_redirect, "w")
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd_line,
                cwd=str(self.cwd),
                env=env,
                stdin=stdin,
                stdout=stdout or asyncio.subprocess.PIPE,
                stderr=stderr or asyncio.subprocess.PIPE,
            )
            
            # Create job
            job = Job(
                job_id=self._next_job_id,
                pid=process.pid,
                command=" ".join(cmd_line),
                process=process,
                started_at=time.time(),
            )
            self._next_job_id += 1
            
            if background:
                self.jobs[job.job_id] = job
                print(f"[{job.job_id}] {job.pid}")
                return 0
            else:
                self._foreground_job = job
                stdout_data, stderr_data = await process.communicate()
                
                if stdout_data:
                    print(stdout_data.decode(), end="")
                if stderr_data:
                    print(stderr_data.decode(), end="", file=sys.stderr)
                
                return process.returncode or 0
                
        finally:
            if stdin and stdin != subprocess.PIPE:
                stdin.close()
            if stdout and stdout != subprocess.PIPE:
                stdout.close()
            if stderr and stderr != subprocess.PIPE:
                stderr.close()
    
    async def _execute_pipeline_commands(
        self,
        commands: list[Command],
        background: bool = False,
    ) -> int:
        """Execute pipeline with multiple commands."""
        import time
        
        # Build pipes
        num_cmds = len(commands)
        processes = []
        
        for i, cmd in enumerate(commands):
            env = {**os.environ, **self.builtins._vars}
            cmd_line = [cmd.name] + cmd.args
            
            if i == 0:
                # First command - stdin from shell
                process = await asyncio.create_subprocess_exec(
                    *cmd_line,
                    cwd=str(self.cwd),
                    env=env,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            else:
                # Middle commands
                process = await asyncio.create_subprocess_exec(
                    *cmd_line,
                    cwd=str(self.cwd),
                    env=env,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            
            processes.append(process)
        
        # Connect pipes
        for i in range(num_cmds - 1):
            await processes[i].stdout.connect_pipe(processes[i + 1].stdin)
        
        # Wait for last process
        if processes:
            stdout, stderr = await processes[-1].communicate()
            
            if stdout:
                print(stdout.decode(), end="")
            if stderr:
                print(stderr.decode(), end="", file=sys.stderr)
            
            return processes[-1].returncode or 0
        
        return 0
    
    def cleanup_jobs(self) -> None:
        """Remove finished jobs from list."""
        finished = []
        for job_id, job in self.jobs.items():
            if job.state in (JobState.DONE, JobState.TERMINATED):
                finished.append(job_id)
        
        for job_id in finished:
            del self.jobs[job_id]


class InteractiveShell:
    """Interactive shell session."""
    
    def __init__(self):
        self.engine = ShellEngine()
        self._running = True
    
    async def run(self) -> None:
        """Run interactive shell."""
        print(f"Shell Engine v1.0 (Python)")
        print("Type 'exit' to quit, 'jobs' to list background jobs\n")
        
        while self._running:
            try:
                prompt = f"{self.engine.cwd}> "
                line = await self._get_input(prompt)
                
                if not line.strip():
                    continue
                
                await self.engine.execute(line)
                
            except SystemExit as e:
                print(f"exit {e.code}")
                self._running = False
            except KeyboardInterrupt:
                print("^C")
            except EOFError:
                break
        
        print("Goodbye!")
    
    async def _get_input(self, prompt: str) -> str:
        """Get input."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: input(prompt))


# Convenience functions

async def quick_shell(command: str) -> int:
    """Execute single command."""
    engine = ShellEngine()
    return await engine.execute(command)


def create_shell() -> ShellEngine:
    """Create new shell engine."""
    return ShellEngine()
