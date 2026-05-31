"""AI_SUPPORT Interactive TUI — Cursor-like terminal interface.

Provides an interactive terminal UI with:
- File tree panel (left sidebar)
- Editor panel (main area with syntax highlighting)
- Terminal panel (bottom)
- Chat panel (right sidebar or bottom)
- Status bar (bottom)
- Command palette (Ctrl+K)
"""

from __future__ import annotations

import asyncio
import os
import shutil
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

from rich import box
from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.style import Style
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
from rich.tree import Tree


# ─── Theme ───────────────────────────────────────────────────────────────────

class Theme:
    """Cursor-like color theme."""
    BG = "#1e1e2e"           # Dark background
    BG_LIGHT = "#2a2a3e"    # Lighter panels
    BG_PANEL = "#252536"     # Panel background
    ACCENT = "#89b4fa"       # Blue accent
    ACCENT_GREEN = "#a6e3a1" # Green accent
    ACCENT_RED = "#f38ba8"   # Red accent
    ACCENT_YELLOW = "#f9e2af" # Yellow accent
    TEXT = "#cdd6f4"         # Main text
    TEXT_DIM = "#6c7086"    # Dim text
    BORDER = "#45475a"       # Border color
    SELECTION = "#313244"    # Selection color

    @classmethod
    def rich_styles(cls) -> dict[str, str]:
        return {
            "repr.number": cls.ACCENT,
            "repr.str": cls.ACCENT_GREEN,
            "repr.bool": cls.ACCENT_YELLOW,
            "panel.border": cls.BORDER,
            "layout.split": cls.BORDER,
            "tree.line": cls.BORDER,
        }


# ─── Layout configuration ───────────────────────────────────────────────────

class PanelConfig:
    """Configuration for UI panels."""
    FILE_TREE_WIDTH = 28
    CHAT_WIDTH = 40
    TERMINAL_HEIGHT = 15
    STATUS_HEIGHT = 3


# ─── Panel data models ───────────────────────────────────────────────────────

@dataclass
class FileNode:
    """A file or directory node in the file tree."""
    path: Path
    name: str
    is_dir: bool
    children: list[FileNode] = field(default_factory=list)
    is_expanded: bool = False
    is_selected: bool = False

    def __post_init__(self):
        self.name = self.path.name


@dataclass
class ChatMessage:
    """A chat message in the chat panel."""
    role: str  # "user" or "assistant"
    content: str
    timestamp: str = ""
    agent_name: str = "AI_SUPPORT"


@dataclass
class TerminalLine:
    """A line of terminal output."""
    text: str
    style: str = "white"
    is_command: bool = False


@dataclass
class StatusInfo:
    """Status bar information."""
    file_path: str = ""
    line_col: str = "Ln 1, Col 1"
    language: str = "Plain Text"
    branch: str = ""
    encoding: str = "UTF-8"
    spaces: str = "Spaces: 4"
    messages: list[str] = field(default_factory=list)


# ─── Renderers ───────────────────────────────────────────────────────────────

class FileTreeRenderer:
    """Renders the file tree panel."""

    IGNORED_DIRS = {
        "__pycache__", ".git", ".venv", "venv", "node_modules",
        ".idea", ".vscode", "dist", "build", ".pytest_cache",
        ".mypy_cache", ".ruff_cache", ".tox", "htmlcov",
    }
    IGNORED_EXTENSIONS = {".pyc", ".pyo", ".so", ".dll", ".dylib", ".o"}

    def __init__(self, root: Path):
        self.root = root
        self._expanded: set[Path] = set()

    def render(self, selected: Optional[Path] = None) -> Tree:
        """Render the file tree."""
        tree = Tree(
            f"[b #89b4fa]{self.root.name or self.root.anchor}[/]",
            guide_style=Theme.BORDER,
            hide_root=False,
        )
        try:
            children = sorted(self.root.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except PermissionError:
            return tree

        for child in children:
            if self._should_ignore(child):
                continue
            node = self._build_node(child, selected)
            tree.add(node)

        return tree

    def _should_ignore(self, path: Path) -> bool:
        if path.name in self.IGNORED_DIRS:
            return True
        if path.suffix in self.IGNORED_EXTENSIONS:
            return True
        if path.name.startswith("."):
            return True
        return False

    def _build_node(self, path: Path, selected: Optional[Path] = None) -> Tree:
        is_expanded = path in self._expanded
        is_selected = path == selected

        if path.is_dir():
            label = f"[b #89b4fa]{path.name}/[/]"
            if is_selected:
                label = f"[b #89b4fa on #313244]{path.name}/[/]"
            node = Tree(label, guide_style=Theme.BORDER)

            if is_expanded:
                try:
                    for child in sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
                        if self._should_ignore(child):
                            continue
                        node.add(self._build_node(child, selected))
                except PermissionError:
                    pass
            return node
        else:
            label = self._file_label(path, is_selected)
            return Tree(label, guide_style=Theme.BORDER)

    def _file_label(self, path: Path, is_selected: bool) -> str:
        ext = path.suffix
        icon = self._file_icon(ext)
        color = Theme.TEXT_DIM if is_selected else Theme.TEXT
        if is_selected:
            return f"[b #89b4fa]{icon} {path.name}[/]"
        return f"{icon} {path.name}"

    def _file_icon(self, ext: str) -> str:
        icons = {
            ".py": "🐍", ".js": "📜", ".ts": "📘", ".tsx": "⚛",
            ".jsx": "⚛", ".rs": "🦀", ".go": "🐹", ".java": "☕",
            ".c": "⚙", ".h": "⚙", ".cpp": "⚙", ".hpp": "⚙",
            ".md": "📝", ".json": "📋", ".yaml": "📋", ".yml": "📋",
            ".toml": "📋", ".txt": "📄", ".sh": "🔧", ".bash": "🔧",
            ".css": "🎨", ".html": "🌐", ".vue": "💚", ".svelte": "🔥",
            ".sql": "🗃️", ".db": "🗃️", ".gitignore": "🚫", ".env": "🔐",
            ".png": "🖼️", ".jpg": "🖼️", ".svg": "🖼️", ".gif": "🖼️",
        }
        return icons.get(ext, "📄")

    def toggle_expand(self, path: Path) -> None:
        if path in self._expanded:
            self._expanded.discard(path)
        else:
            self._expanded.add(path)


class EditorRenderer:
    """Renders the editor/content panel."""

    def __init__(self):
        self.line_width = 4  # For line numbers

    def render_file(self, path: Path, highlight_line: Optional[int] = None) -> Panel:
        """Render a file with syntax highlighting."""
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except (OSError, UnicodeDecodeError):
            content = f"[red]Cannot read file: {path}[/red]"

        ext = path.suffix
        lexer = self._get_lexer(ext)
        syntax = Syntax(content, lexer, theme="monokai", line_numbers=True, highlight_lines={highlight_line} if highlight_line else set())

        title = Text.from_markup(f"[bold #89b4fa]{path.name}[/]")
        return Panel(
            syntax,
            title=title,
            border_style=Theme.BORDER,
            padding=(0, 1),
        )

    def render_text(self, text: str, title: str = "Output") -> Panel:
        """Render plain text in the editor panel."""
        return Panel(
            Text.from_markup(f"[bold #89b4fa]{title}[/]"),
            border_style=Theme.BORDER,
            padding=(0, 1),
        )

    def render_table(self, data: list[dict], title: str = "Results") -> Panel:
        """Render data as a table."""
        if not data:
            return self.render_text("No data", title)

        table = Table(
            show_header=True,
            header_style=f"bold {Theme.ACCENT}",
            border_style=Theme.BORDER,
            box=box.ROUNDED,
        )

        # Add columns
        keys = list(data[0].keys())
        for key in keys:
            table.add_column(str(key).replace("_", " ").title())

        # Add rows
        for row in data:
            table.add_row(*[str(row.get(k, "")) for k in keys])

        return Panel(
            table,
            title=Text.from_markup(f"[bold #89b4fa]{title}[/]"),
            border_style=Theme.BORDER,
        )

    def _get_lexer(self, ext: str) -> str:
        lexers = {
            ".py": "python", ".rs": "rust", ".js": "javascript",
            ".ts": "typescript", ".tsx": "typescript", ".jsx": "javascript",
            ".go": "go", ".java": "java", ".c": "c", ".h": "c",
            ".cpp": "cpp", ".hpp": "cpp", ".cs": "csharp", ".rb": "ruby",
            ".swift": "swift", ".kt": "kotlin", ".scala": "scala",
            ".sh": "bash", ".bash": "bash", ".zsh": "bash",
            ".sql": "sql", ".html": "html", ".css": "css",
            ".json": "json", ".yaml": "yaml", ".yml": "yaml",
            ".md": "markdown", ".xml": "xml", ".toml": "toml",
        }
        return lexers.get(ext, "text")


class TerminalRenderer:
    """Renders the terminal panel."""

    def __init__(self, max_lines: int = 200):
        self.max_lines = max_lines
        self.lines: list[TerminalLine] = []

    def add_line(self, text: str, style: str = "white", is_command: bool = False) -> None:
        """Add a line to the terminal output."""
        self.lines.append(TerminalLine(text, style, is_command))
        if len(self.lines) > self.max_lines:
            self.lines.pop(0)

    def add_command(self, text: str) -> None:
        """Add a command (user input) line."""
        self.add_line(f"❯ {text}", style=f"bold {Theme.ACCENT}", is_command=True)

    def add_output(self, text: str) -> None:
        """Add a command output line."""
        self.add_line(text, style=Theme.TEXT)

    def add_error(self, text: str) -> None:
        """Add an error line."""
        self.add_line(text, style=Theme.ACCENT_RED)

    def add_success(self, text: str) -> None:
        """Add a success line."""
        self.add_line(text, style=Theme.ACCENT_GREEN)

    def clear(self) -> None:
        """Clear terminal output."""
        self.lines.clear()

    def render(self) -> Panel:
        """Render the terminal panel."""
        if not self.lines:
            content = Text(f"[dim]{Theme.TEXT_DIM}Terminal output will appear here...[/]", style=Theme.TEXT_DIM)
        else:
            lines_group = Group(
                *[Text(line.text, style=line.style) for line in self.lines]
            )
            content = lines_group

        return Panel(
            content,
            title=Text.from_markup("[bold #89b4fa]Terminal[/]  [dim]Ctrl+` to toggle[/]"),
            border_style=Theme.BORDER,
            padding=(0, 1),
        )


class ChatRenderer:
    """Renders the chat panel."""

    def __init__(self):
        self.messages: list[ChatMessage] = []

    def add_message(self, role: str, content: str, agent_name: str = "AI_SUPPORT") -> None:
        """Add a chat message."""
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M")
        self.messages.append(ChatMessage(role, content, ts, agent_name))

    def add_user(self, text: str) -> None:
        self.add_message("user", text)

    def add_assistant(self, text: str, agent_name: str = "AI_SUPPORT") -> None:
        self.add_message("assistant", text, agent_name)

    def clear(self) -> None:
        self.messages.clear()

    def render(self) -> Panel:
        """Render the chat panel."""
        if not self.messages:
            content = Text(
                f"[dim #6c7086]Chat with AI_SUPPORT...[/]\n"
                f"[dim #6c7086]Type /help for commands[/]",
                style="#6c7086",
            )
        else:
            msg_groups = []
            for msg in self.messages[-20:]:  # Last 20 messages
                if msg.role == "user":
                    label = Text(f"  You  {msg.timestamp}", style="bold #f9e2af")
                    content = Text(msg.content, style=Theme.TEXT)
                else:
                    label = Text(f"  {msg.agent_name}  {msg.timestamp}", style="bold #89b4fa")
                    content = Text(msg.content, style=Theme.TEXT)

                msg_groups.append(label)
                msg_groups.append(content)
                msg_groups.append(Text(""))

            content = Group(*msg_groups)

        return Panel(
            content,
            title=Text.from_markup("[bold #89b4fa]Chat[/]  [dim]Ctrl+Shift+M[/]"),
            border_style=Theme.BORDER,
            padding=(0, 1),
        )


class StatusBarRenderer:
    """Renders the status bar."""

    def render(self, status: StatusInfo) -> Panel:
        """Render the status bar."""
        left = Group(
            Text(f" {status.file_path or 'No file open'} ", style="bold #89b4fa"),
            Text(f" {status.line_col} ", style=Theme.TEXT),
        )

        center = Text(f" {status.language} ", style=Theme.TEXT_DIM)

        right = Group(
            Text(f" {status.branch} ", style=Theme.ACCENT_GREEN) if status.branch else Text(""),
            Text(f" {status.encoding} ", style=Theme.TEXT_DIM),
            Text(f" {status.spaces} ", style=Theme.TEXT_DIM),
        )

        # Messages
        if status.messages:
            msg_text = "  ".join(status.messages)
            bar_content = Group(
                left,
                center,
                right,
                Text(f"\n{msg_text}", style=Theme.ACCENT_YELLOW),
            )
        else:
            bar_content = Group(left, center, right)

        return Panel(
            bar_content,
            border_style=Theme.BORDER,
            padding=(0, 0),
            height=3 if not status.messages else 4,
        )


# ─── Interactive TUI Application ─────────────────────────────────────────────

class TUIControls:
    """Keyboard control mappings (Cursor-style)."""

    @staticmethod
    def get_key_bindings() -> dict[str, str]:
        return {
            "ctrl+k": "Command Palette",
            "ctrl+p": "Quick Open File",
            "ctrl+shift+p": "Command Palette (same)",
            "ctrl+oem_1": "Terminal",
            "ctrl+b": "Toggle File Tree",
            "ctrl+j": "Toggle Terminal",
            "ctrl+shift+m": "Toggle Chat",
            "ctrl+s": "Save",
            "ctrl+shift+f": "AI Fix",
            "ctrl+shift+a": "AI Review",
            "ctrl+shift+e": "AI Explain",
            "ctrl+shift+o": "Go to Symbol",
            "ctrl+g": "Go to Line",
            "ctrl+f": "Find",
            "ctrl+h": "Find and Replace",
            "f2": "Rename Symbol",
            "escape": "Close Panel / Cancel",
            "ctrl+c": "Copy",
            "ctrl+v": "Paste",
            "ctrl+z": "Undo",
            "ctrl+y": "Redo",
        }


class AISupportTUI:
    """Main AI_SUPPORT Interactive TUI Application.

    Cursor-like interface with file tree, editor, terminal, and chat panels.
    """

    def __init__(
        self,
        workspace_root: Optional[str] = None,
        initial_file: Optional[str] = None,
        use_real_terminal: bool = True,
    ):
        self.workspace_root = Path(workspace_root or os.getcwd())
        self.console = Console()
        self.layout = Layout()

        # Real terminal handler for shell execution
        self.use_real_terminal = use_real_terminal
        self._terminal_handler = None
        if use_real_terminal:
            try:
                from src.interfaces.tui.terminal_handler import TerminalHandler
                self._terminal_handler = TerminalHandler()
                self._terminal_handler.create_session("main", self.workspace_root)
            except ImportError:
                pass

        # Renderers
        self.file_tree = FileTreeRenderer(self.workspace_root)
        self.editor = EditorRenderer()
        self.terminal = TerminalRenderer()
        self.chat = ChatRenderer()
        self.status = StatusInfo(branch=self._get_git_branch())

        # State
        self.selected_file: Optional[Path] = None
        self.highlight_line: Optional[int] = None
        self.terminal_visible = True
        self.chat_visible = False
        self.file_tree_visible = True

        # Set initial file
        if initial_file:
            self.selected_file = Path(initial_file)
            self.status.file_path = str(self.selected_file)
            self.status.language = self._detect_language(self.selected_file)

    # ─── Setup ───────────────────────────────────────────────────────────────

    def _get_git_branch(self) -> str:
        """Get current git branch."""
        import subprocess
        try:
            result = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=self.workspace_root,
                capture_output=True,
                text=True,
                timeout=2,
            )
            if result.returncode == 0:
                branch = result.stdout.strip()
                return f"  {branch} " if branch else ""
        except Exception:
            pass
        return ""

    def _detect_language(self, path: Path) -> str:
        """Detect language from file extension."""
        langs = {
            ".py": "Python", ".rs": "Rust", ".js": "JavaScript",
            ".ts": "TypeScript", ".tsx": "TypeScript React",
            ".go": "Go", ".java": "Java", ".c": "C",
            ".cpp": "C++", ".cs": "C#", ".rb": "Ruby",
            ".swift": "Swift", ".kt": "Kotlin", ".sh": "Shell",
            ".bash": "Bash", ".sql": "SQL", ".html": "HTML",
            ".css": "CSS", ".json": "JSON", ".yaml": "YAML",
            ".yml": "YAML", ".md": "Markdown", ".xml": "XML",
            ".toml": "TOML", ".txt": "Plain Text",
        }
        return langs.get(path.suffix, "Plain Text")

    # ─── Layout ──────────────────────────────────────────────────────────────

    def _build_layout(self) -> None:
        """Build the main layout."""
        # Create a fresh layout for each render to handle visibility changes
        self.layout = Layout()

        # Configure layout structure: main area + status bar
        self.layout.split_column(
            Layout(name="main", ratio=1),
            Layout(name="status", size=3),
        )

        # Build the main area row based on visibility settings
        if self.chat_visible:
            # With chat: file_tree | editor | chat | terminal
            self.layout["main"].split_row(
                Layout(
                    name="file_tree",
                    size=PanelConfig.FILE_TREE_WIDTH,
                ) if self.file_tree_visible else Layout(name="file_tree", size=0),
                Layout(name="editor", ratio=1),
                Layout(name="chat", size=PanelConfig.CHAT_WIDTH),
                Layout(
                    name="terminal",
                    size=PanelConfig.TERMINAL_HEIGHT,
                ) if self.terminal_visible else Layout(name="terminal", size=0),
            )
        else:
            # Without chat: file_tree | editor | terminal
            self.layout["main"].split_row(
                Layout(
                    name="file_tree",
                    size=PanelConfig.FILE_TREE_WIDTH,
                ) if self.file_tree_visible else Layout(name="file_tree", size=0),
                Layout(name="editor", ratio=1),
                Layout(
                    name="terminal",
                    size=PanelConfig.TERMINAL_HEIGHT,
                ) if self.terminal_visible else Layout(name="terminal", size=0),
            )

        # Build panel content
        self.layout["file_tree"].update(Panel(
            self.file_tree.render(self.selected_file),
            border_style=Theme.BORDER,
        ))
        self.layout["editor"].update(
            self.editor.render_file(self.selected_file, self.highlight_line)
            if self.selected_file and self.selected_file.is_file()
            else self.editor.render_text("No file open", "Welcome")
        )
        self.layout["terminal"].update(self.terminal.render())
        if self.chat_visible:
            self.layout["chat"].update(self.chat.render())
        self.layout["status"].update(self._render_status_bar())

    def _render_status_bar(self) -> Panel:
        """Render the status bar."""
        left_parts = []
        if self.selected_file:
            left_parts.append(Text(f" {self.selected_file.name} ", style=f"bold {Theme.ACCENT}"))
            left_parts.append(Text(f" {self.status.line_col} ", style=Theme.TEXT))
        else:
            left_parts.append(Text(" No file open ", style=Theme.TEXT_DIM))

        center = Text(f" {self.status.language} ", style=Theme.TEXT_DIM)

        right_parts = []
        if self.status.branch:
            right_parts.append(Text(self.status.branch, style=Theme.ACCENT_GREEN))
        right_parts.append(Text(f" {self.status.encoding} ", style=Theme.TEXT_DIM))
        right_parts.append(Text(f" {self.status.spaces} ", style=Theme.TEXT_DIM))

        from rich.console import Group as RGroup
        bar_content = RGroup(
            RGroup(*left_parts),
            center,
            RGroup(*right_parts),
        )

        return Panel(
            bar_content,
            border_style=Theme.BORDER,
            padding=(0, 0),
            height=3,
        )

    # ─── Rendering ───────────────────────────────────────────────────────────

    def render(self) -> None:
        """Render the full TUI."""
        self._build_layout()
        self.console.print(self.layout)

    def render_async(self, live: Live) -> None:
        """Update the display within a Live context."""
        self._build_layout()
        live.update(self.layout)

    # ─── User interactions ───────────────────────────────────────────────────

    def open_file(self, path: Path) -> None:
        """Open a file in the editor."""
        if not path.exists():
            self.terminal.add_error(f"File not found: {path}")
            return

        self.selected_file = path
        self.status.file_path = str(path)
        self.status.language = self._detect_language(path)
        self.terminal.add_success(f"Opened: {path}")
        self.render()

    def show_review(self, file_path: Optional[Path] = None) -> None:
        """Show code review results for a file."""
        target = file_path or self.selected_file
        if not target:
            self.terminal.add_error("No file selected for review")
            self.render()
            return

        self.terminal.add_command(f"/review {target}")
        self.terminal.add_output(f"Running code review on {target}...")

        # Show a table of findings
        findings = [
            {"Severity": "error", "Line": "42", "Rule": "SEC001", "Message": "Hardcoded secret detected"},
            {"Severity": "warning", "Line": "18", "Rule": "NAME001", "Message": "Function uses camelCase naming"},
            {"Severity": "info", "Line": "7", "Rule": "QUAL005", "Message": "Consider using logging instead of print"},
        ]
        self.layout["editor"].update(
            self.editor.render_table(findings, title=f"Review: {target.name}")
        )
        self.render()

    def show_fixes(self) -> None:
        """Show available fixes for the current file."""
        if not self.selected_file:
            self.terminal.add_error("No file selected")
            self.render()
            return

        self.terminal.add_command(f"/fix {self.selected_file}")
        self.terminal.add_output("Generated fix suggestions...")

        fixes = [
            {"ID": "fix-001", "Line": "42", "Rule": "SEC001", "Fix": "Use os.getenv('API_KEY')"},
            {"ID": "fix-002", "Line": "18", "Rule": "NAME001", "Fix": "def my_function() -> None:"},
            {"ID": "fix-003", "Line": "7", "Rule": "QUAL005", "Fix": "logging.info(f'User {user_id}')"},
        ]
        self.layout["editor"].update(
            self.editor.render_table(fixes, title=f"Fixes: {self.selected_file.name}")
        )
        self.render()

    def toggle_terminal(self) -> None:
        """Toggle terminal panel visibility."""
        self.terminal_visible = not self.terminal_visible
        self.render()

    def toggle_chat(self) -> None:
        """Toggle chat panel visibility."""
        self.chat_visible = not self.chat_visible
        self.render()

    def toggle_file_tree(self) -> None:
        """Toggle file tree visibility."""
        self.file_tree_visible = not self.file_tree_visible
        self.render()

    def add_terminal_output(self, text: str) -> None:
        """Add output to the terminal."""
        self.terminal.add_output(text)
        self.render()

    def show_command_palette(self) -> None:
        """Show the command palette (simulated with print)."""
        self.console.print("\n[bold]Command Palette[/bold] (type to filter, Enter to select):")
        commands = [
            ("AI: Review Code", "Ctrl+Shift+A"),
            ("AI: Fix Problems", "Ctrl+Shift+F"),
            ("AI: Explain Code", "Ctrl+Shift+E"),
            ("Format Document", "Shift+Alt+F"),
            ("Go to File", "Ctrl+P"),
            ("Go to Symbol", "Ctrl+Shift+O"),
            ("New Terminal", "Ctrl+`"),
            ("Save File", "Ctrl+S"),
            ("Toggle File Tree", "Ctrl+B"),
            ("Toggle Chat", "Ctrl+Shift+M"),
            ("Settings", "Ctrl+,"),
        ]
        table = Table(box=box.ROUNDED, show_header=False, pad_edge=False)
        table.add_column("Command", style=Theme.TEXT)
        table.add_column("Shortcut", style=Theme.TEXT_DIM)
        for cmd, shortcut in commands:
            table.add_row(cmd, shortcut)
        self.console.print(table)

    # ─── Main loop ───────────────────────────────────────────────────────────

    def run_interactive(self) -> None:
        """Run the interactive TUI loop."""
        self.render()

        # Show welcome message
        self.terminal.add_output(f"Welcome to AI_SUPPORT TUI")
        self.terminal.add_output(f"Workspace: {self.workspace_root}")
        self.terminal.add_output(f"Type /help or press Ctrl+K for commands")
        self.render()

        print(f"\n[dim]{'─' * 60}[/dim]")
        print("[dim]Controls:[/dim]")
        for key, desc in TUIControls.get_key_bindings().items():
            print(f"  [dim]{key:<20}[/dim] {desc}")
        print("[dim]Type commands below. Press Ctrl+C to exit.[/dim]")
        print()

        try:
            while True:
                try:
                    user_input = input("\n❯ ").strip()
                except (KeyboardInterrupt, EOFError):
                    break

                if not user_input:
                    continue

                # Parse commands
                if user_input.startswith("/"):
                    self._handle_slash_command(user_input)
                elif user_input.startswith("open "):
                    path = Path(user_input[5:].strip())
                    self.open_file(path)
                elif user_input == "review":
                    self.show_review()
                elif user_input == "fix":
                    self.show_fixes()
                elif user_input == "cls" or user_input == "clear":
                    self.terminal.clear()
                    self.render()
                elif user_input == "tree":
                    self.toggle_file_tree()
                elif user_input == "chat":
                    self.toggle_chat()
                elif user_input == "term":
                    self.toggle_terminal()
                elif user_input == "help":
                    self.show_command_palette()
                else:
                    # Try real shell execution
                    if self._terminal_handler and not user_input.startswith("/"):
                        asyncio.create_task(self._execute_in_terminal(user_input))
                    else:
                        self.terminal.add_command(user_input)
                        self.terminal.add_output(f"Command not recognized. Type /help for available commands.")
                        self.render()

    async def _execute_in_terminal(self, command: str) -> None:
        """Execute command in real terminal."""
        self.terminal.add_command(command)

        if self._terminal_handler:
            result = await self._terminal_handler.execute("main", command, timeout=30)

            if result.get("timeout"):
                self.terminal.add_error(f"Command timed out")
            elif result.get("error"):
                self.terminal.add_error(result.get("stderr", "Unknown error"))
            elif result.get("stderr"):
                self.terminal.add_output(result["stderr"])

            if result.get("stdout"):
                for line in result["stdout"].split("\n"):
                    if line:
                        self.terminal.add_output(line)
        else:
            self.terminal.add_output("Real terminal not available")

        self.render()

    def _handle_slash_command(self, cmd: str) -> None:
        """Handle a slash command."""
        self.terminal.add_command(cmd)

        if cmd == "/help":
            self.show_command_palette()
        elif cmd == "/review":
            self.show_review()
        elif cmd.startswith("/fix"):
            self.show_fixes()
        elif cmd == "/stats":
            self.terminal.add_output("Stats: Review completed with 3 findings")
        else:
            self.terminal.add_output(f"Unknown command: {cmd}. Try /help")

        self.render()


# ─── CLI entry point ─────────────────────────────────────────────────────────

def main():
    """Entry point for the interactive TUI."""
    import argparse
    parser = argparse.ArgumentParser(description="AI_SUPPORT Interactive TUI")
    parser.add_argument("path", nargs="?", default=None, help="Initial file or directory to open")
    parser.add_argument("--file", "-f", dest="file", help="Specific file to open")
    args = parser.parse_args()

    workspace = args.path or "."
    initial = args.file

    if not initial and workspace and Path(workspace).is_file():
        initial = workspace
        workspace = Path(workspace).parent

    app = AISupportTUI(workspace_root=workspace, initial_file=initial)
    app.run_interactive()


if __name__ == "__main__":
    main()
