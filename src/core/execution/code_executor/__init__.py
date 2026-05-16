"""Code executor module."""

from typing import Any


class CodeExecutor:
    """Executes code in sandbox."""
    
    async def execute(self, code: str, language: str = "python") -> dict[str, Any]:
        """Execute code."""
        return {"output": "", "error": None, "exit_code": 0}
