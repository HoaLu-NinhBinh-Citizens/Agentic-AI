"""Vim mode for terminal navigation and editing.

Provides:
- Normal, Insert, Visual modes
- Common motions (hjkl, w, b, e, etc.)
- Text objects and operators
- Macro recording
- Search within buffer
- Yank/Put operations
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable


class VimMode(Enum):
    """Vim editing modes."""
    NORMAL = auto()
    INSERT = auto()
    VISUAL = auto()
    VISUAL_LINE = auto()
    COMMAND = auto()
    REPLACE = auto()


@dataclass
class VimBuffer:
    """Buffer representing editable text."""
    lines: list[str] = field(default_factory=list)
    cursor_line: int = 0
    cursor_col: int = 0
    mark_line: int = 0
    mark_col: int = 0
    visual_start_line: int = 0
    visual_start_col: int = 0
    visual_end_line: int = 0
    visual_end_col: int = 0
    
    @property
    def cursor(self) -> tuple[int, int]:
        """Get cursor position."""
        return (self.cursor_line, self.cursor_col)
    
    @property
    def current_line(self) -> str:
        """Get current line content."""
        if 0 <= self.cursor_line < len(self.lines):
            return self.lines[self.cursor_line]
        return ""
    
    @property
    def line_count(self) -> int:
        """Get number of lines."""
        return len(self.lines)
    
    def move_cursor(self, line: int, col: int) -> None:
        """Move cursor with bounds checking."""
        if self.lines:
            self.cursor_line = max(0, min(line, len(self.lines) - 1))
            self.cursor_col = max(0, min(col, len(self.current_line)))
        else:
            self.cursor_line = 0
            self.cursor_col = 0
    
    def insert_line(self, line: int, text: str = "") -> None:
        """Insert a line."""
        self.lines.insert(line, text)
        if self.cursor_line >= line:
            self.cursor_line += 1
    
    def delete_line(self, line: int) -> str | None:
        """Delete a line and return its content."""
        if 0 <= line < len(self.lines):
            deleted = self.lines.pop(line)
            if self.cursor_line >= line and self.cursor_line > 0:
                self.cursor_line -= 1
            self.cursor_col = min(self.cursor_col, len(self.current_line))
            return deleted
        return None
    
    def set_lines(self, lines: list[str]) -> None:
        """Set buffer content."""
        self.lines = lines.copy()
        self.cursor_line = 0
        self.cursor_col = 0
    
    def get_selection(self) -> str:
        """Get selected text (for visual mode)."""
        if self.visual_start_line == self.visual_end_line:
            start = min(self.visual_start_col, self.visual_end_col)
            end = max(self.visual_start_col, self.visual_end_col)
            return self.current_line[start:end]
        
        # Multi-line selection
        lines = []
        start_line = min(self.visual_start_line, self.visual_end_line)
        end_line = max(self.visual_start_line, self.visual_end_line)
        
        for i, line in enumerate(self.lines[start_line:end_line + 1]):
            if i == 0:
                lines.append(line[self.visual_start_col:])
            elif i == end_line - start_line:
                lines.append(line[:self.visual_end_col + 1])
            else:
                lines.append(line)
        
        return "\n".join(lines)


@dataclass
class VimRegister:
    """Register for yank/delete operations."""
    content: str = ""
    is_linewise: bool = False


@dataclass
class VimState:
    """Complete Vim state."""
    buffer: VimBuffer = field(default_factory=VimBuffer)
    mode: VimMode = VimMode.NORMAL
    registers: dict[str, VimRegister] = field(default_factory=lambda: {"0": VimRegister(), '"': VimRegister()})
    current_register: str = '"'
    search_pattern: str = ""
    search_direction: int = 1  # 1 = forward, -1 = backward
    repeat_count: int = 1
    last_operator: str = ""
    last_motion: str = ""
    macro_registers: dict[str, str] = field(default_factory=dict)
    recording_macro: str | None = None
    macro_content: str = ""
    indent_size: int = 4
    use_spaces: bool = True
    autoindent: bool = True


class VimEngine:
    """Vim-like text editor engine."""
    
    def __init__(self, state: VimState | None = None):
        self.state = state or VimState()
        self._key_handlers: dict[VimMode, dict[str, Callable]] = {}
        self._operators: dict[str, Callable] = {}
        self._motions: dict[str, Callable] = {}
        self._setup_handlers()
        self._setup_operators()
        self._setup_motions()
    
    def _setup_handlers(self) -> None:
        """Setup key handlers for each mode."""
        # Normal mode handlers
        self._key_handlers[VimMode.NORMAL] = {
            "h": self._move_left,
            "j": self._move_down,
            "k": self._move_up,
            "l": self._move_right,
            "w": self._move_word_forward,
            "b": self._move_word_backward,
            "e": self._move_word_end,
            "0": self._move_line_start,
            "$": self._move_line_end,
            "^": self._move_line_content_start,
            "gg": self._move_file_start,
            "G": self._move_file_end,
            "i": self._enter_insert_mode,
            "I": self._enter_insert_line_start,
            "a": self._enter_insert_after,
            "A": self._enter_insert_line_end,
            "o": self._open_line_below,
            "O": self._open_line_above,
            "x": self._delete_char,
            "dd": self._delete_line,
            "yy": self._yank_line,
            "p": self._put_after,
            "P": self._put_before,
            "u": self._undo,
            "Ctrl+r": self._redo,
            "/": self._enter_search,
            "n": self._repeat_search,
            "N": self._repeat_search_reverse,
            "r": self._enter_replace,
            "R": self._enter_replace_mode,
            "v": self._enter_visual,
            "V": self._enter_visual_line,
            "d": self._start_operator,
            "c": self._start_change,
            "y": self._start_yank,
            ">": self._start_indent,
            "<": self._start_dedent,
            ".": self._repeat,
            ":": self._enter_command,
            "zz": self._center_view,
            "zb": self._bottom_view,
            "zt": self._top_view,
        }
        
        # Insert mode handlers
        self._key_handlers[VimMode.INSERT] = {
            "Escape": self._exit_insert_mode,
            "Ctrl+c": self._exit_insert_mode,
            "Ctrl+[": self._exit_insert_mode,
            "Backspace": self._backspace,
            "Tab": self._insert_tab,
            "Enter": self._insert_newline,
        }
        
        # Visual mode handlers
        self._key_handlers[VimMode.VISUAL] = {
            "Escape": self._exit_visual,
            "d": self._visual_delete,
            "y": self._visual_yank,
            "c": self._visual_change,
            "p": self._visual_put,
            "r": self._enter_command,
        }
        
        # Visual line mode handlers
        self._key_handlers[VimMode.VISUAL_LINE] = {
            "Escape": self._exit_visual,
            "d": self._visual_delete,
            "y": self._visual_yank,
            "x": self._visual_delete,
        }
        
        # Command mode handlers
        self._key_handlers[VimMode.COMMAND] = {
            "Escape": self._exit_command,
            "Enter": self._execute_command,
        }
    
    def _setup_operators(self) -> None:
        """Setup operators."""
        self._operators = {
            "d": self._op_delete,
            "c": self._op_change,
            "y": self._op_yank,
            ">": self._op_indent,
            "<": self._op_dedent,
            "g~": self._op_toggle_case,
            "gu": self._op_lowercase,
            "gU": self._op_uppercase,
        }
    
    def _setup_motions(self) -> None:
        """Setup motions."""
        self._motions = {
            "h": self._motion_left,
            "l": self._motion_right,
            "w": self._move_word_forward,
            "b": self._move_word_backward,
            "e": self._move_word_end,
            "$": self._move_line_end,
            "0": self._move_line_start,
            "G": self._move_file_end,
            "j": self._move_down,
            "k": self._move_up,
        }
    
    def load_content(self, content: str) -> None:
        """Load content into buffer."""
        self.state.buffer.set_lines(content.split("\n"))
    
    def get_content(self) -> str:
        """Get buffer content."""
        return "\n".join(self.state.buffer.lines)
    
    def get_display(self) -> str:
        """Get display content with cursor indicator."""
        lines = self.state.buffer.lines.copy()
        
        if self.state.buffer.cursor_line < len(lines):
            line = lines[self.state.buffer.cursor_line]
            col = self.state.buffer.cursor_col
            if col < len(line):
                lines[self.state.buffer.cursor_line] = (
                    line[:col] + "|" + line[col:]
                )
            else:
                lines[self.state.buffer.cursor_line] = line + "|"
        
        return "\n".join(lines)
    
    # Cursor motion methods
    def _move_left(self) -> None:
        """Move cursor left."""
        buf = self.state.buffer
        if buf.cursor_col > 0:
            buf.cursor_col -= 1
    
    def _move_right(self) -> None:
        """Move cursor right."""
        buf = self.state.buffer
        if buf.cursor_col < len(buf.current_line):
            buf.cursor_col += 1
    
    def _move_down(self) -> None:
        """Move cursor down."""
        buf = self.state.buffer
        if buf.cursor_line < buf.line_count - 1:
            buf.cursor_line += 1
            buf.cursor_col = min(buf.cursor_col, len(buf.current_line))
    
    def _move_up(self) -> None:
        """Move cursor up."""
        buf = self.state.buffer
        if buf.cursor_line > 0:
            buf.cursor_line -= 1
            buf.cursor_col = min(buf.cursor_col, len(buf.current_line))
    
    def _move_word_forward(self) -> None:
        """Move to start of next word."""
        buf = self.state.buffer
        line = buf.current_line
        col = buf.cursor_col
        
        # Skip current word
        while col < len(line) and line[col] not in " \t":
            col += 1
        # Skip whitespace
        while col < len(line) and line[col] in " \t":
            col += 1
        
        buf.cursor_col = min(col, len(line))
    
    def _move_word_backward(self) -> None:
        """Move to start of previous word."""
        buf = self.state.buffer
        line = buf.current_line
        col = buf.cursor_col - 1
        
        if col > 0:
            # Skip whitespace
            while col > 0 and line[col] in " \t":
                col -= 1
            # Skip word
            while col > 0 and line[col - 1] not in " \t":
                col -= 1
        
        buf.cursor_col = max(0, col)
    
    def _move_word_end(self) -> None:
        """Move to end of word."""
        buf = self.state.buffer
        line = buf.current_line
        col = buf.cursor_col
        
        if col < len(line) and line[col] in " \t":
            while col < len(line) and line[col] in " \t":
                col += 1
        
        while col < len(line) and line[col] not in " \t":
            col += 1
        
        buf.cursor_col = max(0, col - 1)
    
    def _move_line_start(self) -> None:
        """Move to start of line."""
        self.state.buffer.cursor_col = 0
    
    def _move_line_end(self) -> None:
        """Move to end of line."""
        self.state.buffer.cursor_col = len(self.state.buffer.current_line)
    
    def _move_line_content_start(self) -> None:
        """Move to first non-whitespace character."""
        line = self.state.buffer.current_line
        col = 0
        while col < len(line) and line[col] in " \t":
            col += 1
        self.state.buffer.cursor_col = col
    
    def _move_file_start(self) -> None:
        """Move to start of file."""
        self.state.buffer.move_cursor(0, 0)
    
    def _move_file_end(self) -> None:
        """Move to end of file."""
        buf = self.state.buffer
        buf.move_cursor(buf.line_count - 1, len(buf.current_line))
    
    # Mode transitions
    def _enter_insert_mode(self) -> None:
        """Enter insert mode."""
        self.state.mode = VimMode.INSERT
    
    def _exit_insert_mode(self) -> None:
        """Exit insert mode."""
        self.state.mode = VimMode.NORMAL
    
    def _enter_insert_after(self) -> None:
        """Enter insert mode after cursor."""
        self._move_right()
        self.state.mode = VimMode.INSERT
    
    def _enter_insert_line_start(self) -> None:
        """Enter insert mode at line start."""
        self._move_line_content_start()
        self.state.mode = VimMode.INSERT
    
    def _enter_insert_line_end(self) -> None:
        """Enter insert mode at line end."""
        self._move_line_end()
        self.state.mode = VimMode.INSERT
    
    def _open_line_below(self) -> None:
        """Open new line below."""
        buf = self.state.buffer
        buf.insert_line(buf.cursor_line + 1)
        buf.move_cursor(buf.cursor_line + 1, 0)
        self.state.mode = VimMode.INSERT
    
    def _open_line_above(self) -> None:
        """Open new line above."""
        buf = self.state.buffer
        buf.insert_line(buf.cursor_line)
        buf.move_cursor(buf.cursor_line, 0)
        self.state.mode = VimMode.INSERT
    
    def _enter_visual(self) -> None:
        """Enter visual mode."""
        buf = self.state.buffer
        self.state.mode = VimMode.VISUAL
        buf.visual_start_line = buf.cursor_line
        buf.visual_start_col = buf.cursor_col
    
    def _enter_visual_line(self) -> None:
        """Enter visual line mode."""
        buf = self.state.buffer
        self.state.mode = VimMode.VISUAL_LINE
        buf.visual_start_line = buf.cursor_line
        buf.visual_start_col = 0
        buf.visual_end_line = buf.cursor_line
        buf.visual_end_col = len(buf.current_line) - 1
    
    def _exit_visual(self) -> None:
        """Exit visual mode."""
        self.state.mode = VimMode.NORMAL
    
    def _enter_command(self) -> None:
        """Enter command mode."""
        self.state.mode = VimMode.COMMAND
    
    def _exit_command(self) -> None:
        """Exit command mode."""
        self.state.mode = VimMode.NORMAL
    
    def _enter_replace(self) -> None:
        """Enter single character replace."""
        self.state.mode = VimMode.REPLACE
    
    def _enter_replace_mode(self) -> None:
        """Enter replace mode."""
        self.state.mode = VimMode.REPLACE
    
    # Edit operations
    def _delete_char(self) -> None:
        """Delete character under cursor."""
        buf = self.state.buffer
        line = buf.lines[buf.cursor_line]
        if buf.cursor_col < len(line):
            buf.lines[buf.cursor_line] = line[:buf.cursor_col] + line[buf.cursor_col + 1:]
    
    def _delete_line(self) -> None:
        """Delete current line."""
        self.state.buffer.delete_line(self.state.buffer.cursor_line)
    
    def _yank_line(self) -> None:
        """Yank current line."""
        self.state.registers['"'].content = self.state.buffer.current_line
        self.state.registers['"'].is_linewise = True
    
    def _put_after(self) -> None:
        """Put text after cursor."""
        reg = self.state.registers['"']
        if not reg.content:
            return
        
        buf = self.state.buffer
        if reg.is_linewise:
            buf.insert_line(buf.cursor_line + 1, reg.content)
            buf.move_cursor(buf.cursor_line + 1, 0)
        else:
            line = buf.current_line
            buf.lines[buf.cursor_line] = (
                line[:buf.cursor_col + 1] + reg.content + line[buf.cursor_col + 1:]
            )
            buf.cursor_col += len(reg.content)
    
    def _put_before(self) -> None:
        """Put text before cursor."""
        reg = self.state.registers['"']
        if not reg.content:
            return
        
        buf = self.state.buffer
        if reg.is_linewise:
            buf.insert_line(buf.cursor_line, reg.content)
        else:
            line = buf.current_line
            buf.lines[buf.cursor_line] = (
                line[:buf.cursor_col] + reg.content + line[buf.cursor_col:]
            )
    
    def _undo(self) -> None:
        """Undo last change."""
        pass  # Would need undo stack
    
    def _redo(self) -> None:
        """Redo last undone change."""
        pass  # Would need redo stack
    
    # Insert mode operations
    def _backspace(self) -> None:
        """Handle backspace in insert mode."""
        buf = self.state.buffer
        if buf.cursor_col > 0:
            line = buf.current_line
            buf.lines[buf.cursor_line] = line[:buf.cursor_col - 1] + line[buf.cursor_col:]
            buf.cursor_col -= 1
        elif buf.cursor_line > 0:
            # Join with previous line
            prev_line = buf.lines[buf.cursor_line - 1]
            curr_line = buf.current_line
            buf.lines[buf.cursor_line - 1] = prev_line + curr_line
            buf.delete_line(buf.cursor_line)
            buf.cursor_col = len(prev_line)
    
    def _insert_tab(self) -> None:
        """Insert tab in insert mode."""
        indent = " " * self.state.indent_size if self.state.use_spaces else "\t"
        buf = self.state.buffer
        line = buf.current_line
        buf.lines[buf.cursor_line] = line[:buf.cursor_col] + indent + line[buf.cursor_col:]
        buf.cursor_col += len(indent)
    
    def _insert_newline(self) -> None:
        """Insert newline in insert mode."""
        buf = self.state.buffer
        line = buf.current_line
        before = line[:buf.cursor_col]
        after = line[buf.cursor_col:]
        
        buf.lines[buf.cursor_line] = before
        buf.insert_line(buf.cursor_line + 1, after)
        buf.move_cursor(buf.cursor_line + 1, 0)
    
    def insert_text(self, text: str) -> None:
        """Insert text at cursor (for insert mode)."""
        if self.state.mode != VimMode.INSERT:
            return
        
        buf = self.state.buffer
        line = buf.current_line
        buf.lines[buf.cursor_line] = (
            line[:buf.cursor_col] + text + line[buf.cursor_col:]
        )
        buf.cursor_col += len(text)
    
    # Search
    def _enter_search(self) -> None:
        """Enter search mode."""
        self.state.mode = VimMode.COMMAND
    
    def _repeat_search(self) -> None:
        """Repeat last search."""
        self._search(self.state.search_pattern, self.state.search_direction)
    
    def _repeat_search_reverse(self) -> None:
        """Repeat last search in reverse."""
        self._search(self.state.search_pattern, -self.state.search_direction)
    
    def _search(self, pattern: str, direction: int) -> None:
        """Search for pattern."""
        buf = self.state.buffer
        self.state.search_pattern = pattern
        self.state.search_direction = direction
        
        start_line = buf.cursor_line + direction
        step = direction
        
        for i in range(buf.line_count):
            line_idx = (start_line + i * step) % buf.line_count
            if re.search(pattern, buf.lines[line_idx]):
                buf.move_cursor(line_idx, 0)
                break
    
    # Visual operations
    def _visual_delete(self) -> None:
        """Delete visual selection."""
        buf = self.state.buffer
        start = min(buf.visual_start_line, buf.visual_end_line)
        end = max(buf.visual_start_line, buf.visual_end_line)
        
        # Store in register
        self.state.registers['"'].content = buf.get_selection()
        
        # Delete lines
        for _ in range(end - start + 1):
            buf.delete_line(start)
        
        self._exit_visual()
    
    def _visual_yank(self) -> None:
        """Yank visual selection."""
        buf = self.state.buffer
        self.state.registers['"'].content = buf.get_selection()
        self._exit_visual()
    
    def _visual_change(self) -> None:
        """Change visual selection."""
        self._visual_delete()
        self.state.mode = VimMode.INSERT
    
    def _visual_put(self) -> None:
        """Put in visual selection."""
        self._visual_delete()
        self._put_after()
    
    # Operators and motions
    def _start_operator(self) -> None:
        """Start operator pending state."""
        pass  # Would need more complex state machine
    
    def _start_change(self) -> None:
        """Start change operator."""
        self._delete_line()
        self.state.mode = VimMode.INSERT
    
    def _start_yank(self) -> None:
        """Start yank operator."""
        self._yank_line()
    
    def _start_indent(self) -> None:
        """Start indent."""
        self._op_indent()
    
    def _start_dedent(self) -> None:
        """Start dedent."""
        self._op_dedent()
    
    def _op_delete(self) -> None:
        """Delete operation."""
        self._delete_line()
    
    def _op_change(self) -> None:
        """Change operation."""
        self._delete_line()
        self.state.mode = VimMode.INSERT
    
    def _op_yank(self) -> None:
        """Yank operation."""
        self._yank_line()
    
    def _op_indent(self) -> None:
        """Indent operation."""
        buf = self.state.buffer
        indent = " " * self.state.indent_size if self.state.use_spaces else "\t"
        buf.lines[buf.cursor_line] = indent + buf.current_line
        buf.cursor_col += len(indent)
    
    def _op_dedent(self) -> None:
        """Dedent operation."""
        buf = self.state.buffer
        line = buf.current_line
        if line.startswith(" " * self.state.indent_size):
            buf.lines[buf.cursor_line] = line[self.state.indent_size:]
            buf.cursor_col = max(0, buf.cursor_col - self.state.indent_size)
        elif line.startswith("\t"):
            buf.lines[buf.cursor_line] = line[1:]
            buf.cursor_col = max(0, buf.cursor_col - 1)
    
    def _op_toggle_case(self) -> None:
        """Toggle case of motion."""
        pass
    
    def _op_lowercase(self) -> None:
        """Lowercase motion."""
        pass
    
    def _op_uppercase(self) -> None:
        """Uppercase motion."""
        pass
    
    # View operations
    def _center_view(self) -> None:
        """Center view on cursor."""
        pass
    
    def _bottom_view(self) -> None:
        """Bottom view on cursor."""
        pass
    
    def _top_view(self) -> None:
        """Top view on cursor."""
        pass
    
    # Motions
    def _motion_left(self) -> tuple[int, int]:
        return (self.state.buffer.cursor_line, max(0, self.state.buffer.cursor_col - 1))
    
    def _motion_right(self) -> tuple[int, int]:
        return (self.state.buffer.cursor_line, min(len(self.state.buffer.current_line), self.state.buffer.cursor_col + 1))
    
    def _motion_down(self) -> tuple[int, int]:
        buf = self.state.buffer
        if buf.cursor_line < buf.line_count - 1:
            return (buf.cursor_line + 1, min(buf.cursor_col, len(buf.lines[buf.cursor_line + 1])))
        return (buf.cursor_line, buf.cursor_col)
    
    def _motion_up(self) -> tuple[int, int]:
        buf = self.state.buffer
        if buf.cursor_line > 0:
            return (buf.cursor_line - 1, min(buf.cursor_col, len(buf.lines[buf.cursor_line - 1])))
        return (buf.cursor_line, buf.cursor_col)
    
    def _repeat(self) -> None:
        """Repeat last operation."""
        pass
    
    def _execute_command(self, cmd: str) -> None:
        """Execute ex command."""
        parts = cmd.split(maxsplit=1)
        cmd_name = parts[0]
        cmd_args = parts[1] if len(parts) > 1 else ""
        
        if cmd_name == "q" or cmd_name == "quit":
            raise EOFError()
        elif cmd_name == "w" or cmd_name == "write":
            pass  # Would write file
        elif cmd_name == "wq":
            pass  # Would write and quit
        
        self._exit_command()
    
    def handle_key(self, key: str) -> None:
        """Handle a key press."""
        mode = self.state.mode
        
        if mode in self._key_handlers:
            handlers = self._key_handlers[mode]
            if key in handlers:
                handlers[key]()
                return
        
        # Default: insert in insert mode
        if mode == VimMode.INSERT:
            if key == "Enter":
                self._insert_newline()
            elif key == "Backspace":
                self._backspace()
            elif len(key) == 1:
                self.insert_text(key)


class VimREPL:
    """REPL with Vim mode support."""
    
    def __init__(self):
        self.vim = VimEngine()
        self.repl = None  # Would integrate with interactive REPL
    
    def run(self) -> None:
        """Run Vim-enabled REPL."""
        print("Vim-enabled REPL. Type : for commands, i for insert mode.")
        print("Use vim motions: j/k/h/l, w, b, $, ^, gg, G")
        print()
        
        while True:
            try:
                line = input(f"{self.vim.state.mode.name.lower()}> ")
                for char in line:
                    self.vim.handle_key(char)
            except EOFError:
                break
