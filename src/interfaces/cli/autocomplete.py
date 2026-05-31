"""Autocomplete engine for CLI commands."""

from __future__ import annotations

import os
import readline
from pathlib import Path
from typing import List, Optional


class AutocompleteEngine:
    """Provide Tab autocomplete for CLI commands.

    Integrates with readline for bash-style autocomplete.
    """

    # Available commands
    COMMANDS = [
        "/fix",
        "/review",
        "/explain",
        "/refactor",
        "/test",
        "/stats",
        "/help",
        "/config",
        "/settings",
        "/git-ai",
        "/complete",
        "/watch",
        "/lsp",
    ]

    # File extensions to autocomplete
    CODE_EXTENSIONS = {
        ".py",
        ".js",
        ".ts",
        ".jsx",
        ".tsx",
        ".java",
        ".c",
        ".cpp",
        ".h",
        ".hpp",
        ".rs",
        ".go",
        ".rb",
        ".swift",
        ".kt",
        ".scala",
    }

    # Common skip directories
    SKIP_DIRS = {
        "node_modules",
        "__pycache__",
        ".git",
        ".venv",
        "venv",
        "build",
        "dist",
        ".pytest_cache",
        ".mypy_cache",
        ".tox",
        "htmlcov",
        ".coverage",
    }

    def __init__(self, workspace: Optional[Path] = None):
        """Initialize autocomplete engine.

        Args:
            workspace: Root workspace path for file completion
        """
        self.workspace = workspace or Path.cwd()
        self._files_cache: List[str] = []
        self._symbols_cache: dict = {}
        self._completer_instance: Optional["Completer"] = None

        # Setup readline
        if hasattr(readline, "parse_and_bind"):
            readline.parse_and_bind("tab: complete")
            self._completer_instance = Completer(self)
            readline.set_completer(self._completer_instance.complete)

    def update_workspace(self, workspace: Path) -> None:
        """Update workspace and refresh file cache.

        Args:
            workspace: New workspace path
        """
        self.workspace = workspace
        self._refresh_file_cache()

    def _refresh_file_cache(self) -> None:
        """Refresh the file cache for autocomplete."""
        self._files_cache = []

        if not self.workspace.exists():
            return

        # Collect code files
        for ext in self.CODE_EXTENSIONS:
            for f in self.workspace.rglob(f"*{ext}"):
                # Skip common non-source directories
                parts = f.parts
                if any(skip in parts for skip in self.SKIP_DIRS):
                    continue

                try:
                    rel_path = str(f.relative_to(self.workspace))
                    self._files_cache.append(rel_path)
                except ValueError:
                    pass

    def get_completions(self, text: str) -> List[str]:
        """Get list of completions for given text.

        Args:
            text: Text to complete

        Returns:
            List of possible completions
        """
        tokens = text.split()

        if not tokens:
            return []

        # Complete commands
        if tokens[0].startswith("/"):
            return [cmd for cmd in self.COMMANDS if cmd.startswith(text)]

        # Check if we should complete files
        if text.startswith("@") or any(
            text.startswith(prefix) for prefix in ["./", "../", "src/", "tests/", "~"]
        ):
            return self._get_file_completions(text)

        # Complete flags
        if tokens[0] in ("ai-support", "python", "python3"):
            return self._get_flag_completions(text)

        return []

    def _get_file_completions(self, text: str) -> List[str]:
        """Get file path completions."""
        search = text[1:] if text.startswith("@") else text

        # Exact prefix match
        exact = [f"@{f}" for f in self._files_cache if f.startswith(search)]
        # Fuzzy match (contains)
        fuzzy = [
            f"@{f}" for f in self._files_cache if search in f and f not in exact
        ]

        return exact + fuzzy[:10]

    def _get_flag_completions(self, text: str) -> List[str]:
        """Get command flag completions."""
        flags = [
            "--help",
            "-h",
            "--verbose",
            "-v",
            "--debug",
            "--config",
            "--dry-run",
            "--apply",
            "--format",
            "--focus",
            "--severity",
            "--rule",
            "--file",
        ]
        return [f for f in flags if f.startswith(text)]

    def complete_symbol(self, prefix: str) -> List[str]:
        """Get symbol name completions.

        Args:
            prefix: Symbol prefix to complete

        Returns:
            List of matching symbol names
        """
        symbols = self._symbols_cache.get("symbols", [])
        return [s for s in symbols if s.startswith(prefix)]

    def register_symbols(self, symbols: List[str]) -> None:
        """Register symbol names for completion.

        Args:
            symbols: List of symbol names
        """
        self._symbols_cache["symbols"] = symbols


class Completer:
    """Readline completer wrapper."""

    def __init__(self, engine: AutocompleteEngine):
        self.engine = engine

    def complete(self, text: str, state: int) -> Optional[str]:
        """Readline completion callback.

        Args:
            text: Text being completed
            state: Completion index (0, 1, 2, ...)

        Returns:
            Completion string or None
        """
        if state == 0:
            self._matches = self.engine.get_completions(text)

        if state < len(self._matches):
            return self._matches[state]
        return None


class PathCompleter:
    """Path completer for file and directory paths."""

    def complete(self, text: str, state: int) -> Optional[str]:
        """Complete path (file or directory)."""
        # Expand user home
        if text.startswith("~"):
            text = os.path.expanduser(text)

        # Get directory to list
        if "/" in text or "\\" in text:
            directory = str(Path(text).parent)
            prefix = Path(text).name
        else:
            directory = "."
            prefix = text

        # List directory
        try:
            path = Path(directory)
            if not path.exists():
                return None

            matches: List[str] = []
            for item in path.iterdir():
                name = item.name
                if name.startswith(prefix):
                    if item.is_dir():
                        matches.append(name + os.sep)
                    else:
                        matches.append(name)

            if state < len(matches):
                return matches[state]
        except PermissionError:
            pass

        return None


def setup_autocomplete(workspace: Optional[Path] = None) -> AutocompleteEngine:
    """Setup autocomplete for the CLI.

    Args:
        workspace: Workspace path for file completion

    Returns:
        Configured AutocompleteEngine
    """
    engine = AutocompleteEngine(workspace)
    engine._refresh_file_cache()
    return engine
