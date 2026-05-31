"""Real terminal integration with actual shell execution.

Provides real shell execution capabilities for the AI_SUPPORT TUI.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class TerminalSession:
    """A real shell session."""
    id: str
    cwd: Path
    process: Optional[asyncio.subprocess.Process] = None
    history: list[str] = field(default_factory=list)
    is_alive: bool = False


class TerminalHandler:
    """Real terminal with actual shell execution.

    Provides subprocess-based shell execution with proper async support.

    Usage:
        handler = TerminalHandler()
        session = handler.create_session("main")
        result = await handler.execute("main", "echo hello")
        print(result["stdout"])
    """

    def __init__(self):
        self._sessions: dict[str, TerminalSession] = {}
        self._default_shell = os.environ.get("SHELL", "powershell" if os.name == "nt" else "/bin/bash")

    def create_session(self, session_id: str, cwd: Optional[Path] = None) -> TerminalSession:
        """Create a real shell session.

        Args:
            session_id: Unique identifier for the session
            cwd: Working directory (defaults to current directory)

        Returns:
            TerminalSession object
        """
        cwd = cwd or Path.cwd()
        session = TerminalSession(id=session_id, cwd=cwd)
        self._sessions[session_id] = session
        return session

    async def execute(
        self,
        session_id: str,
        command: str,
        timeout: float = 30.0,
        shell: bool = True,
    ) -> dict:
        """Execute command in real shell.

        Args:
            session_id: Session ID to use
            command: Command to execute
            timeout: Timeout in seconds (default 30)
            shell: Whether to run through shell (default True)

        Returns:
            Dict with stdout, stderr, return_code, command, cwd
        """
        session = self._sessions.get(session_id)
        if not session:
            session = self.create_session(session_id)

        session.history.append(command)
        logger.debug("Executing command: %s", command)

        try:
            if shell:
                proc = await asyncio.create_subprocess_shell(
                    command,
                    cwd=str(session.cwd),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=self._get_clean_env(),
                )
            else:
                args = shlex.split(command)
                proc = await asyncio.create_subprocess_exec(
                    *args,
                    cwd=str(session.cwd),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=self._get_clean_env(),
                )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=timeout,
                )

                return {
                    "stdout": stdout.decode("utf-8", errors="replace"),
                    "stderr": stderr.decode("utf-8", errors="replace"),
                    "return_code": proc.returncode,
                    "command": command,
                    "cwd": str(session.cwd),
                    "timeout": False,
                    "error": False,
                }

            except asyncio.TimeoutError:
                proc.kill()
                try:
                    await proc.wait()
                except ProcessLookupError:
                    pass
                return {
                    "stdout": "",
                    "stderr": f"Command timed out after {timeout}s",
                    "return_code": -1,
                    "command": command,
                    "cwd": str(session.cwd),
                    "timeout": True,
                    "error": False,
                }

        except FileNotFoundError:
            return {
                "stdout": "",
                "stderr": f"Command not found: {command.split()[0]}",
                "return_code": 127,
                "command": command,
                "cwd": str(session.cwd),
                "timeout": False,
                "error": True,
            }
        except PermissionError:
            return {
                "stdout": "",
                "stderr": f"Permission denied: {command}",
                "return_code": 126,
                "command": command,
                "cwd": str(session.cwd),
                "timeout": False,
                "error": True,
            }
        except Exception as e:
            logger.error("Terminal execution failed: %s", e)
            return {
                "stdout": "",
                "stderr": str(e),
                "return_code": -1,
                "command": command,
                "cwd": str(session.cwd),
                "timeout": False,
                "error": True,
            }

    async def execute_interactive(
        self,
        session_id: str,
        command: str,
    ) -> asyncio.subprocess.Process:
        """Start an interactive shell process.

        Args:
            session_id: Session ID
            command: Command to run (e.g., shell name)

        Returns:
            The subprocess.Process object
        """
        session = self._sessions.get(session_id)
        if not session:
            session = self.create_session(session_id)

        proc = await asyncio.create_subprocess_shell(
            command,
            cwd=str(session.cwd),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=self._get_clean_env(),
        )
        session.process = proc
        session.is_alive = proc.returncode is None
        return proc

    async def write_to_process(
        self,
        session_id: str,
        data: str,
    ) -> None:
        """Write to a running process's stdin.

        Args:
            session_id: Session ID
            data: Data to write
        """
        session = self._sessions.get(session_id)
        if session and session.process and session.process.stdin:
            session.process.stdin.write(data.encode())
            await session.process.stdin.drain()

    def get_session(self, session_id: str) -> Optional[TerminalSession]:
        """Get session by ID.

        Args:
            session_id: Session identifier

        Returns:
            TerminalSession or None
        """
        return self._sessions.get(session_id)

    def list_sessions(self) -> list[TerminalSession]:
        """List all sessions.

        Returns:
            List of TerminalSession objects
        """
        return list(self._sessions.values())

    def close_session(self, session_id: str) -> bool:
        """Close a session and terminate its process.

        Args:
            session_id: Session to close

        Returns:
            True if session was found and closed
        """
        session = self._sessions.get(session_id)
        if session:
            if session.process:
                try:
                    session.process.terminate()
                except ProcessLookupError:
                    pass
            session.is_alive = False
            del self._sessions[session_id]
            return True
        return False

    def change_directory(self, session_id: str, path: Path) -> bool:
        """Change the working directory of a session.

        Args:
            session_id: Session to modify
            path: New directory

        Returns:
            True if directory exists and was set
        """
        if path.exists() and path.is_dir():
            session = self._sessions.get(session_id)
            if session:
                session.cwd = path
                return True
        return False

    def _get_clean_env(self) -> dict:
        """Get a clean environment for subprocess."""
        env = os.environ.copy()
        env["TERM"] = env.get("TERM", "xterm-256color")
        return env

    async def run_script(
        self,
        session_id: str,
        script_path: Path,
        args: Optional[list[str]] = None,
        timeout: float = 60.0,
    ) -> dict:
        """Run a script file.

        Args:
            session_id: Session to use
            script_path: Path to script
            args: Optional script arguments
            timeout: Execution timeout

        Returns:
            Result dict from execute
        """
        args_str = " ".join(args) if args else ""
        command = f"{script_path} {args_str}".strip()
        return await self.execute(session_id, command, timeout=timeout, shell=True)


# Singleton instance for convenience
_default_handler: Optional[TerminalHandler] = None


def get_handler() -> TerminalHandler:
    """Get the default terminal handler instance.

    Returns:
        TerminalHandler singleton
    """
    global _default_handler
    if _default_handler is None:
        _default_handler = TerminalHandler()
    return _default_handler
