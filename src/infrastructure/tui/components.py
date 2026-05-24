"""TUI components for Agentic-AI CLI.

Inspired by oh-my-pi's TUI:
- Rich formatting
- Tool cards
- Streaming responses
- Markdown rendering
- Responsive layout
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Color:
    """ANSI color codes."""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    ITALIC = "\033[3m"
    
    # Foreground colors
    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    
    # Bright foreground
    BRIGHT_BLACK = "\033[90m"
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_WHITE = "\033[97m"
    
    # Background colors
    BG_BLACK = "\033[40m"
    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_YELLOW = "\033[43m"
    BG_BLUE = "\033[44m"
    BG_MAGENTA = "\033[45m"
    BG_CYAN = "\033[46m"
    BG_WHITE = "\033[47m"


class Theme:
    """Default theme colors."""
    PRIMARY = Color.CYAN
    SECONDARY = Color.BLUE
    SUCCESS = Color.GREEN
    WARNING = Color.YELLOW
    ERROR = Color.RED
    INFO = Color.BRIGHT_BLACK
    DIM = Color.DIM
    
    USER_MESSAGE = Color.BRIGHT_CYAN
    ASSISTANT_MESSAGE = Color.WHITE
    SYSTEM_MESSAGE = Color.DIM
    
    TOOL_HEADER = Color.YELLOW
    TOOL_SUCCESS = Color.GREEN
    TOOL_ERROR = Color.RED
    
    CODE_BLOCK = Color.BRIGHT_BLACK
    LINK = Color.BLUE


@dataclass
class Style:
    """Text styling."""
    bold: bool = False
    italic: bool = False
    color: str = ""
    bg_color: str = ""
    
    def apply(self, text: str) -> str:
        result = text
        if self.bold:
            result = f"{Color.BOLD}{result}"
        if self.italic:
            result = f"{Color.ITALIC}{result}"
        if self.color:
            result = f"{self.color}{result}"
        if self.bg_color:
            result = f"{self.bg_color}{result}"
        if any([self.bold, self.italic, self.color, self.bg_color]):
            result = f"{result}{Color.RESET}"
        return result


class Align(Enum):
    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"


@dataclass
class BoxStyle:
    """Box drawing style."""
    top_left: str = "┌"
    top_right: str = "┐"
    bottom_left: str = "└"
    bottom_right: str = "┘"
    horizontal: str = "─"
    vertical: str = "│"
    border_color: str = ""
    
    @classmethod
    def rounded(cls, color: str = ""):
        return cls("╭", "╮", "╰", "╯", "─", "│", color)
    
    @classmethod
    def double(cls, color: str = ""):
        return cls("╔", "╗", "╚", "╝", "═", "║", color)
    
    @classmethod
    def simple(cls, color: str = ""):
        return cls("+", "+", "+", "-", "|", color)


def get_terminal_width() -> int:
    """Get terminal width."""
    try:
        import shutil
        return shutil.get_terminal_size().columns
    except:
        return 80


def get_terminal_height() -> int:
    """Get terminal height."""
    try:
        import shutil
        return shutil.get_terminal_size().lines
    except:
        return 24


def render_box(content: str, style: BoxStyle | None = None, width: int | None = None) -> str:
    """Render content in a box."""
    if style is None:
        style = BoxStyle()
    
    if width is None:
        width = get_terminal_width()
    
    lines = content.split("\n")
    max_len = max(len(l) for l in lines)
    box_width = min(width - 4, max(max_len + 4, 10))
    
    result = []
    
    # Top border
    border = style.horizontal * (box_width - 2)
    if style.border_color:
        result.append(f"{style.border_color}{style.top_left}{border}{style.top_right}{Color.RESET}")
    else:
        result.append(f"{style.top_left}{border}{style.top_right}")
    
    # Content
    for line in lines:
        padding = box_width - len(line) - 4
        if padding < 0:
            padding = 0
        if style.border_color:
            result.append(f"{style.border_color}{style.vertical} {Color.RESET}{line}{' ' * padding}{style.border_color} {style.vertical}{Color.RESET}")
        else:
            result.append(f"{style.vertical} {line}{' ' * padding} {style.vertical}")
    
    # Bottom border
    if style.border_color:
        result.append(f"{style.border_color}{style.bottom_left}{border}{style.bottom_right}{Color.RESET}")
    else:
        result.append(f"{style.bottom_left}{border}{style.bottom_right}")
    
    return "\n".join(result)


@dataclass
class ToolCard:
    """A tool execution card."""
    name: str
    arguments: dict[str, Any] | None = None
    result: str = ""
    success: bool = True
    error: str | None = None
    duration_ms: float = 0
    collapsed: bool = False
    
    def render(self) -> str:
        """Render the tool card."""
        lines = []
        
        # Header
        status_icon = "✓" if self.success else "✗"
        status_color = Theme.TOOL_SUCCESS if self.success else Theme.TOOL_ERROR
        
        args_str = ""
        if self.arguments:
            if len(str(self.arguments)) < 100:
                args_str = f" {self.arguments}"
            else:
                args_str = f" ({len(str(self.arguments))} chars)"
        
        header = f"[Tool: {self.name}{args_str}] {status_color}{status_icon}{Color.RESET}"
        if self.duration_ms > 0:
            header += f" {Theme.DIM}({self.duration_ms:.0f}ms){Color.RESET}"
        
        lines.append(header)
        
        # Result (if not collapsed)
        if not self.collapsed:
            if self.error:
                lines.append(f"  {Theme.TOOL_ERROR}{self.error}{Color.RESET}")
            elif self.result:
                # Truncate long results
                result_lines = self.result.split("\n")
                if len(result_lines) > 10:
                    result_lines = result_lines[:10] + [f"... ({len(result_lines) - 10} more lines)"]
                
                for line in result_lines:
                    if len(line) > get_terminal_width() - 6:
                        line = line[:get_terminal_width() - 10] + "..."
                    lines.append(f"  {Theme.INFO}{line}{Color.RESET}")
        
        return "\n".join(lines)


@dataclass
class MessageCard:
    """A message card."""
    role: str  # "user", "assistant", "system"
    content: str
    tool_calls: list[ToolCard] = field(default_factory=list)
    
    def render(self) -> str:
        """Render the message card."""
        lines = []
        
        # Role indicator
        if self.role == "user":
            role_color = Theme.USER_MESSAGE
            role_text = "You"
        elif self.role == "assistant":
            role_color = Theme.ASSISTANT_MESSAGE
            role_text = "Agentic-AI"
        else:
            role_color = Theme.SYSTEM_MESSAGE
            role_text = "System"
        
        lines.append(f"{role_color}{Color.BOLD}{role_text}:{Color.RESET}")
        lines.append("")
        
        # Content (rendered as markdown)
        content = self._render_markdown(self.content)
        for line in content.split("\n"):
            lines.append(f"  {line}")
        
        lines.append("")
        
        # Tool calls
        for tc in self.tool_calls:
            lines.append(tc.render())
        
        return "\n".join(lines)
    
    def _render_markdown(self, text: str) -> str:
        """Simple markdown rendering."""
        # Code blocks
        text = re.sub(r"```(\w+)?\n(.*?)```", self._render_code_block, text, flags=re.DOTALL)
        
        # Inline code
        text = re.sub(r"`([^`]+)`", lambda m: f"{Theme.CODE_BLOCK}{m.group(1)}{Color.RESET}", text)
        
        # Bold
        text = re.sub(r"\*\*(.+?)\*\*", lambda m: f"{Color.BOLD}{m.group(1)}{Color.RESET}", text)
        
        # Italic
        text = re.sub(r"\*(.+?)\*", lambda m: f"{Color.ITALIC}{m.group(1)}{Color.RESET}", text)
        
        # Links
        text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", lambda m: f"{Theme.LINK}{m.group(1)}{Color.RESET} ({m.group(2)})", text)
        
        return text
    
    def _render_code_block(self, m) -> str:
        """Render a code block."""
        lang = m.group(1) or ""
        code = m.group(2)
        
        lines = code.split("\n")
        max_len = max(len(l) for l in lines)
        width = min(get_terminal_width() - 4, max_len + 4)
        
        result = []
        result.append(f"{Theme.CODE_BLOCK}┌{'─' * (width - 2)}┐{Color.RESET}")
        
        for line in lines:
            padding = width - len(line) - 4
            result.append(f"{Theme.CODE_BLOCK}│{Color.RESET} {Theme.CODE_BLOCK}{line}{Color.RESET}{' ' * padding}{Theme.CODE_BLOCK}│{Color.RESET}")
        
        result.append(f"{Theme.CODE_BLOCK}└{'─' * (width - 2)}┘{Color.RESET}")
        
        if lang:
            result.append(f"{Theme.DIM}  [{lang}]{Color.RESET}")
        
        return "\n".join(result)


@dataclass
class ProgressIndicator:
    """Animated progress indicator."""
    message: str = ""
    frames: list[str] = field(default_factory=lambda: ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"])
    interval_ms: int = 80
    
    def __post_init__(self):
        self._index = 0
        self._done = False
    
    def render(self) -> str:
        """Render current frame."""
        frame = self.frames[self._index % len(self.frames)]
        return f"{Theme.PRIMARY}{frame}{Color.RESET} {self.message}"
    
    def step(self) -> bool:
        """Advance to next frame."""
        self._index += 1
        return not self._done
    
    def done(self) -> None:
        """Mark as done."""
        self._done = True
    
    @property
    def is_done(self) -> bool:
        return self._done


class Spinner:
    """Simple spinner context manager."""
    
    def __init__(self, message: str = "Working"):
        self.message = message
        self.indicator = ProgressIndicator(message)
        self._task = None
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        self.indicator.done()
        print(f"\r{' ' * (len(self.indicator.render()) + 2)}\r", end="")
    
    def render(self) -> str:
        return self.indicator.render()


class Table:
    """Simple table renderer."""
    
    def __init__(self, headers: list[str]):
        self.headers = headers
        self.rows: list[list[str]] = []
    
    def add_row(self, row: list[str]) -> None:
        self.rows.append(row)
    
    def render(self) -> str:
        """Render the table."""
        if not self.rows:
            return ""
        
        # Calculate column widths
        widths = [len(h) for h in self.headers]
        for row in self.rows:
            for i, cell in enumerate(row):
                widths[i] = max(widths[i], len(str(cell)))
        
        # Render
        lines = []
        
        # Header
        header_parts = []
        for i, h in enumerate(self.headers):
            header_parts.append(f"{Color.BOLD}{h:>{widths[i]}}{Color.RESET}")
        lines.append("  " + " | ".join(header_parts))
        
        # Separator
        sep_parts = []
        for w in widths:
            sep_parts.append("─" * w)
        lines.append("  " + "-+-".join(sep_parts))
        
        # Rows
        for row in self.rows:
            row_parts = []
            for i, cell in enumerate(row):
                row_parts.append(f"{str(cell):>{widths[i]}}")
            lines.append("  " + " | ".join(row_parts))
        
        return "\n".join(lines)


class StatusBar:
    """Status bar at the bottom of terminal."""
    
    def __init__(self):
        self.left: str = ""
        self.center: str = ""
        self.right: str = ""
    
    def set_left(self, text: str) -> None:
        self.left = text
    
    def set_center(self, text: str) -> None:
        self.center = text
    
    def set_right(self, text: str) -> None:
        self.right = text
    
    def render(self) -> str:
        """Render the status bar."""
        width = get_terminal_width()
        
        # Pad sections
        left = self.left[:width // 3]
        right = self.right[-width // 3:] if self.right else ""
        center = self.center
        
        # Truncate center if needed
        remaining = width - len(left) - len(right) - 4
        if remaining > 0 and len(center) > remaining:
            center = center[:remaining - 3] + "..."
        
        return f"{Color.BG_BLACK}{Theme.PRIMARY}{left}{Color.RESET} {center} {Color.BG_BLACK}{Theme.PRIMARY}{right:>{len(right) if right else width // 3}}{Color.RESET}"


# Convenience functions
def print_header(text: str, width: int | None = None) -> None:
    """Print a centered header."""
    if width is None:
        width = get_terminal_width()
    
    text = f" {text} "
    padding = (width - len(text)) // 2
    line = "=" * width
    print(f"\n{Theme.PRIMARY}{line}{Color.RESET}")
    print(f"{Theme.PRIMARY}{' ' * padding}{Color.BOLD}{text}{Color.RESET}")
    print(f"{Theme.PRIMARY}{line}{Color.RESET}\n")


def print_success(text: str) -> None:
    """Print success message."""
    print(f"{Theme.SUCCESS}✓ {text}{Color.RESET}")


def print_error(text: str) -> None:
    """Print error message."""
    print(f"{Theme.ERROR}✗ {text}{Color.RESET}")


def print_warning(text: str) -> None:
    """Print warning message."""
    print(f"{Theme.WARNING}⚠ {text}{Color.RESET}")


def print_info(text: str) -> None:
    """Print info message."""
    print(f"{Theme.INFO}ℹ {text}{Color.RESET}")


def clear_line() -> None:
    """Clear current line."""
    print("\r" + " " * get_terminal_width() + "\r", end="")


def move_cursor_up(lines: int = 1) -> None:
    """Move cursor up."""
    print(f"\033[{lines}A", end="")


def move_cursor_down(lines: int = 1) -> None:
    """Move cursor down."""
    print(f"\033[{lines}B", end="")


def save_cursor() -> None:
    """Save cursor position."""
    print("\033[s", end="")


def restore_cursor() -> None:
    """Restore cursor position."""
    print("\033[u", end="")
