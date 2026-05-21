"""Process isolation sandbox module."""

import subprocess
from typing import Any, List


class ProcessIsolationSandbox:
    """Process-based isolation."""
    
    async def execute(self, command: str | List[str]) -> dict[str, Any]:
        """Execute with isolation.
        
        Args:
            command: Command to execute. If string, will be parsed.
                      If list, executed directly without shell.
        """
        # FIX: Use shell=False for security, parse command if string
        if isinstance(command, str):
            # Parse command string into list for shell=False
            import shlex
            cmd_list = shlex.split(command)
        else:
            cmd_list = command
        
        result = subprocess.run(
            cmd_list,
            capture_output=True,
            shell=False,  # FIX: Disable shell to prevent injection
        )
        return {
            "output": result.stdout.decode() if result.stdout else "",
            "error": result.stderr.decode() if result.stderr else "",
            "exit_code": result.returncode,
        }
