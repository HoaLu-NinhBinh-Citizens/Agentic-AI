"""CLI commands module."""

from typing import Any


class Command:
    """Base command class."""
    
    name: str = ""
    help: str = ""
    
    async def execute(self, args: list[str]) -> int:
        """Execute command."""
        return 0


class HelpCommand(Command):
    """Help command."""
    name = "help"
    help = "Show help information"
    
    async def execute(self, args: list[str]) -> int:
        print("Available commands: help, status")
        return 0
