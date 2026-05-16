"""Tool permissions stub for Phase 2B.

Security stub interface for tool permission checking.
Full enforcement will be implemented in Phase 3.
"""

from __future__ import annotations


class ToolPermissions:
    """Stub for tool permission checking.

    Phase 2B: Always returns True for all permission checks.
    Phase 3: Will implement actual permission validation.

    Attributes:
        enabled: Whether permission checking is active.
    """

    def __init__(self, enabled: bool = False) -> None:
        """Initialize tool permissions.

        Args:
            enabled: Whether to enable permission checks (Phase 2B: always False).
        """
        self._enabled = enabled

    @property
    def enabled(self) -> bool:
        """Return whether permission checking is enabled."""
        return self._enabled

    async def can_execute(self, session_id: str, tool_name: str) -> bool:
        """Check if a session can execute a specific tool.

        Phase 2B: Always returns True.

        Args:
            session_id: The session requesting execution.
            tool_name: Name of the tool to execute.

        Returns:
            True (permission granted).
        """
        return True

    async def can_access_server(self, session_id: str, server_name: str) -> bool:
        """Check if a session can access a specific MCP server.

        Phase 2B: Always returns True.

        Args:
            session_id: The session requesting access.
            server_name: Name of the MCP server.

        Returns:
            True (permission granted).
        """
        return True

    async def get_allowed_tools(self, session_id: str) -> list[str] | None:
        """Get list of tools the session is allowed to execute.

        Phase 2B: Returns None (all tools allowed).

        Args:
            session_id: The session to check.

        Returns:
            None (all tools allowed) or list of allowed tool names.
        """
        return None

    async def filter_tool_arguments(
        self,
        session_id: str,
        tool_name: str,
        arguments: dict,
    ) -> dict:
        """Filter or sanitize tool arguments.

        Phase 2B: Returns arguments unchanged.

        Args:
            session_id: The session executing the tool.
            tool_name: Name of the tool.
            arguments: Original tool arguments.

        Returns:
            Filtered arguments (unchanged in Phase 2B).
        """
        return arguments
