"""Interactive TUI with real-time streaming updates.

Features:
- Live token streaming display
- Tool execution cards with progress
- Message history with smooth scrolling
- Keyboard navigation
- Status indicators
- Async refresh
"""

from __future__ import annotations

import asyncio
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, AsyncIterator, Callable

# Rich for TUI rendering
try:
    from rich.console import Console
    from rich.live import Live
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
    from rich.layout import Layout
    from rich.table import Table
    from rich.text import Text
    HAS_RICH = True
except ImportError:
    HAS_RICH = False


@dataclass
class StreamState:
    """State of a streaming response."""
    content: str = ""
    is_complete: bool = False
    tool_calls: list[dict] = field(default_factory=list)
    error: str | None = None


class TUIRenderer:
    """Base TUI renderer (no dependencies).
    
    Used when rich is not available.
    """
    
    def __init__(self, width: int | None = None):
        self.width = width or shutil.get_terminal_size().columns
        self.height = shutil.get_terminal_size().lines
    
    def clear(self):
        """Clear the screen."""
        print("\033[2J\033[H", end="", flush=True)
    
    def move_cursor(self, x: int, y: int):
        """Move cursor to position."""
        print(f"\033[{y};{x}H", end="", flush=True)
    
    def hide_cursor(self):
        print("\033[?25l", end="", flush=True)
    
    def show_cursor(self):
        print("\033[?25h", end="", flush=True)
    
    def bold(self, text: str) -> str:
        return f"\033[1m{text}\033[0m"
    
    def dim(self, text: str) -> str:
        return f"\033[2m{text}\033[0m"
    
    def cyan(self, text: str) -> str:
        return f"\033[36m{text}\033[0m"
    
    def green(self, text: str) -> str:
        return f"\033[32m{text}\033[0m"
    
    def red(self, text: str) -> str:
        return f"\033[31m{text}\033[0m"
    
    def yellow(self, text: str) -> str:
        return f"\033[33m{text}\033[0m"
    
    def render_message(self, role: str, content: str) -> str:
        """Render a message."""
        role_colors = {
            "user": self.cyan,
            "assistant": self.bold,
            "system": self.dim,
            "tool": self.yellow,
        }
        color_fn = role_colors.get(role, str)
        prefix = color_fn(f"[{role}]")
        return f"{prefix} {content}"
    
    def render_tool_card(
        self,
        name: str,
        status: str,
        duration_ms: float | None = None,
    ) -> str:
        """Render a tool execution card."""
        status_colors = {
            "running": self.yellow,
            "success": self.green,
            "error": self.red,
        }
        color_fn = status_colors.get(status, str)
        status_text = color_fn(f"[{status}]")
        duration = f" ({duration_ms:.0f}ms)" if duration_ms else ""
        return f"{self.bold('[Tool]')} {name} {status_text}{duration}"
    
    def render_spinner(self, frame: int) -> str:
        """Render spinner frame."""
        frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧"]
        return frames[frame % len(frames)]


class RichTUIRenderer:
    """Rich-based TUI renderer with advanced features."""
    
    def __init__(self):
        if not HAS_RICH:
            raise ImportError("rich library required for RichTUIRenderer")
        
        self.console = Console(width=None, height=None)
        self.layout = Layout()
        self.progress = None
        self._live = None
    
    def create_layout(self, header: str, footer: str):
        """Create the main layout structure."""
        self.layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main"),
            Layout(name="footer", size=3),
        )
        
        self.layout["header"].update(
            Panel(f"[bold cyan]{header}[/bold cyan]", border_style="cyan")
        )
        self.layout["footer"].update(
            Panel(f"[dim]{footer}[/dim]", border_style="dim")
        )
    
    def render_message_card(self, role: str, content: str, timestamp: datetime | None = None):
        """Render a message card."""
        from rich.markdown import Markdown
        
        role_icons = {
            "user": "👤",
            "assistant": "🤖",
            "system": "⚙️",
            "tool": "🔧",
        }
        icon = role_icons.get(role, "•")
        
        time_str = ""
        if timestamp:
            time_str = f"[dim]{timestamp.strftime('%H:%M:%S')}[/dim]"
        
        return Panel(
            Markdown(content) if len(content) < 500 else content,
            title=f"{icon} {role.title()} {time_str}",
            border_style="cyan" if role == "user" else "green" if role == "assistant" else "dim",
        )
    
    def render_tool_execution(
        self,
        name: str,
        arguments: dict | None = None,
        status: str = "pending",
        result: str | None = None,
        error: str | None = None,
        duration_ms: float | None = None,
    ):
        """Render a tool execution card."""
        from rich.tree import Tree
        
        tree = Tree(f"[yellow]🔧[/yellow] [bold]{name}[/bold]")
        
        if arguments:
            args_text = " ".join(f"[cyan]{k}[/cyan]=[yellow]{v}[/yellow]" 
                                for k, v in list(arguments.items())[:3])
            tree.add(f"Args: {args_text}")
        
        if status == "running":
            tree.add("[yellow]⟳ Running...[/yellow]")
        elif status == "success" and result:
            result_preview = result[:200] + "..." if len(result) > 200 else result
            tree.add(f"[green]✓[/green] [dim]{result_preview}[/dim]")
        elif status == "error":
            tree.add(f"[red]✗[/red] {error}")
        
        if duration_ms:
            tree.add(f"[dim]Duration: {duration_ms:.0f}ms[/dim]")
        
        return tree
    
    def render_streaming_content(self, content: str, cursor: str = "▌") -> str:
        """Render streaming content with cursor."""
        from rich.text import Text
        
        text = Text(content)
        text.append(cursor, style="blink cyan")
        return text
    
    def create_progress_bar(self) -> Progress:
        """Create a progress bar."""
        return Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            console=self.console,
        )
    
    def render_table(self, data: list[dict], headers: list[str]) -> Table:
        """Render a table."""
        table = Table(show_header=True, header_style="bold cyan")
        
        for header in headers:
            table.add_column(header)
        
        for row in data:
            table.add_row(*[str(row.get(h, "")) for h in headers])
        
        return table
    
    async def live_update(self, render_fn: Callable[[], Any]):
        """Update display in real-time."""
        with Live(
            render_fn(),
            console=self.console,
            refresh_per_second=10,
            transient=False,
        ) as live:
            self._live = live
            yield live
            self._live = None


class StreamingTUIPanel:
    """Interactive TUI panel for streaming responses."""
    
    def __init__(self, use_rich: bool = True):
        if use_rich and HAS_RICH:
            self.renderer = RichTUIRenderer()
        else:
            self.renderer = TUIRenderer()
        
        self.messages: list[dict] = []
        self.tool_calls: list[dict] = []
        self.state = StreamState()
    
    def add_message(self, role: str, content: str, timestamp: datetime | None = None):
        """Add a message to the history."""
        self.messages.append({
            "role": role,
            "content": content,
            "timestamp": timestamp or datetime.now(),
        })
    
    def add_tool_call(self, name: str, arguments: dict):
        """Record a tool call."""
        self.tool_calls.append({
            "name": name,
            "arguments": arguments,
            "status": "running",
            "started_at": datetime.now(),
        })
    
    def complete_tool_call(self, result: str | None = None, error: str | None = None):
        """Complete the current tool call."""
        if self.tool_calls:
            tool = self.tool_calls[-1]
            tool["status"] = "error" if error else "success"
            tool["completed_at"] = datetime.now()
            tool["duration_ms"] = (
                tool["completed_at"] - tool["started_at"]
            ).total_seconds() * 1000
            if result:
                tool["result"] = result
            if error:
                tool["error"] = error
    
    def update_stream(self, token: str):
        """Append a streaming token."""
        self.state.content += token
    
    def complete_stream(self):
        """Mark streaming as complete."""
        self.state.is_complete = True
    
    async def stream_tokens(
        self,
        token_iterator: AsyncIterator[str],
        render_delay: float = 0.01,
    ):
        """Stream tokens with real-time display updates.
        
        Args:
            token_iterator: Async iterator of tokens
            render_delay: Delay between renders (seconds)
        """
        self.state = StreamState()
        
        async for token in token_iterator:
            self.update_stream(token)
            # Render update
            self._render_streaming()
            await asyncio.sleep(render_delay)
        
        self.complete_stream()
        self.add_message("assistant", self.state.content)
    
    def _render_streaming(self):
        """Render the current streaming state."""
        if HAS_RICH:
            self._render_rich_streaming()
        else:
            self._render_basic_streaming()
    
    def _render_basic_streaming(self):
        """Render streaming with basic ANSI."""
        r = self.renderer
        
        # Get terminal size
        width = r.width
        height = r.height
        
        # Header
        print(r.bold("\n╔" + "═" * (width - 2) + "╗"))
        print(r.bold("║") + " Agentic-AI ".center(width - 2) + r.bold("║"))
        print(r.bold("╚" + "═" * (width - 2) + "╝"))
        
        # Messages
        print()
        for msg in self.messages[-5:]:  # Last 5 messages
            print(r.render_message(msg["role"], msg["content"][:width - 10]))
        
        print()
        
        # Streaming content
        content = self.state.content
        if len(content) > width - 4:
            content = content[-(width - 4):]
        print(r.cyan(f"► {content}"))
        
        # Tool calls
        if self.tool_calls:
            print()
            for tool in self.tool_calls[-3:]:
                print(r.render_tool_card(
                    tool["name"],
                    tool["status"],
                    tool.get("duration_ms"),
                ))
        
        # Move cursor up
        lines = len(self.messages[-5:]) + len(self.tool_calls[-3:]) + 10
        print(f"\033[{lines}A", end="", flush=True)
    
    def _render_rich_streaming(self):
        """Render streaming with Rich."""
        from rich.live import Live
        from rich.panel import Panel
        from rich.text import Text
        
        content = self.state.content
        if not content:
            content = "[dim]Waiting for response...[/dim]"
        
        streaming_text = Text(content)
        streaming_text.append("▌", style="blink cyan")
        
        # Build output
        from rich.console import Group
        
        panels = [
            Panel(streaming_text, title="[cyan]Streaming[/cyan]", border_style="cyan")
        ]
        
        # Tool calls
        if self.tool_calls:
            tool_panels = []
            for tool in self.tool_calls[-3:]:
                status = tool["status"]
                status_icon = "⟳" if status == "running" else "✓" if status == "success" else "✗"
                status_style = "yellow" if status == "running" else "green" if status == "success" else "red"
                
                tool_text = f"[yellow]{status_icon}[/yellow] [bold]{tool['name']}[/bold]"
                if tool.get("duration_ms"):
                    tool_text += f" [dim]({tool['duration_ms']:.0f}ms)[/dim]"
                
                tool_panels.append(Panel(tool_text, border_style=status_style))
            
            panels.extend(tool_panels)
        
        return Group(*panels)
    
    def render(self) -> str:
        """Render the full TUI state."""
        if HAS_RICH:
            return self._render_rich()
        return self._render_basic()
    
    def _render_basic(self) -> str:
        """Basic text rendering."""
        r = self.renderer
        lines = []
        
        lines.append(r.bold("=" * r.width))
        lines.append(r.cyan(" Agentic-AI ").center(r.width))
        lines.append(r.bold("=" * r.width))
        lines.append("")
        
        for msg in self.messages[-10:]:
            lines.append(r.render_message(msg["role"], msg["content"][:r.width - 20]))
        
        lines.append("")
        
        if self.state.content:
            lines.append(r.cyan(f"► {self.state.content}"))
        
        return "\n".join(lines)
    
    def _render_rich(self) -> str:
        """Rich rendering."""
        from rich.console import Group
        from rich.panel import Panel
        
        panels = []
        
        for msg in self.messages[-10:]:
            panels.append(self.renderer.render_message_card(
                msg["role"],
                msg["content"],
                msg.get("timestamp"),
            ))
        
        return Group(*panels)


class InputHandler:
    """Handle user input in the TUI."""
    
    def __init__(self):
        self.history: list[str] = []
        self.history_index: int = -1
    
    def get_input(self, prompt: str = "> ") -> str:
        """Get user input with history navigation."""
        import readline
        
        # Setup readline
        readline.parse_and_bind("tab: complete")
        readline.parse_and_bind("up: previous-history")
        readline.parse_and_bind("down: next-history")
        
        try:
            user_input = input(prompt)
            if user_input.strip():
                self.history.append(user_input)
                self.history_index = len(self.history)
            return user_input
        except (EOFError, KeyboardInterrupt):
            return "/quit"
    
    async def get_input_async(self, prompt: str = "> ") -> str:
        """Async input (runs in executor)."""
        return await asyncio.to_thread(self.get_input, prompt)


# ANSI escape codes for basic TUI
CLEAR_SCREEN = "\033[2J"
MOVE_HOME = "\033[H"
HIDE_CURSOR = "\033[?25l"
SHOW_CURSOR = "\033[?25h"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

CURSOR_UP = "\033[A"
ERASE_LINE = "\033[2K"


async def demo_streaming():
    """Demo the streaming TUI."""
    panel = StreamingTUIPanel(use_rich=False)
    
    # Add some messages
    panel.add_message("user", "Hello, how are you?")
    panel.add_message("assistant", "I'm doing well! How can I help you today?")
    
    # Simulate streaming
    print(CLEAR_SCREEN + MOVE_HOME + HIDE_CURSOR)
    
    async def token_stream():
        response = "I'm an AI assistant powered by local models. I can help with code, files, and more!"
        for char in response:
            yield char
            await asyncio.sleep(0.02)
    
    await panel.stream_tokens(token_stream())
    
    print(SHOW_CURSOR)
    print("\n\n[Demo complete]")


if __name__ == "__main__":
    asyncio.run(demo_streaming())
