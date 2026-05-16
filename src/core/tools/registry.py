"""
Tool Registry

Central registry for managing tools.
"""

import logging
from typing import Any, Callable, Dict, List, Optional, Set

from src.core.tools.schema import (
    Tool,
    ToolCategory,
    ToolPermission,
    ToolParameter,
)

logger = logging.getLogger(__name__)


class ToolRegistry:
    """
    Central registry for tools.

    Features:
    - Tool registration and unregistration
    - Tool lookup by name
    - Tool search by name, category, tags
    - Permission checking
    - Tool validation

    Usage:
        registry = ToolRegistry()

        # Register a tool
        registry.register(my_tool)

        # Lookup
        tool = registry.get("read_file")

        # Search
        file_tools = registry.search(category=ToolCategory.FILE)

        # List all
        all_tools = registry.list_tools()
    """

    def __init__(self):
        """Initialize registry."""
        self._tools: Dict[str, Tool] = {}
        self._categories: Dict[ToolCategory, List[str]] = {}
        self._tags: Dict[str, Set[str]] = {}  # tag -> tool names
        self._permissions: Dict[ToolPermission, Set[str]] = {}  # permission -> tool names

    def register(self, tool: Tool) -> None:
        """
        Register a tool.

        Args:
            tool: Tool definition to register

        Raises:
            ValueError: If tool with same name already exists
        """
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered")

        # Validate tool
        self._validate_tool(tool)

        # Store tool
        self._tools[tool.name] = tool

        # Update category index
        if tool.category not in self._categories:
            self._categories[tool.category] = []
        self._categories[tool.category].append(tool.name)

        # Update tag index
        for tag in tool.tags:
            if tag not in self._tags:
                self._tags[tag] = set()
            self._tags[tag].add(tool.name)

        # Update permission index
        for permission in tool.permissions:
            if permission not in self._permissions:
                self._permissions[permission] = set()
            self._permissions[permission].add(tool.name)

        logger.info(f"Registered tool: {tool.name} (category={tool.category.value})")

    def unregister(self, name: str) -> bool:
        """
        Unregister a tool.

        Args:
            name: Tool name to unregister

        Returns:
            True if tool was unregistered, False if not found
        """
        if name not in self._tools:
            return False

        tool = self._tools[name]

        # Remove from main index
        del self._tools[name]

        # Remove from category index
        if tool.category in self._categories:
            self._categories[tool.category].remove(name)
            if not self._categories[tool.category]:
                del self._categories[tool.category]

        # Remove from tag index
        for tag in tool.tags:
            if tag in self._tags:
                self._tags[tag].discard(name)
                if not self._tags[tag]:
                    del self._tags[tag]

        # Remove from permission index
        for permission in tool.permissions:
            if permission in self._permissions:
                self._permissions[permission].discard(name)
                if not self._permissions[permission]:
                    del self._permissions[permission]

        logger.info(f"Unregistered tool: {name}")
        return True

    def get(self, name: str) -> Optional[Tool]:
        """
        Get a tool by name.

        Args:
            name: Tool name

        Returns:
            Tool definition or None if not found
        """
        return self._tools.get(name)

    def list_tools(self) -> List[Tool]:
        """
        List all registered tools.

        Returns:
            List of all tools
        """
        return list(self._tools.values())

    def list_tool_names(self) -> List[str]:
        """
        List all tool names.

        Returns:
            List of tool names
        """
        return list(self._tools.keys())

    def search(
        self,
        query: Optional[str] = None,
        category: Optional[ToolCategory] = None,
        tags: Optional[List[str]] = None,
        permissions: Optional[List[ToolPermission]] = None,
    ) -> List[Tool]:
        """
        Search for tools.

        Args:
            query: Search in name and description
            category: Filter by category
            tags: Filter by tags (all must match)
            permissions: Filter by permissions (any must match)

        Returns:
            List of matching tools
        """
        results = set(self._tools.keys())

        # Filter by query
        if query:
            query_lower = query.lower()
            matching = {
                name
                for name, tool in self._tools.items()
                if query_lower in tool.name.lower()
                or query_lower in tool.description.lower()
            }
            results &= matching

        # Filter by category
        if category:
            if category in self._categories:
                results &= set(self._categories[category])
            else:
                return []  # Category doesn't exist

        # Filter by tags
        if tags:
            for tag in tags:
                if tag in self._tags:
                    results &= self._tags[tag]
                else:
                    return []  # Tag doesn't exist

        # Filter by permissions
        if permissions:
            perm_results = set()
            for perm in permissions:
                if perm in self._permissions:
                    perm_results |= self._permissions[perm]
            results &= perm_results

        return [self._tools[name] for name in results]

    def get_by_category(self, category: ToolCategory) -> List[Tool]:
        """
        Get all tools in a category.

        Args:
            category: Tool category

        Returns:
            List of tools in category
        """
        names = self._categories.get(category, [])
        return [self._tools[name] for name in names]

    def get_by_tag(self, tag: str) -> List[Tool]:
        """
        Get all tools with a tag.

        Args:
            tag: Tag to search for

        Returns:
            List of tools with tag
        """
        names = self._tags.get(tag, set())
        return [self._tools[name] for name in names]

    def get_by_permission(self, permission: ToolPermission) -> List[Tool]:
        """
        Get all tools with a permission.

        Args:
            permission: Permission to search for

        Returns:
            List of tools with permission
        """
        names = self._permissions.get(permission, set())
        return [self._tools[name] for name in names]

    def get_categories(self) -> List[ToolCategory]:
        """
        Get all registered categories.

        Returns:
            List of categories with at least one tool
        """
        return list(self._categories.keys())

    def get_tags(self) -> List[str]:
        """
        Get all registered tags.

        Returns:
            List of all tags
        """
        return list(self._tags.keys())

    def has_tool(self, name: str) -> bool:
        """
        Check if a tool is registered.

        Args:
            name: Tool name

        Returns:
            True if tool exists
        """
        return name in self._tools

    def count(self) -> int:
        """
        Get total number of registered tools.

        Returns:
            Number of tools
        """
        return len(self._tools)

    def count_by_category(self) -> Dict[ToolCategory, int]:
        """
        Get tool counts by category.

        Returns:
            Dict mapping category to count
        """
        return {cat: len(tools) for cat, tools in self._categories.items()}

    def _validate_tool(self, tool: Tool) -> None:
        """
        Validate a tool definition.

        Args:
            tool: Tool to validate

        Raises:
            ValueError: If tool is invalid
        """
        if not tool.name:
            raise ValueError("Tool name is required")

        if not tool.description:
            raise ValueError(f"Tool '{tool.name}' description is required")

        # Check parameter names are unique
        param_names = [p.name for p in tool.parameters]
        if len(param_names) != len(set(param_names)):
            raise ValueError(f"Tool '{tool.name}' has duplicate parameter names")

        # Validate parameter defaults
        for param in tool.parameters:
            if param.default is not None:
                valid, _ = param.validate(param.default)
                if not valid:
                    raise ValueError(
                        f"Tool '{tool.name}' parameter '{param.name}' has invalid default"
                    )

    def clear(self) -> None:
        """Clear all registered tools."""
        self._tools.clear()
        self._categories.clear()
        self._tags.clear()
        self._permissions.clear()
        logger.info("Cleared all tools from registry")

    def get_tool_info(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed tool info.

        Args:
            name: Tool name

        Returns:
            Dict with tool info or None
        """
        tool = self.get(name)
        if not tool:
            return None

        return {
            "name": tool.name,
            "description": tool.description,
            "category": tool.category.value,
            "parameters": [p.to_dict() for p in tool.parameters],
            "returns": tool.returns,
            "permissions": [p.value for p in tool.permissions],
            "timeout": tool.timeout,
            "cacheable": tool.cacheable,
            "tags": tool.tags,
            "version": tool.version,
        }


# Global singleton registry
_registry: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    """
    Get the global tool registry instance.

    Returns:
        Global ToolRegistry
    """
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry


def reset_tool_registry() -> None:
    """Reset the global tool registry."""
    global _registry
    if _registry:
        _registry.clear()
    _registry = None
