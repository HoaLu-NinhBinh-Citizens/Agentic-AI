"""Command Palette — Cursor-like Cmd/Ctrl+K command interface.

A fuzzy-searchable command palette that provides quick access to:
- Slash commands (/fix, /review, /explain, etc.)
- File actions (open, save, rename, delete)
- Editor commands (format, lint, refactor)
- Navigation (go to symbol, go to file)
- Agent commands (ask AI, explain, fix)
- Settings
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional


# ─── Command types ───────────────────────────────────────────────────────────

class CommandKind(Enum):
    """Category of command in the palette."""
    AGENT = "agent"         # AI-powered commands
    EDITOR = "editor"       # File/text editing
    NAVIGATION = "nav"      # Go to, find
    TERMINAL = "terminal"    # Shell commands
    REFACTOR = "refactor"   # Code transformations
    SETTINGS = "settings"   # Config/preferences
    WORKFLOW = "workflow"   # Review/analysis workflows
    FILE = "file"           # File operations


@dataclass
class Command:
    """A command available in the command palette."""
    id: str
    label: str
    description: str = ""
    kind: CommandKind = CommandKind.EDITOR
    shortcut: str = ""
    icon: str = ""
    keywords: list[str] = field(default_factory=list)
    handler: Optional[Callable[..., Any]] = None
    args_schema: dict[str, Any] = field(default_factory=dict)
    requires_confirmation: bool = False

    def matches(self, query: str) -> float:
        """Return a fuzzy match score (higher = better match)."""
        if not query:
            return 1.0

        query_lower = query.lower()
        label_lower = self.label.lower()
        desc_lower = self.description.lower()

        # Exact prefix match gets highest score
        if label_lower.startswith(query_lower):
            return 10.0
        if any(kw.lower().startswith(query_lower) for kw in self.keywords):
            return 8.0
        if query_lower in label_lower:
            return 6.0
        if query_lower in desc_lower:
            return 4.0

        # Fuzzy character match
        query_chars = [c for c in query_lower if c.isalnum()]
        label_chars = [c for c in label_lower if c.isalnum()]
        if all(qc in label_chars for qc in query_chars):
            return 3.0

        return 0.0


@dataclass
class PaletteResult:
    """A result returned by the command palette."""
    command: Command
    score: float
    match_highlight: list[tuple[int, int]] = field(default_factory=list)  # char ranges to highlight


# ─── Built-in commands ───────────────────────────────────────────────────────

def _get_builtin_commands() -> list[Command]:
    return [
        # Agent commands
        Command(
            id="agent.review",
            label="AI: Review Code",
            description="Run AI-powered code review on current file or selection",
            kind=CommandKind.AGENT,
            shortcut="Ctrl+Shift+A",
            icon="🔍",
            keywords=["review", "analyze", "lint", "check", "ai"],
            handler=None,
        ),
        Command(
            id="agent.fix",
            label="AI: Fix Problems",
            description="Fix code issues in current file using AI suggestions",
            kind=CommandKind.AGENT,
            shortcut="Ctrl+Shift+F",
            icon="🔧",
            keywords=["fix", "repair", "autofix", "correct", "ai"],
            handler=None,
        ),
        Command(
            id="agent.explain",
            label="AI: Explain Code",
            description="Get AI explanation of selected code or current symbol",
            kind=CommandKind.AGENT,
            shortcut="Ctrl+Shift+E",
            icon="💡",
            keywords=["explain", "understand", "what does", "ai"],
            handler=None,
        ),
        Command(
            id="agent.generate",
            label="AI: Generate Code",
            description="Generate code from description or template",
            kind=CommandKind.AGENT,
            icon="✨",
            keywords=["generate", "create", "scaffold", "ai"],
            handler=None,
        ),
        Command(
            id="agent.refactor",
            label="AI: Refactor Selection",
            description="Refactor selected code (extract function, rename, etc.)",
            kind=CommandKind.AGENT,
            icon="🔄",
            keywords=["refactor", "restructure", "improve", "ai"],
            handler=None,
        ),
        Command(
            id="agent.test",
            label="AI: Generate Tests",
            description="Generate unit tests for current file or function",
            kind=CommandKind.AGENT,
            icon="🧪",
            keywords=["test", "unit", "spec", "generate", "ai"],
            handler=None,
        ),
        Command(
            id="agent.chat",
            label="AI: Inline Chat",
            description="Start inline chat with AI assistant",
            kind=CommandKind.AGENT,
            shortcut="Ctrl+I",
            icon="🤖",
            keywords=["chat", "ask", "question", "ai"],
            handler=None,
        ),

        # Workflow commands
        Command(
            id="workflow.security-audit",
            label="Workflow: Security Audit",
            description="Run full security audit on the codebase",
            kind=CommandKind.WORKFLOW,
            icon="🔒",
            keywords=["security", "audit", "vulnerability", "scan"],
            handler=None,
        ),
        Command(
            id="workflow.ml-review",
            label="Workflow: ML Code Review",
            description="Review ML/AI code for data leakage, loss functions, etc.",
            kind=CommandKind.WORKFLOW,
            icon="🧠",
            keywords=["ml", "machine learning", "ai", "data", "model"],
            handler=None,
        ),
        Command(
            id="workflow.dependency-audit",
            label="Workflow: Dependency Audit",
            description="Analyze dependencies and their versions",
            kind=CommandKind.WORKFLOW,
            icon="📦",
            keywords=["deps", "dependencies", "packages", "versions"],
            handler=None,
        ),

        # Editor commands
        Command(
            id="editor.format",
            label="Format Document",
            description="Format the current document",
            kind=CommandKind.EDITOR,
            shortcut="Shift+Alt+F",
            icon="📐",
            keywords=["format", "prettier", "black", "style"],
            handler=None,
        ),
        Command(
            id="editor.lint",
            label="Lint Document",
            description="Run linter on current file",
            kind=CommandKind.EDITOR,
            icon="🔎",
            keywords=["lint", "eslint", "ruff", "check"],
            handler=None,
        ),
        Command(
            id="editor.rename",
            label="Rename Symbol",
            description="Rename all occurrences of a symbol",
            kind=CommandKind.REFACTOR,
            shortcut="F2",
            icon="✏️",
            keywords=["rename", "refactor", "symbol", "identifier"],
            handler=None,
        ),
        Command(
            id="editor.extract-function",
            label="Extract to Function",
            description="Extract selection to a new function",
            kind=CommandKind.REFACTOR,
            shortcut="Ctrl+Shift+R",
            icon="📤",
            keywords=["extract", "function", "refactor"],
            handler=None,
        ),
        Command(
            id="editor.inline-variable",
            label="Inline Variable",
            description="Inline a variable at its usage sites",
            kind=CommandKind.REFACTOR,
            icon="📥",
            keywords=["inline", "variable", "refactor"],
            handler=None,
        ),

        # Navigation commands
        Command(
            id="nav.goto-symbol",
            label="Go to Symbol",
            description="Navigate to a symbol in the current file",
            kind=CommandKind.NAVIGATION,
            shortcut="Ctrl+Shift+O",
            icon="🏷️",
            keywords=["goto", "symbol", "function", "class", "navigate"],
            handler=None,
        ),
        Command(
            id="nav.goto-file",
            label="Go to File",
            description="Quickly open a file by name",
            kind=CommandKind.NAVIGATION,
            shortcut="Ctrl+P",
            icon="📄",
            keywords=["open", "file", "goto", "find"],
            handler=None,
        ),
        Command(
            id="nav.goto-line",
            label="Go to Line",
            description="Go to a specific line number",
            kind=CommandKind.NAVIGATION,
            shortcut="Ctrl+G",
            icon="🔢",
            keywords=["goto", "line", "number", "navigate"],
            handler=None,
        ),
        Command(
            id="nav.find-references",
            label="Find All References",
            description="Find all references to the current symbol",
            kind=CommandKind.NAVIGATION,
            shortcut="Shift+F12",
            icon="📍",
            keywords=["references", "find", "usages", "symbols"],
            handler=None,
        ),

        # File commands
        Command(
            id="file.save",
            label="Save File",
            description="Save the current file",
            kind=CommandKind.FILE,
            shortcut="Ctrl+S",
            icon="💾",
            keywords=["save", "write", "file"],
            handler=None,
        ),
        Command(
            id="file.save-all",
            label="Save All",
            description="Save all open files",
            kind=CommandKind.FILE,
            shortcut="Ctrl+Shift+S",
            icon="💾",
            keywords=["save", "all", "files"],
            handler=None,
        ),
        Command(
            id="file.new",
            label="New File",
            description="Create a new file",
            kind=CommandKind.FILE,
            shortcut="Ctrl+N",
            icon="📝",
            keywords=["new", "create", "file"],
            handler=None,
        ),
        Command(
            id="file.close",
            label="Close File",
            description="Close the current file",
            kind=CommandKind.FILE,
            shortcut="Ctrl+W",
            icon="❌",
            keywords=["close", "file"],
            handler=None,
        ),

        # Terminal commands
        Command(
            id="terminal.new",
            label="New Terminal",
            description="Open a new terminal",
            kind=CommandKind.TERMINAL,
            shortcut="Ctrl+`",
            icon="🖥️",
            keywords=["terminal", "shell", "console", "bash"],
            handler=None,
        ),
        Command(
            id="terminal.run",
            label="Run Selection in Terminal",
            description="Run selected text as a command",
            kind=CommandKind.TERMINAL,
            icon="▶️",
            keywords=["run", "execute", "terminal", "command"],
            handler=None,
        ),

        # Settings commands
        Command(
            id="settings.open",
            label="Open Settings",
            description="Open AI_SUPPORT settings",
            kind=CommandKind.SETTINGS,
            shortcut="Ctrl+,",
            icon="⚙️",
            keywords=["settings", "preferences", "config", "options"],
            handler=None,
        ),
        Command(
            id="settings.keybindings",
            label="Keyboard Shortcuts",
            description="View and edit keyboard shortcuts",
            kind=CommandKind.SETTINGS,
            icon="⌨️",
            keywords=["keybindings", "shortcuts", "keyboard", "hotkeys"],
            handler=None,
        ),
        Command(
            id="settings.rules",
            label="Manage Rules",
            description="Enable/disable linting and analysis rules",
            kind=CommandKind.SETTINGS,
            icon="📋",
            keywords=["rules", "linting", "analysis", "settings"],
            handler=None,
        ),
    ]


# ─── Command Palette ──────────────────────────────────────────────────────────

class CommandPalette:
    """Cursor-like command palette with fuzzy search.

    Usage:
        palette = CommandPalette()
        results = palette.search("fix")
        for result in results:
            print(f"{result.command.icon} {result.command.label}")
            print(f"  {result.command.description}")
    """

    def __init__(
        self,
        custom_commands: Optional[list[Command]] = None,
    ):
        self._commands: dict[str, Command] = {}
        self._search_index: list[Command] = []
        self._recent: list[str] = []  # Recent command IDs
        self._favorites: set[str] = set()  # Favorited command IDs

        # Register built-in commands
        for cmd in _get_builtin_commands():
            self.register(cmd)

        # Register custom commands
        if custom_commands:
            for cmd in custom_commands:
                self.register(cmd)

    def register(self, command: Command) -> None:
        """Register a command in the palette."""
        self._commands[command.id] = command
        self._search_index.append(command)

    def unregister(self, command_id: str) -> bool:
        """Unregister a command."""
        cmd = self._commands.pop(command_id, None)
        if cmd:
            self._search_index.remove(cmd)
            return True
        return False

    def search(
        self,
        query: str,
        max_results: int = 10,
        kind_filter: Optional[list[CommandKind]] = None,
    ) -> list[PaletteResult]:
        """Search commands by fuzzy match."""
        if not query and kind_filter is None:
            # Return recent commands when no query
            return self._recent_commands(max_results)

        results: list[PaletteResult] = []

        for cmd in self._search_index:
            # Apply kind filter
            if kind_filter and cmd.kind not in kind_filter:
                continue

            # Score the match
            score = cmd.matches(query)
            if score > 0:
                highlight = self._get_highlight_ranges(cmd.label, query)
                results.append(PaletteResult(
                    command=cmd,
                    score=score,
                    match_highlight=highlight,
                ))

        # Sort by score (descending), then by recency
        results.sort(
            key=lambda r: (
                -r.score,
                -self._recent.index(r.command.id) if r.command.id in self._recent else 0,
            ),
        )

        return results[:max_results]

    def _recent_commands(self, max_results: int) -> list[PaletteResult]:
        """Get recently used commands."""
        results = []
        for cmd_id in reversed(self._recent[:max_results]):
            cmd = self._commands.get(cmd_id)
            if cmd:
                results.append(PaletteResult(command=cmd, score=1.0, match_highlight=[]))
        return results

    def _get_highlight_ranges(
        self,
        label: str,
        query: str,
    ) -> list[tuple[int, int]]:
        """Get character ranges in label that match the query."""
        if not query:
            return []

        label_lower = label.lower()
        query_lower = query.lower()

        # Find prefix match
        if label_lower.startswith(query_lower):
            return [(0, len(query))]

        # Find substring
        start = label_lower.find(query_lower)
        if start >= 0:
            return [(start, start + len(query))]

        # Fuzzy match - find matching characters
        ranges: list[tuple[int, int]] = []
        qi = 0
        start = -1
        for i, c in enumerate(label_lower):
            if qi < len(query_lower) and c == query_lower[qi]:
                if start < 0:
                    start = i
                qi += 1
            elif start >= 0 and qi > 0:
                ranges.append((start, i))
                start = -1
                qi = 0

        if start >= 0 and qi > 0:
            ranges.append((start, start + qi))

        return ranges

    def execute(self, command_id: str, **kwargs) -> Any:
        """Execute a command by ID."""
        cmd = self._commands.get(command_id)
        if not cmd:
            raise ValueError(f"Unknown command: {command_id}")

        # Record as recent
        if command_id in self._recent:
            self._recent.remove(command_id)
        self._recent.insert(0, command_id)
        if len(self._recent) > 20:
            self._recent.pop()

        # Execute handler
        if cmd.handler:
            return cmd.handler(**kwargs)

        return {"executed": command_id, "args": kwargs}

    def toggle_favorite(self, command_id: str) -> bool:
        """Toggle favorite status for a command."""
        if command_id in self._favorites:
            self._favorites.remove(command_id)
            return False
        self._favorites.add(command_id)
        return True

    def get_favorites(self) -> list[Command]:
        """Get favorited commands."""
        return [self._commands[cid] for cid in self._favorites if cid in self._commands]

    def get_all_commands(self) -> list[Command]:
        """Get all registered commands."""
        return list(self._commands.values())

    def get_by_kind(self, kind: CommandKind) -> list[Command]:
        """Get commands by kind."""
        return [cmd for cmd in self._commands.values() if cmd.kind == kind]

    def get_stats(self) -> dict[str, Any]:
        """Get command palette statistics."""
        return {
            "total_commands": len(self._commands),
            "by_kind": {
                k.value: len([c for c in self._commands.values() if c.kind == k])
                for k in CommandKind
            },
            "recent_count": len(self._recent),
            "favorites_count": len(self._favorites),
        }
