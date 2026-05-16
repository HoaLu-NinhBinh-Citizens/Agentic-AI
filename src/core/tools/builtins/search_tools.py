"""
Search Tools

Built-in tools for search operations.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List

from src.core.tools.schema import (
    Tool,
    ToolParameter,
    ToolPermission,
    ToolCategory,
    ParameterType,
)
from src.core.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


def grep_handler(params: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Search for text in files."""
    import fnmatch

    root = Path(params["root"])
    pattern = params["pattern"]
    file_pattern = params.get("file_pattern", "*.py")
    recursive = params.get("recursive", True)
    case_sensitive = params.get("case_sensitive", False)

    if not root.exists():
        return {"success": False, "matches": [], "error": "Root not found"}

    matches = []
    pattern_lower = pattern if case_sensitive else pattern.lower()

    files = root.rglob(file_pattern) if recursive else root.glob(file_pattern)

    for file_path in files:
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                for line_num, line in enumerate(f, 1):
                    line_check = line if case_sensitive else line.lower()
                    if pattern_lower in line_check:
                        matches.append({
                            "file": str(file_path.relative_to(root)),
                            "line": line_num,
                            "content": line.strip(),
                        })
        except Exception:
            continue

    return {
        "success": True,
        "pattern": pattern,
        "matches": matches,
        "count": len(matches),
    }


def find_text_handler(params: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Find files containing text."""
    root = Path(params["root"])
    pattern = params["pattern"]
    file_pattern = params.get("file_pattern", "*")
    recursive = params.get("recursive", True)

    if not root.exists():
        return {"success": False, "files": [], "error": "Root not found"}

    matching_files = []

    files = root.rglob(file_pattern) if recursive else root.glob(file_pattern)

    for file_path in files:
        if not file_path.is_file():
            continue

        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                if pattern in content:
                    matching_files.append(str(file_path.relative_to(root)))
        except Exception:
            continue

    return {
        "success": True,
        "pattern": pattern,
        "files": matching_files,
        "count": len(matching_files),
    }


def list_symbols_handler(params: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """List symbols (functions, classes) in a file."""
    import ast
    import re

    path = Path(params["path"])

    if not path.exists():
        return {"success": False, "symbols": [], "error": "File not found"}

    symbols = []

    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        if params.get("language") == "python" or path.suffix == ".py":
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    symbols.append({
                        "name": node.name,
                        "type": "function",
                        "line": node.lineno,
                    })
                elif isinstance(node, ast.ClassDef):
                    symbols.append({
                        "name": node.name,
                        "type": "class",
                        "line": node.lineno,
                    })
                elif isinstance(node, ast.AsyncFunctionDef):
                    symbols.append({
                        "name": node.name,
                        "type": "async_function",
                        "line": node.lineno,
                    })
        else:
            # Simple regex-based for other languages
            func_pattern = re.compile(r"(?:def|function|func)\s+(\w+)")
            class_pattern = re.compile(r"(?:class|struct)\s+(\w+)")

            for match in func_pattern.finditer(content):
                symbols.append({
                    "name": match.group(1),
                    "type": "function",
                    "line": content[:match.start()].count("\n") + 1,
                })

            for match in class_pattern.finditer(content):
                symbols.append({
                    "name": match.group(1),
                    "type": "class",
                    "line": content[:match.start()].count("\n") + 1,
                })

    except Exception as e:
        return {"success": False, "symbols": [], "error": str(e)}

    return {
        "success": True,
        "path": str(path),
        "symbols": symbols,
        "count": len(symbols),
    }


def search_web_handler(params: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Search the web (placeholder - requires API key)."""
    query = params["query"]
    return {
        "success": False,
        "error": "Web search requires API configuration",
        "query": query,
        "note": "Configure web search API key to enable this tool",
    }


def register_search_tools(registry: ToolRegistry) -> None:
    """Register all search tools."""

    # Grep
    registry.register(Tool(
        name="search_grep",
        description="Search for text pattern in files",
        category=ToolCategory.SEARCH,
        parameters=[
            ToolParameter(
                name="root",
                type=ParameterType.DIRECTORY_PATH,
                description="Root directory to search",
            ),
            ToolParameter(
                name="pattern",
                type=ParameterType.STRING,
                description="Text pattern to search for",
            ),
            ToolParameter(
                name="file_pattern",
                type=ParameterType.STRING,
                description="File pattern (e.g., *.py)",
                required=False,
                default="*.py",
            ),
            ToolParameter(
                name="recursive",
                type=ParameterType.BOOLEAN,
                description="Search recursively",
                required=False,
                default=True,
            ),
            ToolParameter(
                name="case_sensitive",
                type=ParameterType.BOOLEAN,
                description="Case sensitive search",
                required=False,
                default=False,
            ),
        ],
        returns="List of matches with file and line number",
        permissions=[ToolPermission.READ],
        handler=grep_handler,
        tags=["search", "grep", "text"],
    ))

    # Find files with content
    registry.register(Tool(
        name="search_files_with",
        description="Find files containing text",
        category=ToolCategory.SEARCH,
        parameters=[
            ToolParameter(
                name="root",
                type=ParameterType.DIRECTORY_PATH,
                description="Root directory to search",
            ),
            ToolParameter(
                name="pattern",
                type=ParameterType.STRING,
                description="Text pattern to find",
            ),
            ToolParameter(
                name="file_pattern",
                type=ParameterType.STRING,
                description="File pattern",
                required=False,
                default="*",
            ),
            ToolParameter(
                name="recursive",
                type=ParameterType.BOOLEAN,
                description="Search recursively",
                required=False,
                default=True,
            ),
        ],
        returns="List of files containing the pattern",
        permissions=[ToolPermission.READ],
        handler=find_text_handler,
        tags=["search", "find", "files"],
    ))

    # List symbols
    registry.register(Tool(
        name="search_symbols",
        description="List functions and classes in a file",
        category=ToolCategory.SEARCH,
        parameters=[
            ToolParameter(
                name="path",
                type=ParameterType.FILE_PATH,
                description="File path",
            ),
            ToolParameter(
                name="language",
                type=ParameterType.STRING,
                description="Programming language",
                required=False,
            ),
        ],
        returns="List of symbols",
        permissions=[ToolPermission.READ],
        handler=list_symbols_handler,
        tags=["search", "symbols", "ast", "parse"],
    ))

    # Web search (placeholder)
    registry.register(Tool(
        name="web_search",
        description="Search the web",
        category=ToolCategory.SEARCH,
        parameters=[
            ToolParameter(
                name="query",
                type=ParameterType.STRING,
                description="Search query",
            ),
        ],
        returns="Search results",
        permissions=[ToolPermission.NETWORK],
        handler=search_web_handler,
        tags=["search", "web", "internet"],
    ))

    logger.info("Registered 4 search tools")
