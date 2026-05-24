"""TUI Application for Agentic-AI CLI.

Inspired by oh-my-pi's TUI:
- Interactive terminal interface
- Rich formatting
- Tool cards
- Streaming responses
- Input history
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from .components import (
    Color,
    Theme,
    ToolCard,
    MessageCard,
    ProgressIndicator,
    StatusBar,
    Table,
    print_header,
    print_success,
    print_error,
    print_warning,
    print_info,
    clear_line,
    move_cursor_up,
    save_cursor,
    restore_cursor,
    get_terminal_width,
)


@dataclass
class TUIColorScheme:
    """Color scheme for the TUI."""
    primary: str = Color.CYAN
    secondary: str = Color.BLUE
    success: str = Color.GREEN
    warning: str = Color.YELLOW
    error: str = Color.RED
    user_message: str = Color.BRIGHT_CYAN
    assistant_message: str = Color.WHITE
    dim: str = Color.DIM


class TUIRenderer:
    """Renders TUI components."""
    
    def __init__(self, color_scheme: TUIColorScheme | None = None):
        self.colors = color_scheme or TUIColorScheme()
    
    def render_message(self, role: str, content: str, tool_calls: list[ToolCard] | None = None) -> str:
        """Render a message card."""
        card = MessageCard(role=role, content=content, tool_calls=tool_calls or [])
        return card.render()
    
    def render_tool_card(
        self,
        name: str,
        args: dict | None = None,
        result: str = "",
        success: bool = True,
        error: str | None = None,
        duration_ms: float = 0,
    ) -> str:
        """Render a tool card."""
        card = ToolCard(
            name=name,
            arguments=args,
            result=result,
            success=success,
            error=error,
            duration_ms=duration_ms,
        )
        return card.render()
    
    def render_header(self) -> str:
        """Render the application header."""
        width = get_terminal_width()
        
        lines = []
        lines.append(f"{self.colors.primary}{'═' * width}{Color.RESET}")
        
        title = "Agentic-AI CLI"
        subtitle = "Production coding agent"
        
        padding = (width - len(title) - 2) // 2
        lines.append(f"{self.colors.primary}║{Color.RESET}{' ' * padding}{self.colors.secondary}{Color.BOLD}{title}{Color.RESET}{' ' * (width - padding - len(title) - 2)}{self.colors.primary}║{Color.RESET}")
        
        padding = (width - len(subtitle) - 2) // 2
        lines.append(f"{self.colors.primary}║{Color.RESET}{' ' * padding}{self.colors.dim}{subtitle}{Color.RESET}{' ' * (width - padding - len(subtitle) - 2)}{self.colors.primary}║{Color.RESET}")
        
        lines.append(f"{self.colors.primary}{'═' * width}{Color.RESET}")
        
        return "\n".join(lines)
    
    def render_footer(self, status: str = "") -> str:
        """Render the footer."""
        width = get_terminal_width()
        
        commands = [
            ("exit", "quit"),
            ("help", "show commands"),
            ("clear", "clear screen"),
        ]
        
        left = "Type 'exit' to quit"
        center = status
        right = " | ".join(f"Ctrl+C: cancel" for _ in [1])
        
        footer = f"{self.colors.dim}{left}{Color.RESET}"
        if center:
            padding = width - len(left) - len(right) - 2
            footer += f"{' ' * max(1, padding)}{self.colors.primary}{center}{Color.RESET}"
        
        return footer
    
    def render_prompt(self, prefix: str = "> ") -> str:
        """Render input prompt."""
        return f"{self.colors.user_message}{prefix}{Color.RESET}"
    
    def render_welcome(self) -> str:
        """Render welcome screen."""
        lines = []
        
        lines.append(self.render_header())
        lines.append("")
        
        lines.append(f"  {self.colors.success}✓{Color.RESET} Session ready")
        lines.append(f"  {self.colors.success}✓{Color.RESET} Tools loaded")
        lines.append(f"  {self.colors.success}✓{Color.RESET} LLM connected")
        
        lines.append("")
        lines.append(f"  Commands:")
        lines.append(f"    {self.colors.dim}help{Color.RESET}   - Show help")
        lines.append(f"    {self.colors.dim}tools{Color.RESET}  - List tools")
        lines.append(f"    {self.colors.dim}exit{Color.RESET}   - Exit")
        
        lines.append("")
        lines.append(f"{self.colors.primary}{'─' * get_terminal_width()}{Color.RESET}")
        lines.append("")
        
        return "\n".join(lines)


class TUISession:
    """TUI session with history and state."""
    
    def __init__(self):
        self.messages: list[tuple[str, str]] = []  # (role, content)
        self.tool_calls: list[ToolCard] = []
        self.start_time = datetime.now()
        self.turn_count = 0
        self.token_count = 0
    
    def add_message(self, role: str, content: str) -> None:
        """Add a message to history."""
        self.messages.append((role, content))
        if role == "user":
            self.turn_count += 1
    
    def add_tool_call(self, tool_card: ToolCard) -> None:
        """Add a tool call to history."""
        self.tool_calls.append(tool_card)
    
    def get_last_tool_calls(self) -> list[ToolCard]:
        """Get tool calls from last assistant message."""
        return self.tool_calls[-10:] if self.tool_calls else []
    
    def get_stats(self) -> dict:
        """Get session statistics."""
        duration = (datetime.now() - self.start_time).total_seconds()
        
        return {
            "turns": self.turn_count,
            "messages": len(self.messages),
            "tool_calls": len(self.tool_calls),
            "duration_seconds": duration,
        }


class TUIInput:
    """TUI input handling with history."""
    
    def __init__(self):
        self.history: list[str] = []
        self.history_index: int = -1
        self.current_input: str = ""
    
    def add_to_history(self, line: str) -> None:
        """Add line to history."""
        if line.strip() and (not self.history or self.history[0] != line):
            self.history.insert(0, line)
            if len(self.history) > 100:
                self.history.pop()
        self.history_index = -1
    
    def navigate_history(self, up: bool = True) -> str | None:
        """Navigate through history."""
        if not self.history:
            return None
        
        if up:
            if self.history_index < len(self.history) - 1:
                self.history_index += 1
        else:
            if self.history_index > 0:
                self.history_index -= 1
            elif self.history_index == 0:
                self.history_index = -1
                return None
        
        if self.history_index >= 0:
            return self.history[self.history_index]
        return None
    
    def read_line(self, prompt: str, history_enabled: bool = True) -> str:
        """Read a line with history navigation."""
        print(prompt, end="", flush=True)
        
        line = []
        cursor_pos = 0
        
        while True:
            try:
                char = input()
                break
            except (KeyboardInterrupt, EOFError):
                raise
            
        return line
    
    @staticmethod
    def simple_read(prompt: str) -> str:
        """Simple line reading."""
        try:
            return input(prompt)
        except (KeyboardInterrupt, EOFError):
            return ""


class AgenticTUI:
    """Main TUI application.
    
    Features:
    - Rich terminal formatting
    - Message history
    - Tool cards
    - Status bar
    - Input history
    """
    
    def __init__(
        self,
        session: TUISession | None = None,
        color_scheme: TUIColorScheme | None = None,
    ):
        self.session = session or TUISession()
        self.renderer = TUIRenderer(color_scheme)
        self.input_handler = TUIInput()
        self.status_bar = StatusBar()
        self._running = False
    
    def print_welcome(self) -> None:
        """Print welcome screen."""
        print(self.renderer.render_welcome())
    
    def print_message(self, role: str, content: str, tool_calls: list[ToolCard] | None = None) -> None:
        """Print a message with formatting."""
        msg = self.renderer.render_message(role, content, tool_calls)
        print(msg)
        self.session.add_message(role, content)
    
    def print_user_message(self, content: str) -> None:
        """Print user message."""
        self.print_message("user", content)
    
    def print_assistant_message(self, content: str, tool_calls: list[ToolCard] | None = None) -> None:
        """Print assistant message."""
        self.print_message("assistant", content, tool_calls)
    
    def print_system_message(self, content: str) -> None:
        """Print system message."""
        self.print_message("system", content)
    
    def print_tool_card(
        self,
        name: str,
        args: dict | None = None,
        result: str = "",
        success: bool = True,
        error: str | None = None,
        duration_ms: float = 0,
    ) -> None:
        """Print a tool card."""
        card = self.renderer.render_tool_card(name, args, result, success, error, duration_ms)
        print(card)
        
        tool_card = ToolCard(
            name=name,
            arguments=args,
            result=result,
            success=success,
            error=error,
            duration_ms=duration_ms,
        )
        self.session.add_tool_call(tool_card)
    
    def print_status(self, status: str) -> None:
        """Print status message."""
        self.status_bar.set_center(status)
        print(f"\r{self.status_bar.render()}", end="", flush=True)
        move_cursor_up()
    
    def print_error(self, error: str) -> None:
        """Print error message."""
        print_error(error)
    
    def print_success(self, message: str) -> None:
        """Print success message."""
        print_success(message)
    
    def print_info(self, message: str) -> None:
        """Print info message."""
        print_info(message)
    
    def print_table(self, headers: list[str], rows: list[list[str]]) -> None:
        """Print a table."""
        table = Table(headers)
        for row in rows:
            table.add_row(row)
        print(table.render())
    
    def read_input(self) -> str:
        """Read user input."""
        prompt = self.renderer.render_prompt()
        return self.input_handler.simple_read(prompt)
    
    async def read_input_async(self) -> str:
        """Read user input asynchronously."""
        loop = asyncio.get_event_loop()
        prompt = self.renderer.render_prompt()
        
        return await loop.run_in_executor(None, lambda: self.input_handler.simple_read(prompt))
    
    def clear_screen(self) -> None:
        """Clear the screen."""
        import os
        os.system("cls" if os.name == "nt" else "clear")
    
    def show_help(self) -> None:
        """Show help."""
        help_text = """
Commands:
  help     - Show this help
  tools    - List available tools
  session  - Show session stats
  clear    - Clear the screen
  exit     - Exit the CLI
  /model   - Switch LLM model
  /memory  - Hindsight memory commands
  /verbose - Toggle verbose mode

Tips:
  - Use up/down arrows to navigate input history
  - Tool calls are shown in collapsible cards
  - Markdown is rendered in responses
"""
        print(help_text)
    
    def show_tools(self, tools: list[dict]) -> None:
        """Show available tools."""
        print(f"\n{self.renderer.colors.secondary}[{len(tools)} Tools]{Color.RESET}\n")
        
        # Group by category
        by_category: dict[str, list] = {}
        for tool in tools:
            cat = tool.get("category", "unknown")
            by_category.setdefault(cat, []).append(tool)
        
        for cat, cat_tools in sorted(by_category.items()):
            print(f"  {self.renderer.colors.primary}[{cat}]{Color.RESET}")
            for tool in cat_tools:
                name = tool.get("name", "unknown")
                desc = tool.get("description", "")[:50]
                print(f"    {self.renderer.colors.success}{name}{Color.RESET} - {desc}")
            print()
    
    def show_session(self) -> None:
        """Show session statistics."""
        stats = self.session.get_stats()
        
        print(f"""
Session Statistics:
  Turns:      {stats['turns']}
  Messages:   {stats['messages']}
  Tool calls: {stats['tool_calls']}
  Duration:   {stats['duration_seconds']:.1f}s
""")
    
    async def run(self) -> None:
        """Run the TUI application."""
        self._running = True
        
        self.print_welcome()
        
        while self._running:
            try:
                user_input = await self.read_input_async()
                
                if not user_input.strip():
                    continue
                
                # Add to history
                self.input_handler.add_to_history(user_input)
                
                # Handle commands
                if user_input.strip() in ("exit", "quit", "q"):
                    self.print_info("Goodbye!")
                    break
                
                if user_input.strip() == "help":
                    self.show_help()
                    continue
                
                if user_input.strip() == "tools":
                    # This would be filled by the CLI
                    print_info("Use /tools to see available tools")
                    continue
                
                if user_input.strip() == "session":
                    self.show_session()
                    continue
                
                if user_input.strip() == "clear":
                    self.clear_screen()
                    continue
                
                # Yield to caller for LLM processing
                yield user_input
                
            except KeyboardInterrupt:
                print("\n(Use 'exit' to quit)")
            except EOFError:
                break
        
        self._running = False
    
    def stop(self) -> None:
        """Stop the TUI."""
        self._running = False
