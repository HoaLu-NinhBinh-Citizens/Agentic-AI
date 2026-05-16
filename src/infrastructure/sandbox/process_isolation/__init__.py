"""Process isolation sandbox module."""

import subprocess
from typing import Any


class ProcessIsolationSandbox:
    """Process-based isolation."""
    
    async def execute(self, command: str) -> dict[str, Any]:
        """Execute with isolation."""
        result = subprocess.run(command, capture_output=True, shell=True)
        return {
            "output": result.stdout.decode(),
            "error": result.stderr.decode(),
            "exit_code": result.returncode,
        }
