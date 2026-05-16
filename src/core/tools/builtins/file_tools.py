"""
File Tools

Built-in tools for file operations with sandbox integration.
"""

import logging
from pathlib import Path
from typing import Any, Dict, TYPE_CHECKING

from src.core.tools.schema import (
    Tool,
    ToolParameter,
    ToolPermission,
    ToolCategory,
    ParameterType,
)
from src.core.tools.registry import ToolRegistry

if TYPE_CHECKING:
    from src.core.tools.context import ToolContext

logger = logging.getLogger(__name__)


def _check_path_permission(context: Any, path: Path, operation: str = "read") -> None:
    """
    Check if path operation is allowed in current context.

    Args:
        context: Tool execution context
        path: Path to check
        operation: Operation type (read, write, delete)

    Raises:
        PermissionError: If operation is not allowed
    """
    from src.core.tools.context import ToolExecutionMode

    if context is None:
        return

    if hasattr(context, "mode"):
        mode = context.mode
        if mode == ToolExecutionMode.DRY_RUN:
            if operation != "read":
                raise PermissionError(f"{operation.capitalize()} operations not allowed in dry_run mode")

    if hasattr(context, "is_path_allowed") and callable(context.is_path_allowed):
        if not context.is_path_allowed(path):
            raise PermissionError(f"Path '{path}' is not allowed for {operation} operation")

    # Check via sandbox manager if available
    if hasattr(context, "sandbox_enabled") and context.sandbox_enabled:
        if hasattr(context, "sandbox_manager") and context.sandbox_manager:
            is_allowed, error = context.sandbox_manager.is_path_allowed(path)
            if not is_allowed:
                raise PermissionError(error or f"Path '{path}' is not allowed for {operation} operation")


def read_file_handler(params: Dict[str, Any], context: Any) -> str:
    """Read file contents with sandbox validation."""
    path = Path(params["path"])
    encoding = params.get("encoding", "utf-8")

    _check_path_permission(context, path, "read")

    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    with open(path, "r", encoding=encoding) as f:
        content = f.read()

    return content


def write_file_handler(params: Dict[str, Any], context: Any) -> str:
    """Write file contents with sandbox validation."""
    path = Path(params["path"])
    content = params["content"]
    encoding = params.get("encoding", "utf-8")
    create_dirs = params.get("create_directories", True)

    _check_path_permission(context, path, "write")

    if create_dirs:
        _check_path_permission(context, path.parent, "write")
        path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding=encoding) as f:
        f.write(content)

    return f"Written {len(content)} bytes to {path}"


def list_directory_handler(params: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """List directory contents with sandbox validation."""
    path = Path(params["path"])

    _check_path_permission(context, path, "read")

    if not path.exists():
        raise FileNotFoundError(f"Directory not found: {path}")

    if not path.is_dir():
        raise NotADirectoryError(f"Not a directory: {path}")

    items = []
    for item in path.iterdir():
        rel_path = item.relative_to(path)
        items.append({
            "name": item.name,
            "type": "directory" if item.is_dir() else "file",
            "path": str(item),
            "size": item.stat().st_size if item.is_file() else None,
        })

    return {"path": str(path), "items": items, "count": len(items)}


def file_exists_handler(params: Dict[str, Any], context: Any) -> bool:
    """Check if file exists with sandbox validation."""
    path = Path(params["path"])

    _check_path_permission(context, path, "read")

    return path.exists()


def delete_file_handler(params: Dict[str, Any], context: Any) -> str:
    """Delete a file with sandbox validation."""
    path = Path(params["path"])

    _check_path_permission(context, path, "delete")

    if not path.exists():
        return f"File does not exist: {path}"

    if path.is_dir():
        raise IsADirectoryError(f"Cannot delete directory with this tool: {path}")

    path.unlink()
    return f"Deleted: {path}"


def copy_file_handler(params: Dict[str, Any], context: Any) -> str:
    """Copy a file with sandbox validation."""
    import shutil

    src = Path(params["source"])
    dst = Path(params["destination"])

    _check_path_permission(context, src, "read")
    _check_path_permission(context, dst.parent, "write")

    if not src.exists():
        raise FileNotFoundError(f"Source not found: {src}")

    dst.parent.mkdir(parents=True, exist_ok=True)

    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=params.get("overwrite", False))
    else:
        shutil.copy2(src, dst)

    return f"Copied {src} to {dst}"


def move_file_handler(params: Dict[str, Any], context: Any) -> str:
    """Move a file with sandbox validation."""
    import shutil

    src = Path(params["source"])
    dst = Path(params["destination"])

    _check_path_permission(context, src, "delete")
    _check_path_permission(context, dst.parent, "write")

    if not src.exists():
        raise FileNotFoundError(f"Source not found: {src}")

    dst.parent.mkdir(parents=True, exist_ok=True)

    shutil.move(str(src), str(dst))

    return f"Moved {src} to {dst}"


def get_file_info_handler(params: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Get file information with sandbox validation."""
    path = Path(params["path"])

    _check_path_permission(context, path, "read")

    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    stat = path.stat()

    return {
        "path": str(path),
        "name": path.name,
        "type": "directory" if path.is_dir() else "file",
        "size": stat.st_size,
        "modified": stat.st_mtime,
        "created": stat.st_ctime,
        "is_file": path.is_file(),
        "is_dir": path.is_dir(),
        "is_symlink": path.is_symlink(),
    }


def search_files_handler(params: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Search for files by pattern with sandbox validation."""
    import fnmatch

    root = Path(params["root"])
    pattern = params["pattern"]
    recursive = params.get("recursive", False)

    _check_path_permission(context, root, "read")

    if not root.exists():
        raise FileNotFoundError(f"Root not found: {root}")

    matches = []
    if recursive:
        for path in root.rglob(pattern):
            # Validate each match
            try:
                _check_path_permission(context, path, "read")
                matches.append(str(path))
            except PermissionError:
                # Skip paths outside allowed directories
                continue
    else:
        for path in root.glob(pattern):
            try:
                _check_path_permission(context, path, "read")
                matches.append(str(path))
            except PermissionError:
                continue

    return {"pattern": pattern, "matches": matches, "count": len(matches)}


def register_file_tools(registry: ToolRegistry) -> None:
    """Register all file tools."""

    # Read file
    registry.register(Tool(
        name="file_read",
        description="Read contents of a file",
        category=ToolCategory.FILE,
        parameters=[
            ToolParameter(
                name="path",
                type=ParameterType.FILE_PATH,
                description="Path to the file",
            ),
            ToolParameter(
                name="encoding",
                type=ParameterType.STRING,
                description="File encoding",
                required=False,
                default="utf-8",
            ),
        ],
        returns="File contents as string",
        permissions=[ToolPermission.READ],
        handler=read_file_handler,
        tags=["file", "read", "io"],
    ))

    # Write file
    registry.register(Tool(
        name="file_write",
        description="Write contents to a file",
        category=ToolCategory.FILE,
        parameters=[
            ToolParameter(
                name="path",
                type=ParameterType.FILE_PATH,
                description="Path to write to",
            ),
            ToolParameter(
                name="content",
                type=ParameterType.STRING,
                description="Content to write",
            ),
            ToolParameter(
                name="encoding",
                type=ParameterType.STRING,
                description="File encoding",
                required=False,
                default="utf-8",
            ),
            ToolParameter(
                name="create_directories",
                type=ParameterType.BOOLEAN,
                description="Create parent directories if needed",
                required=False,
                default=True,
            ),
        ],
        returns="Success message",
        permissions=[ToolPermission.WRITE, ToolPermission.FILESYSTEM],
        handler=write_file_handler,
        tags=["file", "write", "io"],
    ))

    # List directory
    registry.register(Tool(
        name="directory_list",
        description="List contents of a directory",
        category=ToolCategory.FILE,
        parameters=[
            ToolParameter(
                name="path",
                type=ParameterType.DIRECTORY_PATH,
                description="Directory path",
            ),
        ],
        returns="Directory contents",
        permissions=[ToolPermission.READ],
        handler=list_directory_handler,
        tags=["file", "directory", "list"],
    ))

    # File exists
    registry.register(Tool(
        name="file_exists",
        description="Check if a file exists",
        category=ToolCategory.FILE,
        parameters=[
            ToolParameter(
                name="path",
                type=ParameterType.FILE_PATH,
                description="Path to check",
            ),
        ],
        returns="Boolean",
        permissions=[ToolPermission.READ],
        handler=file_exists_handler,
        tags=["file", "exists", "check"],
    ))

    # Delete file
    registry.register(Tool(
        name="file_delete",
        description="Delete a file",
        category=ToolCategory.FILE,
        parameters=[
            ToolParameter(
                name="path",
                type=ParameterType.FILE_PATH,
                description="File to delete",
            ),
        ],
        returns="Success message",
        permissions=[ToolPermission.WRITE, ToolPermission.FILESYSTEM],
        handler=delete_file_handler,
        tags=["file", "delete", "dangerous"],
    ))

    # Copy file
    registry.register(Tool(
        name="file_copy",
        description="Copy a file or directory",
        category=ToolCategory.FILE,
        parameters=[
            ToolParameter(
                name="source",
                type=ParameterType.FILE_PATH,
                description="Source path",
            ),
            ToolParameter(
                name="destination",
                type=ParameterType.FILE_PATH,
                description="Destination path",
            ),
            ToolParameter(
                name="overwrite",
                type=ParameterType.BOOLEAN,
                description="Overwrite if exists",
                required=False,
                default=False,
            ),
        ],
        returns="Success message",
        permissions=[ToolPermission.READ, ToolPermission.WRITE, ToolPermission.FILESYSTEM],
        handler=copy_file_handler,
        tags=["file", "copy", "io"],
    ))

    # Move file
    registry.register(Tool(
        name="file_move",
        description="Move a file or directory",
        category=ToolCategory.FILE,
        parameters=[
            ToolParameter(
                name="source",
                type=ParameterType.FILE_PATH,
                description="Source path",
            ),
            ToolParameter(
                name="destination",
                type=ParameterType.FILE_PATH,
                description="Destination path",
            ),
        ],
        returns="Success message",
        permissions=[ToolPermission.WRITE, ToolPermission.FILESYSTEM],
        handler=move_file_handler,
        tags=["file", "move", "io"],
    ))

    # File info
    registry.register(Tool(
        name="file_info",
        description="Get information about a file",
        category=ToolCategory.FILE,
        parameters=[
            ToolParameter(
                name="path",
                type=ParameterType.FILE_PATH,
                description="File path",
            ),
        ],
        returns="File information",
        permissions=[ToolPermission.READ],
        handler=get_file_info_handler,
        tags=["file", "info", "metadata"],
    ))

    # Search files
    registry.register(Tool(
        name="file_search",
        description="Search for files by pattern",
        category=ToolCategory.FILE,
        parameters=[
            ToolParameter(
                name="root",
                type=ParameterType.DIRECTORY_PATH,
                description="Root directory to search",
            ),
            ToolParameter(
                name="pattern",
                type=ParameterType.STRING,
                description="Glob pattern (e.g., *.py)",
            ),
            ToolParameter(
                name="recursive",
                type=ParameterType.BOOLEAN,
                description="Search recursively",
                required=False,
                default=False,
            ),
        ],
        returns="List of matching files",
        permissions=[ToolPermission.READ],
        handler=search_files_handler,
        tags=["file", "search", "glob"],
    ))

    logger.info("Registered 9 file tools")
