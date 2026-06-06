"""Rich autocomplete engine using prompt_toolkit.

Provides:
- Dropdown completion with descriptions
- Fuzzy matching for commands and file paths
- Inline hint text (grayed out)
- Symbol name completion
- @file path completion with fuzzy search

Falls back to readline-based autocomplete if prompt_toolkit is unavailable.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, List, Optional

try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.completion import (
        Completer,
        Completion,
        FuzzyCompleter,
        merge_completers,
    )
    from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
    from prompt_toolkit.history import FileHistory, InMemoryHistory
    from prompt_toolkit.formatted_text import HTML
    from prompt_toolkit.styles import Style

    HAS_PROMPT_TOOLKIT = True
except ImportError:
    HAS_PROMPT_TOOLKIT = False


# ─── Command Definitions ─────────────────────────────────────────────────────

COMMAND_DEFS: list[tuple[str, str]] = [
    ("/fix", "Show and apply fixes for a file or line"),
    ("/review", "Run code review on files"),
    ("/explain", "Explain a symbol, class, or function"),
    ("/refactor", "Refactor code with suggestions"),
    ("/test", "Generate or run tests"),
    ("/stats", "Show review statistics"),
    ("/help", "Show available commands"),
    ("/config", "View or edit configuration"),
    ("/settings", "Manage settings"),
    ("/git-ai", "AI-assisted git operations"),
    ("/complete", "Code completion"),
    ("/watch", "Watch mode for live review"),
    ("/lsp", "Language server operations"),
    ("/search", "Search codebase"),
    ("/undo", "Undo last fix"),
]

FLAG_DEFS: list[tuple[str, str]] = [
    ("--dry-run", "Preview without applying changes"),
    ("--apply", "Apply fixes automatically"),
    ("--interactive", "Interactive fix mode"),
    ("--format=", "Output format (rich/json/html/markdown)"),
    ("--focus=", "Focus area (security/quality/ml/embedded)"),
    ("--severity=", "Minimum severity (critical/high/medium/low)"),
    ("--rule=", "Filter by rule ID"),
    ("--file=", "Specify target file"),
    ("--verbose", "Verbose output"),
    ("--llm", "Use LLM for fix suggestions"),
]

# ─── Style ────────────────────────────────────────────────────────────────────

PROMPT_STYLE = Style.from_dict({
    "completion-menu.completion": "bg:#313244 #cdd6f4",
    "completion-menu.completion.current": "bg:#45475a #89b4fa bold",
    "completion-menu.meta.completion": "bg:#313244 #6c7086",
    "completion-menu.meta.completion.current": "bg:#45475a #a6adc8",
    "auto-suggest": "#6c7086",
    "prompt": "#89b4fa bold",
}) if HAS_PROMPT_TOOLKIT else None


# ─── Fuzzy Matching ──────────────────────────────────────────────────────────


def _fuzzy_score(query: str, target: str) -> int:
    """Compute fuzzy match score (higher = better match).

    Matches non-contiguous character subsequences.
    Returns -1 if no match.
    """
    query_lower = query.lower()
    target_lower = target.lower()

    # Exact prefix match gets highest score
    if target_lower.startswith(query_lower):
        return 1000 - len(target)

    # Subsequence match
    qi = 0
    score = 0
    last_match_pos = -1
    for ti, char in enumerate(target_lower):
        if qi < len(query_lower) and char == query_lower[qi]:
            # Bonus for consecutive matches
            if ti == last_match_pos + 1:
                score += 10
            else:
                score += 5
            # Bonus for matching at word boundaries
            if ti == 0 or target[ti - 1] in "/_-. ":
                score += 15
            last_match_pos = ti
            qi += 1

    if qi == len(query_lower):
        return score
    return -1


# ─── Completers ──────────────────────────────────────────────────────────────

if HAS_PROMPT_TOOLKIT:

    class CommandCompleter(Completer):
        """Complete slash commands with descriptions."""

        def get_completions(self, document, complete_event):
            text = document.text_before_cursor.lstrip()

            if not text or text[0] == "/":
                query = text.lstrip("/")
                for cmd, desc in COMMAND_DEFS:
                    cmd_name = cmd.lstrip("/")
                    score = _fuzzy_score(query, cmd_name) if query else 500
                    if score >= 0 or not query:
                        yield Completion(
                            cmd,
                            start_position=-len(text),
                            display=cmd,
                            display_meta=desc,
                        )

    class FileCompleter(Completer):
        """Complete @file paths with fuzzy search."""

        def __init__(self, workspace: Optional[Path] = None):
            self.workspace = workspace or Path.cwd()
            self._cache: List[str] = []
            self._cache_valid = False

        def refresh_cache(self) -> None:
            """Refresh file path cache."""
            self._cache = []
            skip_dirs = {
                "node_modules", "__pycache__", ".git", ".venv", "venv",
                "build", "dist", ".pytest_cache", ".mypy_cache",
            }
            code_exts = {
                ".py", ".js", ".ts", ".jsx", ".tsx", ".java",
                ".c", ".cpp", ".h", ".hpp", ".rs", ".go",
            }
            if not self.workspace.exists():
                return
            for ext in code_exts:
                for f in self.workspace.rglob(f"*{ext}"):
                    if any(s in f.parts for s in skip_dirs):
                        continue
                    try:
                        rel = str(f.relative_to(self.workspace)).replace("\\", "/")
                        self._cache.append(rel)
                    except ValueError:
                        pass
            self._cache_valid = True

        def get_completions(self, document, complete_event):
            text = document.text_before_cursor
            if "@" not in text:
                return

            # Extract the part after @
            at_pos = text.rfind("@")
            query = text[at_pos + 1:]

            if not self._cache_valid:
                self.refresh_cache()

            if not query:
                # Show first 15 files
                for f in self._cache[:15]:
                    yield Completion(
                        f"@{f}",
                        start_position=-(len(query) + 1),
                        display=f"@{f}",
                    )
                return

            # Fuzzy match and sort by score
            scored = []
            for f in self._cache:
                score = _fuzzy_score(query, f)
                if score >= 0:
                    scored.append((score, f))

            scored.sort(key=lambda x: -x[0])

            for score, f in scored[:15]:
                yield Completion(
                    f"@{f}",
                    start_position=-(len(query) + 1),
                    display=f"@{f}",
                    display_meta=f"score:{score}",
                )

    class FlagCompleter(Completer):
        """Complete command flags with descriptions."""

        def get_completions(self, document, complete_event):
            text = document.text_before_cursor
            words = text.split()

            # Only complete flags after a command
            if len(words) < 2:
                return

            current = words[-1] if words[-1].startswith("-") else ""
            if not current.startswith("-"):
                return

            for flag, desc in FLAG_DEFS:
                if flag.startswith(current):
                    yield Completion(
                        flag,
                        start_position=-len(current),
                        display=flag,
                        display_meta=desc,
                    )

    class SymbolCompleter(Completer):
        """Complete symbol names from indexed codebase."""

        def __init__(self):
            self._symbols: List[str] = []

        def register_symbols(self, symbols: List[str]) -> None:
            """Register available symbols."""
            self._symbols = symbols

        def get_completions(self, document, complete_event):
            text = document.text_before_cursor
            words = text.split()
            if not words:
                return

            current = words[-1]
            # Only suggest symbols if not a command or flag
            if current.startswith("/") or current.startswith("-") or current.startswith("@"):
                return

            for sym in self._symbols:
                score = _fuzzy_score(current, sym)
                if score >= 0:
                    yield Completion(
                        sym,
                        start_position=-len(current),
                        display=sym,
                    )

    class AICompleter(Completer):
        """Combined completer that routes to appropriate sub-completer."""

        def __init__(self, workspace: Optional[Path] = None):
            self.command_completer = CommandCompleter()
            self.file_completer = FileCompleter(workspace)
            self.flag_completer = FlagCompleter()
            self.symbol_completer = SymbolCompleter()

        def get_completions(self, document, complete_event):
            text = document.text_before_cursor.lstrip()

            if not text or text.startswith("/"):
                yield from self.command_completer.get_completions(document, complete_event)
            elif "@" in text:
                yield from self.file_completer.get_completions(document, complete_event)
            elif text.split()[-1].startswith("-") if text.split() else False:
                yield from self.flag_completer.get_completions(document, complete_event)
            else:
                yield from self.symbol_completer.get_completions(document, complete_event)

        def register_symbols(self, symbols: List[str]) -> None:
            """Register symbols for completion."""
            self.symbol_completer.register_symbols(symbols)

        def refresh_files(self) -> None:
            """Refresh file cache."""
            self.file_completer.refresh_cache()


# ─── Session Factory ─────────────────────────────────────────────────────────


def create_prompt_session(
    workspace: Optional[Path] = None,
    history_file: Optional[str] = None,
) -> "PromptSession | None":
    """Create a prompt_toolkit session with rich autocomplete.

    Args:
        workspace: Workspace root for file completion
        history_file: Path to command history file

    Returns:
        Configured PromptSession, or None if prompt_toolkit unavailable
    """
    if not HAS_PROMPT_TOOLKIT:
        return None

    completer = AICompleter(workspace)
    completer.refresh_files()

    history = (
        FileHistory(history_file) if history_file
        else InMemoryHistory()
    )

    session = PromptSession(
        completer=completer,
        auto_suggest=AutoSuggestFromHistory(),
        history=history,
        style=PROMPT_STYLE,
        complete_while_typing=True,
        complete_in_thread=True,
    )

    return session


def prompt_with_completion(
    session: "PromptSession",
    prompt_text: str = "ai-support> ",
) -> str:
    """Prompt user with rich autocomplete.

    Args:
        session: PromptSession instance
        prompt_text: Prompt string to display

    Returns:
        User input string
    """
    return session.prompt(HTML(f"<prompt>{prompt_text}</prompt>"))


# ─── Fallback for no prompt_toolkit ──────────────────────────────────────────


def setup_rich_autocomplete(
    workspace: Optional[Path] = None,
    history_file: Optional[str] = None,
) -> "PromptSession | None":
    """Setup rich autocomplete, falling back to readline if needed.

    Args:
        workspace: Workspace path
        history_file: Optional history file path

    Returns:
        PromptSession if prompt_toolkit available, else None
    """
    if HAS_PROMPT_TOOLKIT:
        return create_prompt_session(workspace, history_file)

    # Fallback: setup basic readline autocomplete
    from src.interfaces.cli.autocomplete import setup_autocomplete
    setup_autocomplete(workspace)
    return None
