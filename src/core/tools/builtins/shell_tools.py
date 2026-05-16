"""
Shell Tools

Built-in tools for shell operations with sandbox integration.
"""

import asyncio
import logging
import os
import resource
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.core.tools.schema import (
    Tool,
    ToolParameter,
    ToolPermission,
    ToolCategory,
    ParameterType,
)
from src.core.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


# Shell tool blocklist - dangerous commands that should never run
SHELL_COMMAND_BLOCKLIST = {
    "rm -rf /",
    "dd if=/dev/zero of=/dev/sda",
    ":(){ :|:& };:",  # Fork bomb
    "mkfs",
    "dd",
    "> /dev/sd*",
    "chmod -R 777 /",
    "wget .* | sh",
    "curl .* | sh",
    "eval ",
}


def _check_shell_permission(context: Any) -> None:
    """
    Check if shell execution is allowed in current context.

    Args:
        context: Tool execution context

    Raises:
        PermissionError: If shell execution is not allowed
    """
    from src.core.tools.context import ToolExecutionMode

    if context is None:
        return

    if hasattr(context, "mode"):
        mode = context.mode
        if mode == ToolExecutionMode.DRY_RUN:
            raise PermissionError("Shell execution not allowed in dry_run mode")

    # Check sandbox configuration for subprocess permissions
    if hasattr(context, "sandbox_config") and context.sandbox_config:
        if not context.sandbox_config.allow_subprocess:
            raise PermissionError("Subprocess execution is disabled in sandbox configuration")


def _check_dangerous_command(command: str) -> bool:
    """
    Check if command contains dangerous patterns.

    Args:
        command: Command to check

    Returns:
        True if command is safe
    """
    command_lower = command.lower()

    for dangerous in SHELL_COMMAND_BLOCKLIST:
        if dangerous.lower() in command_lower:
            logger.warning(f"Blocked dangerous command pattern: {dangerous}")
            return False

    # Check for common injection patterns
    dangerous_patterns = [
        "&& rm ",
        "; rm ",
        "| rm ",
        "&& chmod",
        "; chmod",
        "eval $(",
        "$(rm ",
        "`rm ",
    ]

    for pattern in dangerous_patterns:
        if pattern in command_lower:
            logger.warning(f"Blocked dangerous pattern: {pattern}")
            return False

    return True


def _build_sandboxed_env(context: Any) -> Dict[str, str]:
    """
    Build sandboxed environment for subprocess execution.

    Args:
        context: Tool execution context

    Returns:
        Sanitized environment variables
    """
    # Start with a minimal environment
    env = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": os.environ.get("HOME", "/tmp"),
        "LANG": "en_US.UTF-8",
        "LC_ALL": "en_US.UTF-8",
        "TMPDIR": tempfile.gettempdir(),
    }

    # Add allowed environment variables from context
    if context and hasattr(context, "environment"):
        for key, value in context.environment.items():
            if key.isupper() and "_" in key or key in ("PATH", "HOME", "TMPDIR"):
                env[key] = value

    return env


def _apply_resource_limits(context: Any, timeout: int) -> Dict[str, Any]:
    """
    Get resource limit configuration for subprocess.

    Args:
        context: Tool execution context
        timeout: Execution timeout

    Returns:
        Resource limit configuration
    """
    limits = {
        "timeout": timeout,
    }

    if context and hasattr(context, "resource_limits"):
        rl = context.resource_limits
        limits.update({
            "max_memory_mb": getattr(rl, "max_memory_mb", 256),
            "max_cpu_time": getattr(rl, "max_cpu_time_seconds", 30),
            "max_open_files": getattr(rl, "max_open_files", 100),
        })

    return limits


async def _run_subprocess_sandboxed(
    command: str,
    cwd: Optional[Path],
    timeout: int,
    env: Dict[str, str],
    resource_limits: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Run subprocess with sandbox restrictions.

    Args:
        command: Command to execute
        cwd: Working directory
        timeout: Timeout in seconds
        env: Environment variables
        resource_limits: Resource limit configuration

    Returns:
        Execution result dictionary
    """
    # Prepare subprocess arguments
    subproc_env = {**os.environ, **env}

    # Remove potentially dangerous environment variables
    dangerous_vars = ["LD_PRELOAD", "LD_LIBRARY_PATH", "DYLD_INSERT_LIBRARIES"]
    for var in dangerous_vars:
        subproc_env.pop(var, None)

    try:
        # Create subprocess
        process = await asyncio.create_subprocess_shell(
            command,
            cwd=str(cwd) if cwd else None,
            env=subproc_env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=resource_limits.get("max_open_files", 100) * 1024,  # Buffer limit
        )

        # Wait with timeout
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout,
            )

            return {
                "success": process.returncode == 0,
                "returncode": process.returncode,
                "stdout": stdout.decode("utf-8", errors="replace") if stdout else "",
                "stderr": stderr.decode("utf-8", errors="replace") if stderr else "",
            }

        except asyncio.TimeoutError:
            # Kill the process on timeout
            process.kill()
            try:
                await asyncio.wait_for(process.wait(), timeout=5)
            except asyncio.TimeoutError:
                pass  # Process may have already exited

            return {
                "success": False,
                "returncode": -1,
                "stdout": "",
                "stderr": f"Command timed out after {timeout} seconds",
            }

    except Exception as e:
        return {
            "success": False,
            "returncode": -1,
            "stdout": "",
            "stderr": str(e),
        }


def run_command_handler(params: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Run a shell command with sandbox validation."""
    command = params["command"]
    cwd = params.get("cwd")
    timeout = min(params.get("timeout", 30), 300)  # Cap at 5 minutes
    env_updates = params.get("env", {})

    # Check permissions
    _check_shell_permission(context)

    # Check for dangerous commands
    if not _check_dangerous_command(command):
        return {
            "success": False,
            "returncode": -1,
            "stdout": "",
            "stderr": "Command blocked due to security policy",
        }

    # Validate working directory
    working_dir = Path(cwd) if cwd else None
    if working_dir:
        _check_path_permission(context, working_dir, "execute")

    # Build sandboxed environment
    sandboxed_env = _build_sandboxed_env(context)
    sandboxed_env.update(env_updates)

    # Get resource limits
    resource_limits = _apply_resource_limits(context, timeout)

    # Run synchronously using run_in_executor
    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(
            _run_subprocess_sandboxed(
                command=command,
                cwd=working_dir,
                timeout=timeout,
                env=sandboxed_env,
                resource_limits=resource_limits,
            )
        )
        return result
    finally:
        loop.close()


def run_python_handler(params: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Run Python code with sandbox validation."""
    import sys

    code = params["code"]
    timeout = min(params.get("timeout", 30), 60)  # Cap at 1 minute

    # Check permissions
    _check_shell_permission(context)

    # Build sandboxed environment
    sandboxed_env = _build_sandboxed_env(context)
    sandboxed_env["PYTHONDONTWRITEBYTECODE"] = "1"  # Prevent .pyc files
    sandboxed_env["PYTHONUNBUFFERED"] = "1"

    try:
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, **sandboxed_env},
        )

        return {
            "success": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "returncode": -1,
            "stdout": "",
            "stderr": f"Execution timed out after {timeout} seconds",
        }
    except Exception as e:
        return {
            "success": False,
            "returncode": -1,
            "stdout": "",
            "stderr": str(e),
        }


def _check_path_permission(context: Any, path: Path, operation: str = "read") -> None:
    """Check path permission for shell tools."""
    if context is None:
        return

    if hasattr(context, "is_path_allowed") and callable(context.is_path_allowed):
        if not context.is_path_allowed(path):
            raise PermissionError(f"Path '{path}' is not allowed for {operation} operation")


def get_env_handler(params: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Get environment variable with sandboxing."""
    import os

    name = params["name"]
    default = params.get("default")

    # In sandbox mode, block sensitive variables
    sensitive_vars = {
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "DATABASE_URL",
        "PASSWORD",
        "SECRET",
        "TOKEN",
        "API_KEY",
        "PRIVATE_KEY",
    }

    if context and hasattr(context, "mode"):
        from src.core.tools.context import ToolExecutionMode
        if context.mode == ToolExecutionMode.SANDBOX:
            if name.upper() in sensitive_vars or "_SECRET" in name.upper():
                return {
                    "name": name,
                    "value": None,
                    "exists": True,
                    "redacted": True,
                }

    value = os.environ.get(name, default)

    return {
        "name": name,
        "value": value,
        "exists": name in os.environ,
    }


def set_env_handler(params: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Set environment variable with sandboxing."""
    name = params["name"]
    value = params["value"]

    # Check if env write is allowed
    if context and hasattr(context, "sandbox_config") and context.sandbox_config:
        if not context.sandbox_config.allow_env_write:
            return {
                "name": name,
                "value": None,
                "success": False,
                "error": "Environment variable modification is disabled in sandbox mode",
            }

    import os

    os.environ[name] = value

    return {
        "name": name,
        "value": value,
        "success": True,
    }


def list_env_handler(params: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """List environment variables with sandboxing."""
    import os

    prefix = params.get("prefix", "")

    # In sandbox mode, filter sensitive variables
    sensitive_patterns = ["SECRET", "PASSWORD", "TOKEN", "KEY", "PRIVATE", "CREDENTIAL"]

    vars_list = []
    for k, v in os.environ.items():
        if k.startswith(prefix) or prefix == "":
            # Filter sensitive variables in sandbox mode
            if context and hasattr(context, "mode"):
                from src.core.tools.context import ToolExecutionMode
                if context.mode == ToolExecutionMode.SANDBOX:
                    if any(p in k.upper() for p in sensitive_patterns):
                        vars_list.append({"name": k, "value": "***REDACTED***"})
                        continue
            vars_list.append({"name": k, "value": v})

    return {
        "variables": vars_list,
        "count": len(vars_list),
    }


def register_shell_tools(registry: ToolRegistry) -> None:
    """Register all shell tools."""

    # Run command
    registry.register(Tool(
        name="shell_run",
        description="Run a shell command",
        category=ToolCategory.SHELL,
        parameters=[
            ToolParameter(
                name="command",
                type=ParameterType.STRING,
                description="Command to run",
            ),
            ToolParameter(
                name="cwd",
                type=ParameterType.DIRECTORY_PATH,
                description="Working directory",
                required=False,
            ),
            ToolParameter(
                name="timeout",
                type=ParameterType.INTEGER,
                description="Timeout in seconds",
                required=False,
                default=30,
                min_value=1,
                max_value=300,
            ),
            ToolParameter(
                name="env",
                type=ParameterType.OBJECT,
                description="Environment variables to set",
                required=False,
            ),
        ],
        returns="Command result with returncode, stdout, stderr",
        permissions=[ToolPermission.EXECUTE],
        handler=run_command_handler,
        tags=["shell", "execute", "command"],
    ))

    # Run Python
    registry.register(Tool(
        name="python_run",
        description="Run Python code",
        category=ToolCategory.SHELL,
        parameters=[
            ToolParameter(
                name="code",
                type=ParameterType.STRING,
                description="Python code to execute",
            ),
            ToolParameter(
                name="timeout",
                type=ParameterType.INTEGER,
                description="Timeout in seconds",
                required=False,
                default=30,
                min_value=1,
                max_value=60,
            ),
        ],
        returns="Execution result with stdout, stderr",
        permissions=[ToolPermission.EXECUTE],
        handler=run_python_handler,
        tags=["python", "execute", "script"],
    ))

    # Get env
    registry.register(Tool(
        name="env_get",
        description="Get environment variable",
        category=ToolCategory.SHELL,
        parameters=[
            ToolParameter(
                name="name",
                type=ParameterType.STRING,
                description="Variable name",
            ),
            ToolParameter(
                name="default",
                type=ParameterType.STRING,
                description="Default value if not found",
                required=False,
            ),
        ],
        returns="Variable value and existence status",
        permissions=[ToolPermission.READ],
        handler=get_env_handler,
        tags=["environment", "env", "variable"],
    ))

    # Set env
    registry.register(Tool(
        name="env_set",
        description="Set environment variable",
        category=ToolCategory.SHELL,
        parameters=[
            ToolParameter(
                name="name",
                type=ParameterType.STRING,
                description="Variable name",
            ),
            ToolParameter(
                name="value",
                type=ParameterType.STRING,
                description="Variable value",
            ),
        ],
        returns="Success status",
        permissions=[ToolPermission.WRITE],
        handler=set_env_handler,
        tags=["environment", "env", "variable"],
    ))

    # List env
    registry.register(Tool(
        name="env_list",
        description="List environment variables",
        category=ToolCategory.SHELL,
        parameters=[
            ToolParameter(
                name="prefix",
                type=ParameterType.STRING,
                description="Filter by prefix",
                required=False,
                default="",
            ),
        ],
        returns="List of variables",
        permissions=[ToolPermission.READ],
        handler=list_env_handler,
        tags=["environment", "env", "list"],
    ))

    logger.info("Registered 5 shell tools")
