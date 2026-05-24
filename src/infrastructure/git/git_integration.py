"""Git integration for Agentic-AI.

Provides:
- Git operations (status, commit, branch, etc.)
- Diff visualization
- Commit history
- Blame analysis
- Git-aware file operations
"""

from __future__ import annotations

import asyncio
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


class GitError(Exception):
    """Git operation error."""
    pass


class DiffFormat(Enum):
    """Diff output format."""
    SIMPLE = "simple"
    SIDE_BY_SIDE = "side_by_side"
    UNIFIED = "unified"


@dataclass
class GitCommit:
    """A git commit."""
    hash: str
    short_hash: str
    message: str
    author: str
    author_email: str
    date: datetime
    refs: str = ""


@dataclass
class GitBranch:
    """A git branch."""
    name: str
    is_current: bool
    is_remote: bool
    upstream: str | None = None
    ahead: int = 0
    behind: int = 0


@dataclass
class GitFileStatus:
    """Status of a file."""
    path: str
    status: str  # M, A, D, R, C, U, ??
    staged: bool = False
    hunks: list[dict] = field(default_factory=list)


@dataclass
class GitDiff:
    """A diff between two commits/refs."""
    old_path: str
    new_path: str
    is_binary: bool = False
    additions: int = 0
    deletions: int = 0
    hunks: list[dict] = field(default_factory=list)


class GitRepo:
    """Git repository wrapper.
    
    Provides async git operations with proper error handling.
    """
    
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self._verify_git_repo()
    
    def _verify_git_repo(self) -> None:
        """Verify this is a git repository."""
        if not (self.path / ".git").exists():
            raise GitError(f"Not a git repository: {self.path}")
    
    async def _run_git(self, *args, check: bool = True) -> str:
        """Run a git command."""
        proc = await asyncio.create_subprocess_exec(
            "git", *args,
            cwd=str(self.path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        
        stdout, stderr = await proc.communicate()
        output = stdout.decode().strip()
        
        if check and proc.returncode != 0:
            error = stderr.decode().strip()
            raise GitError(f"Git command failed: {error}")
        
        return output
    
    async def status(self) -> list[GitFileStatus]:
        """Get working tree status."""
        output = await self._run_git("status", "--porcelain")
        
        files = []
        for line in output.split("\n"):
            if not line:
                continue
            
            # Parse porcelain format: XY filename
            if len(line) < 3:
                continue
            
            index_status = line[0]
            worktree_status = line[1]
            
            # Determine primary status
            if index_status == "?":
                status = "??"
            elif index_status == " ":
                status = worktree_status
            else:
                status = index_status
            
            path = line[3:].strip()
            
            # Handle renamed files
            if " -> " in path:
                path = path.split(" -> ")[-1]
            
            files.append(GitFileStatus(
                path=path,
                status=status,
                staged=index_status not in " ?",
            ))
        
        return files
    
    async def current_branch(self) -> str:
        """Get current branch name."""
        return await self._run_git("branch", "--show-current")
    
    async def branches(self, include_remote: bool = True) -> list[GitBranch]:
        """List all branches."""
        args = ["branch"]
        if include_remote:
            args.append("-a")
        
        output = await self._run_git(*args)
        
        branches = []
        for line in output.split("\n"):
            if not line:
                continue
            
            is_current = line.startswith("*")
            is_remote = "remotes/" in line or "/" in line and not line.startswith("*")
            
            # Clean up name
            name = line.lstrip("* ").strip()
            if name.startswith("remotes/"):
                name = name.replace("remotes/", "")
            
            # Parse tracking info
            upstream = None
            ahead = 0
            behind = 0
            
            if "[ahead" in line:
                match = re.search(r"ahead (\d+)", line)
                if match:
                    ahead = int(match.group(1))
            
            if "[behind" in line:
                match = re.search(r"behind (\d+)", line)
                if match:
                    behind = int(match.group(1))
            
            branches.append(GitBranch(
                name=name,
                is_current=is_current,
                is_remote=is_remote,
                upstream=upstream,
                ahead=ahead,
                behind=behind,
            ))
        
        return branches
    
    async def log(
        self,
        limit: int = 50,
        path: str | None = None,
        author: str | None = None,
    ) -> list[GitCommit]:
        """Get commit log."""
        args = [
            "log",
            f"-{limit}",
            "--pretty=format:%H|%h|%s|%an|%ae|%aI|%D",
        ]
        
        if path:
            args.append("--")
            args.append(path)
        
        if author:
            args.extend(["--author", author])
        
        output = await self._run_git(*args)
        
        commits = []
        for line in output.split("\n"):
            if not line or "|" not in line:
                continue
            
            parts = line.split("|")
            if len(parts) < 6:
                continue
            
            try:
                commits.append(GitCommit(
                    hash=parts[0],
                    short_hash=parts[1],
                    message=parts[2],
                    author=parts[3],
                    author_email=parts[4],
                    date=datetime.fromisoformat(parts[5]),
                    refs=parts[6] if len(parts) > 6 else "",
                ))
            except (ValueError, IndexError):
                continue
        
        return commits
    
    async def show(self, ref: str, stat_only: bool = True) -> str:
        """Show commit details."""
        args = ["show", ref]
        if stat_only:
            args.append("--stat")
        
        return await self._run_git(*args)
    
    async def diff(
        self,
        ref1: str = "HEAD",
        ref2: str | None = None,
        path: str | None = None,
    ) -> list[GitDiff]:
        """Get diff between refs."""
        args = ["diff", "--numstat"]
        
        if ref2:
            args.append(f"{ref1}...{ref2}")
        else:
            args.append(ref1)
        
        if path:
            args.append("--")
            args.append(path)
        
        output = await self._run_git(*args)
        
        diffs = []
        for line in output.split("\n"):
            if not line or "\t" not in line:
                continue
            
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            
            try:
                additions = int(parts[0]) if parts[0] != "-" else 0
                deletions = int(parts[1]) if parts[1] != "-" else 0
                paths = parts[2].split("\t")
                
                diffs.append(GitDiff(
                    old_path=paths[0] if len(paths) > 0 else "",
                    new_path=paths[1] if len(paths) > 1 else paths[0],
                    additions=additions,
                    deletions=deletions,
                ))
            except (ValueError, IndexError):
                continue
        
        return diffs
    
    async def staged_diff(self) -> list[GitDiff]:
        """Get diff of staged changes."""
        args = ["diff", "--cached", "--numstat"]
        output = await self._run_git(*args)
        
        diffs = []
        for line in output.split("\n"):
            if not line or "\t" not in line:
                continue
            
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            
            try:
                diffs.append(GitDiff(
                    old_path=parts[2],
                    new_path=parts[2],
                    additions=int(parts[0]) if parts[0] != "-" else 0,
                    deletions=int(parts[1]) if parts[1] != "-" else 0,
                ))
            except ValueError:
                continue
        
        return diffs
    
    async def blame(self, path: str) -> list[dict]:
        """Get blame for a file."""
        args = ["blame", "--line-porcelain", path]
        output = await self._run_git(*args)
        
        lines = output.split("\n")
        blame_info = []
        current = {}
        
        for line in lines:
            if not line:
                if current:
                    blame_info.append(current)
                    current = {}
                continue
            
            if line.startswith("\t"):
                # Content line
                current["content"] = line[1:]
                blame_info.append(current)
                current = {}
            else:
                parts = line.split(" ", 1)
                if len(parts) == 2:
                    key, value = parts
                    current[key] = value
        
        return blame_info
    
    async def add(self, *paths: str) -> None:
        """Stage files."""
        await self._run_git("add", *paths)
    
    async def restore(self, *paths: str, staged: bool = False) -> None:
        """Restore files."""
        args = ["restore"]
        if staged:
            args.append("--staged")
        args.extend(paths)
        await self._run_git(*args)
    
    async def commit(self, message: str, amend: bool = False) -> str:
        """Create a commit."""
        args = ["commit", "-m", message]
        if amend:
            args.append("--amend")
        
        return await self._run_git(*args)
    
    async def checkout(self, ref: str) -> None:
        """Checkout a branch or commit."""
        await self._run_git("checkout", ref)
    
    async def create_branch(self, name: str, start_point: str | None = None) -> None:
        """Create a new branch."""
        args = ["branch", name]
        if start_point:
            args.append(start_point)
        await self._run_git(*args)
    
    async def delete_branch(self, name: str, force: bool = False) -> None:
        """Delete a branch."""
        args = ["branch"]
        if force:
            args.append("-D")
        else:
            args.append("-d")
        args.append(name)
        await self._run_git(*args)
    
    async def merge(self, branch: str, no_ff: bool = True) -> str:
        """Merge a branch."""
        args = ["merge"]
        if no_ff:
            args.append("--no-ff")
        args.append(branch)
        return await self._run_git(*args)
    
    async def rebase(self, branch: str) -> str:
        """Rebase onto branch."""
        return await self._run_git("rebase", branch)
    
    async def stash(self, push: bool = True, message: str | None = None) -> str:
        """Stash changes."""
        args = ["stash"]
        if push:
            args.append("push")
            if message:
                args.extend(["-m", message])
        return await self._run_git(*args)
    
    async def stash_pop(self) -> str:
        """Pop stash."""
        return await self._run_git("stash", "pop")
    
    async def remote_url(self, remote: str = "origin") -> str | None:
        """Get remote URL."""
        try:
            return await self._run_git("remote", "get-url", remote)
        except GitError:
            return None
    
    async def fetch(self, remote: str | None = None) -> None:
        """Fetch from remote."""
        args = ["fetch"]
        if remote:
            args.append(remote)
        await self._run_git(*args)
    
    async def pull(self, remote: str | None = None, branch: str | None = None) -> str:
        """Pull from remote."""
        args = ["pull"]
        if remote:
            args.append(remote)
        if branch:
            args.append(branch)
        return await self._run_git(*args)
    
    async def push(
        self,
        remote: str = "origin",
        branch: str | None = None,
        set_upstream: bool = False,
        force: bool = False,
    ) -> str:
        """Push to remote."""
        args = ["push"]
        if set_upstream:
            args.append("-u")
        if force:
            args.append("--force")
        args.append(remote)
        if branch:
            args.append(branch)
        return await self._run_git(*args)


class GitDiffFormatter:
    """Format diffs for display."""
    
    def __init__(self, format: DiffFormat = DiffFormat.UNIFIED):
        self.format = format
    
    def format_diff(self, diff: GitDiff) -> str:
        """Format a single diff."""
        if self.format == DiffFormat.UNIFIED:
            return self._format_unified(diff)
        elif self.format == DiffFormat.SIMPLE:
            return self._format_simple(diff)
        return str(diff)
    
    def _format_simple(self, diff: GitDiff) -> str:
        """Format as simple diff."""
        lines = []
        lines.append(f"📄 {diff.new_path}")
        lines.append(f"   +{diff.additions} -{diff.deletions}")
        return "\n".join(lines)
    
    def _format_unified(self, diff: GitDiff) -> str:
        """Format as unified diff."""
        lines = []
        lines.append(f"--- a/{diff.old_path}")
        lines.append(f"+++ b/{diff.new_path}")
        lines.append(f"@@ -{diff.deletions}, +{diff.additions} @@")
        return "\n".join(lines)


class GitInteractive:
    """Interactive git operations."""
    
    def __init__(self, repo: GitRepo):
        self.repo = repo
    
    async def interactive_add(self, paths: list[str]) -> list[str]:
        """Interactively stage parts of files."""
        # For now, just stage all
        await self.repo.add(*paths)
        return paths
    
    async def interactive_rebase(self, count: int) -> str:
        """Interactive rebase."""
        return await self.repo._run_git("rebase", "-i", f"HEAD~{count}")
    
    async def bisect_start(self, bad: str, good: str) -> None:
        """Start bisect."""
        await self.repo._run_git("bisect", "start", bad, good)
    
    async def bisect_good(self) -> None:
        """Mark current as good."""
        await self.repo._run_git("bisect", "good")
    
    async def bisect_bad(self) -> None:
        """Mark current as bad."""
        await self.repo._run_git("bisect", "bad")
    
    async def bisect_reset(self) -> None:
        """Reset bisect."""
        await self.repo._run_git("bisect", "reset")


# Utility functions

async def quick_clone(url: str, path: Path) -> GitRepo:
    """Quick git clone."""
    proc = await asyncio.create_subprocess_exec(
        "git", "clone", url, str(path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()
    
    if proc.returncode != 0:
        raise GitError("Clone failed")
    
    return GitRepo(path)


def is_git_repo(path: Path) -> bool:
    """Check if path is a git repository."""
    return (path / ".git").exists()
