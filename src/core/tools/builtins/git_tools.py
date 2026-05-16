"""
Git Tools

Built-in tools for Git operations.
"""

import logging
import subprocess
from pathlib import Path
from typing import Any, Dict

from src.core.tools.schema import (
    Tool,
    ToolParameter,
    ToolPermission,
    ToolCategory,
    ParameterType,
)
from src.core.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


def run_git_command(command: str, cwd: Path) -> Dict[str, Any]:
    """Run a git command."""
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=30,
        )

        return {
            "success": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "returncode": -1,
            "stdout": "",
            "stderr": "Git command timed out",
        }
    except Exception as e:
        return {
            "success": False,
            "returncode": -1,
            "stdout": "",
            "stderr": str(e),
        }


def git_status_handler(params: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Get git status."""
    cwd = Path(params["path"])
    return run_git_command("git status --porcelain", cwd)


def git_branch_handler(params: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Get git branches."""
    cwd = Path(params["path"])
    return run_git_command("git branch -a", cwd)


def git_log_handler(params: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Get git log."""
    cwd = Path(params["path"])
    limit = params.get("limit", 10)
    return run_git_command(f"git log --oneline -n {limit}", cwd)


def git_diff_handler(params: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Get git diff."""
    cwd = Path(params["path"])
    target = params.get("target", "HEAD")
    return run_git_command(f"git diff {target}", cwd)


def git_checkout_handler(params: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Checkout a branch or commit."""
    cwd = Path(params["path"])
    branch = params["branch"]
    create = params.get("create", False)

    if create:
        return run_git_command(f"git checkout -b {branch}", cwd)
    else:
        return run_git_command(f"git checkout {branch}", cwd)


def git_commit_handler(params: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Create a commit."""
    cwd = Path(params["path"])
    message = params["message"]

    # Stage all changes
    stage_result = run_git_command("git add -A", cwd)
    if not stage_result["success"]:
        return stage_result

    return run_git_command(f'git commit -m "{message}"', cwd)


def git_pull_handler(params: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Pull from remote."""
    cwd = Path(params["path"])
    branch = params.get("branch", "")
    return run_git_command(f"git pull {branch}", cwd)


def git_push_handler(params: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Push to remote."""
    cwd = Path(params["path"])
    branch = params.get("branch", "")
    set_upstream = params.get("set_upstream", False)

    if set_upstream:
        return run_git_command(f"git push -u origin {branch}", cwd)
    else:
        return run_git_command(f"git push {branch}", cwd)


def register_git_tools(registry: ToolRegistry) -> None:
    """Register all git tools."""

    # Git status
    registry.register(Tool(
        name="git_status",
        description="Get git repository status",
        category=ToolCategory.GIT,
        parameters=[
            ToolParameter(
                name="path",
                type=ParameterType.DIRECTORY_PATH,
                description="Repository path",
            ),
        ],
        returns="Git status output",
        permissions=[ToolPermission.READ],
        handler=git_status_handler,
        tags=["git", "status", "vcs"],
    ))

    # Git branch
    registry.register(Tool(
        name="git_branch",
        description="List git branches",
        category=ToolCategory.GIT,
        parameters=[
            ToolParameter(
                name="path",
                type=ParameterType.DIRECTORY_PATH,
                description="Repository path",
            ),
        ],
        returns="List of branches",
        permissions=[ToolPermission.READ],
        handler=git_branch_handler,
        tags=["git", "branch", "vcs"],
    ))

    # Git log
    registry.register(Tool(
        name="git_log",
        description="Get git commit history",
        category=ToolCategory.GIT,
        parameters=[
            ToolParameter(
                name="path",
                type=ParameterType.DIRECTORY_PATH,
                description="Repository path",
            ),
            ToolParameter(
                name="limit",
                type=ParameterType.INTEGER,
                description="Number of commits to show",
                required=False,
                default=10,
                min_value=1,
                max_value=100,
            ),
        ],
        returns="Git log output",
        permissions=[ToolPermission.READ],
        handler=git_log_handler,
        tags=["git", "log", "history", "vcs"],
    ))

    # Git diff
    registry.register(Tool(
        name="git_diff",
        description="Get git diff",
        category=ToolCategory.GIT,
        parameters=[
            ToolParameter(
                name="path",
                type=ParameterType.DIRECTORY_PATH,
                description="Repository path",
            ),
            ToolParameter(
                name="target",
                type=ParameterType.STRING,
                description="Target commit/branch",
                required=False,
                default="HEAD",
            ),
        ],
        returns="Git diff output",
        permissions=[ToolPermission.READ],
        handler=git_diff_handler,
        tags=["git", "diff", "vcs"],
    ))

    # Git checkout
    registry.register(Tool(
        name="git_checkout",
        description="Checkout a branch or commit",
        category=ToolCategory.GIT,
        parameters=[
            ToolParameter(
                name="path",
                type=ParameterType.DIRECTORY_PATH,
                description="Repository path",
            ),
            ToolParameter(
                name="branch",
                type=ParameterType.STRING,
                description="Branch or commit to checkout",
            ),
            ToolParameter(
                name="create",
                type=ParameterType.BOOLEAN,
                description="Create new branch",
                required=False,
                default=False,
            ),
        ],
        returns="Checkout result",
        permissions=[ToolPermission.WRITE],
        handler=git_checkout_handler,
        tags=["git", "checkout", "vcs"],
    ))

    # Git commit
    registry.register(Tool(
        name="git_commit",
        description="Create a commit",
        category=ToolCategory.GIT,
        parameters=[
            ToolParameter(
                name="path",
                type=ParameterType.DIRECTORY_PATH,
                description="Repository path",
            ),
            ToolParameter(
                name="message",
                type=ParameterType.STRING,
                description="Commit message",
            ),
        ],
        returns="Commit result",
        permissions=[ToolPermission.WRITE],
        handler=git_commit_handler,
        tags=["git", "commit", "vcs"],
    ))

    # Git pull
    registry.register(Tool(
        name="git_pull",
        description="Pull from remote",
        category=ToolCategory.GIT,
        parameters=[
            ToolParameter(
                name="path",
                type=ParameterType.DIRECTORY_PATH,
                description="Repository path",
            ),
            ToolParameter(
                name="branch",
                type=ParameterType.STRING,
                description="Branch to pull",
                required=False,
                default="",
            ),
        ],
        returns="Pull result",
        permissions=[ToolPermission.READ, ToolPermission.NETWORK],
        handler=git_pull_handler,
        tags=["git", "pull", "vcs", "network"],
    ))

    # Git push
    registry.register(Tool(
        name="git_push",
        description="Push to remote",
        category=ToolCategory.GIT,
        parameters=[
            ToolParameter(
                name="path",
                type=ParameterType.DIRECTORY_PATH,
                description="Repository path",
            ),
            ToolParameter(
                name="branch",
                type=ParameterType.STRING,
                description="Branch to push",
                required=False,
                default="",
            ),
            ToolParameter(
                name="set_upstream",
                type=ParameterType.BOOLEAN,
                description="Set upstream branch",
                required=False,
                default=False,
            ),
        ],
        returns="Push result",
        permissions=[ToolPermission.WRITE, ToolPermission.NETWORK],
        handler=git_push_handler,
        tags=["git", "push", "vcs", "network"],
    ))

    logger.info("Registered 8 git tools")
