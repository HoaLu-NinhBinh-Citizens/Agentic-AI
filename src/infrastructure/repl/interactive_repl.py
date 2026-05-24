"""Interactive REPL with advanced features.

Features:
- Multi-line input with history
- Auto-indentation
- Tab completion
- Magic commands
- Variable introspection
- Output rendering
- Async execution
"""

from __future__ import annotations

import asyncio
import code
import inspect
import os
import re
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable


class REPLMode(Enum):
    """REPL operating modes."""
    NORMAL = "normal"
    INSERT = "insert"
    VISUAL = "visual"
    PAGER = "pager"


@dataclass
class REPLHistory:
    """REPL command history."""
    commands: list[str] = field(default_factory=list)
    current_index: int = -1
    
    def add(self, command: str) -> None:
        """Add command to history."""
        if command.strip() and command != self.commands[-1] if self.commands else True:
            self.commands.append(command)
        self.current_index = len(self.commands)
    
    def previous(self) -> str | None:
        """Get previous command."""
        if self.current_index > 0:
            self.current_index -= 1
            return self.commands[self.current_index]
        return None
    
    def next(self) -> str | None:
        """Get next command."""
        if self.current_index < len(self.commands) - 1:
            self.current_index += 1
            return self.commands[self.current_index]
        self.current_index = len(self.commands)
        return ""
    
    def save(self, path: Path) -> None:
        """Save history to file."""
        path.write_text("\n".join(self.commands))
    
    def load(self, path: Path) -> None:
        """Load history from file."""
        if path.exists():
            self.commands = path.read_text().strip().split("\n")


@dataclass 
class MagicCommand:
    """A magic command definition."""
    name: str
    func: Callable
    description: str
    args_help: str = ""


class InteractiveREPL:
    """Interactive Python REPL with advanced features.
    
    Supports:
    - Multi-line statements
    - Magic commands (% prefix)
    - Auto-indentation
    - Tab completion
    - Variable introspection
    - Output rendering
    - Async code execution
    """
    
    def __init__(self, globals: dict | None = None, locals: dict | None = None):
        self.globals = globals or {}
        self.locals = locals or self.globals
        self.history = REPLHistory()
        self._mode = REPLMode.NORMAL
        self._buffer: list[str] = []
        self._indent_level = 0
        self._magic_commands: dict[str, MagicCommand] = {}
        self._output_handlers: list[Callable] = []
        self._setup_magic_commands()
    
    def _setup_magic_commands(self) -> None:
        """Setup built-in magic commands."""
        self.register_magic("help", self._magic_help, "Show help", "[command]")
        self.register_magic("ls", self._magic_ls, "List variables")
        self.register_magic("who", self._magic_who, "Show all variables")
        self.register_magic("whos", self._magic_who, "Show all variables (detailed)")
        self.register_magic("load", self._magic_load, "Load code from file", "<filename>")
        self.register_magic("save", self._magic_save, "Save session to file", "<filename>")
        self.register_magic("time", self._magic_time, "Time execution", "<code>")
        self.register_magic("timeit", self._magic_timeit, "Time with repetition", "<code>")
        self.register_magic("pdb", self._magic_pdb, "Start debugger")
        self.register_magic("debug", self._magic_debug, "Toggle debug mode")
        self.register_magic("clear", self._magic_clear, "Clear screen")
        self.register_magic("reset", self._magic_reset, "Reset namespace")
        self.register_magic("env", self._magic_env, "Show environment")
        self.register_magic("cd", self._magic_cd, "Change directory", "<path>")
        self.register_magic("pwd", self._magic_pwd, "Print working directory")
        self.register_magic("history", self._magic_history, "Show command history")
        self.register_magic("doc", self._magic_doc, "Show documentation", "<object>")
        self.register_magic("source", self._magic_source, "Show source code", "<object>")
    
    def register_magic(self, name: str, func: Callable, description: str, args_help: str = "") -> None:
        """Register a magic command."""
        self._magic_commands[name] = MagicCommand(
            name=name,
            func=func,
            description=description,
            args_help=args_help,
        )
    
    def push_handler(self, handler: Callable) -> None:
        """Add output handler."""
        self._output_handlers.append(handler)
    
    async def run(self) -> None:
        """Run the REPL."""
        print("Python Interactive REPL (Agentic-AI)")
        print("Type 'help' for commands, 'exit()' to quit\n")
        
        while True:
            try:
                line = await self._get_input()
                
                if not line.strip():
                    continue
                
                # Handle magic commands
                if line.startswith("%"):
                    await self._handle_magic(line[1:])
                    continue
                
                # Handle exit
                if line.strip() in ("exit()", "exit", "quit()", "quit", "q"):
                    break
                
                # Add to history
                self.history.add(line)
                
                # Execute
                await self._execute(line)
                
            except (KeyboardInterrupt, EOFError):
                print("\nUse exit() to quit")
                continue
    
    async def _get_input(self) -> str:
        """Get input from user."""
        prompt = self._get_prompt()
        
        # Use asyncio for non-blocking input
        loop = asyncio.get_event_loop()
        line = await loop.run_in_executor(
            None,
            lambda: input(prompt)
        )
        return line
    
    def _get_prompt(self) -> str:
        """Get appropriate prompt."""
        if self._buffer:
            return "..." + " " * (self._indent_level * 4)
        return ">>> "
    
    async def _execute(self, code: str) -> Any:
        """Execute Python code."""
        # Combine with buffer if in multi-line mode
        full_code = "\n".join(self._buffer + [code])
        
        # Check if statement is complete
        if self._is_incomplete(full_code):
            self._buffer.append(code)
            self._indent_level = self._calc_indent(code)
            return None
        
        # Execute
        code_to_run = full_code
        self._buffer = []
        self._indent_level = 0
        
        try:
            # Check for async
            if "async " in code_to_run or "await " in code_to_run:
                result = await self._execute_async(code_to_run)
            else:
                result = exec(code_to_run, self.globals, self.locals)
            
            # Call output handlers
            if result is not None:
                self._handle_output(result)
            
            return result
            
        except SyntaxError as e:
            if e.msg == "unexpected EOF while parsing":
                # Multi-line not yet complete
                self._buffer.append(code)
                self._indent_level = self._calc_indent(code)
            else:
                print(f"SyntaxError: {e}")
                self._buffer = []
                self._indent_level = 0
                
        except Exception as e:
            print(f"{type(e).__name__}: {e}")
    
    async def _execute_async(self, code: str) -> Any:
        """Execute async code."""
        compiled = compile(code, "<stdin>", "exec")
        
        # Wrap in async function if needed
        if "await " in code:
            async def run_async():
                exec(compiled, self.globals, self.locals)
            
            return await run_async()
        
        return exec(compiled, self.globals, self.locals)
    
    def _is_incomplete(self, code: str) -> bool:
        """Check if code is incomplete."""
        try:
            compile(code, "<stdin>", "exec")
            return False
        except SyntaxError as e:
            return "incomplete" in str(e).lower() or e.msg in (
                "unexpected EOF while parsing",
                "EOF in multi-line statement",
            )
    
    def _calc_indent(self, code: str) -> int:
        """Calculate expected indent level."""
        # Simple heuristic based on trailing :
        stripped = code.rstrip()
        if stripped.endswith(":"):
            return self._indent_level + 1
        
        # Dedent on pass, return, break, continue
        if stripped in ("pass", "break", "continue"):
            return max(0, self._indent_level - 1)
        
        if stripped.startswith("return") and not stripped.startswith("return "):
            return max(0, self._indent_level - 1)
        
        return self._indent_level
    
    def _handle_output(self, result: Any) -> None:
        """Handle and render output."""
        for handler in self._output_handlers:
            handler(result)
        
        # Default rendering
        if result is not None:
            print(self._render_result(result))
    
    def _render_result(self, result: Any) -> str:
        """Render result for display."""
        if isinstance(result, str):
            return result
        if isinstance(result, (list, tuple, set)):
            return repr(result)
        if isinstance(result, dict):
            lines = [f"{{{len(result)} items}}"]
            for k, v in list(result.items())[:5]:
                lines.append(f"  {k}: {repr(v)[:50]}")
            return "\n".join(lines)
        if isinstance(result, (int, float, bool)):
            return str(result)
        
        # Object representation
        return repr(result)
    
    async def _handle_magic(self, command: str) -> None:
        """Handle magic command."""
        parts = command.split(maxsplit=1)
        name = parts[0]
        args = parts[1] if len(parts) > 1 else ""
        
        if name in self._magic_commands:
            try:
                await self._magic_commands[name].func(args)
            except Exception as e:
                print(f"Error: {e}")
        else:
            print(f"Unknown magic command: {name}")
            print("Type %help for available commands")
    
    # Magic command implementations
    
    async def _magic_help(self, args: str) -> None:
        """Show help."""
        if args:
            # Help for specific thing
            try:
                obj = self.locals.get(args) or self.globals.get(args)
                if obj:
                    print(inspect.getdoc(obj) or "No documentation")
                else:
                    print(f"'{args}' not found")
            except:
                print(f"Could not get help for '{args}'")
        else:
            print("Available magic commands:")
            for name, cmd in sorted(self._magic_commands.items()):
                args = f" {cmd.args_help}" if cmd.args_help else ""
                print(f"  %{name}{args} - {cmd.description}")
    
    async def _magic_ls(self, args: str) -> None:
        """List variables."""
        vars = [(k, type(v).__name__, repr(v)[:50]) 
                for k, v in self.locals.items() 
                if not k.startswith("_")]
        for name, type_name, value in sorted(vars):
            print(f"  {name}: {type_name} = {value}")
    
    async def _magic_who(self, args: str) -> None:
        """Show all variables detailed."""
        for name, value in sorted(self.locals.items()):
            if name.startswith("_"):
                continue
            print(f"{name}:")
            print(f"  type: {type(value).__name__}")
            print(f"  value: {repr(value)[:100]}")
            print()
    
    async def _magic_load(self, args: str) -> None:
        """Load code from file."""
        if not args:
            print("Usage: %load <filename>")
            return
        
        path = Path(args)
        if not path.exists():
            print(f"File not found: {args}")
            return
        
        code = path.read_text()
        exec(code, self.globals, self.locals)
        print(f"Loaded {path.name}")
    
    async def _magic_save(self, args: str) -> None:
        """Save session to file."""
        if not args:
            print("Usage: %save <filename>")
            return
        
        path = Path(args)
        path.write_text("\n".join(self.history.commands))
        print(f"Saved {len(self.history.commands)} commands")
    
    async def _magic_time(self, args: str) -> None:
        """Time code execution."""
        if not args:
            print("Usage: %time <code>")
            return
        
        import time
        start = time.perf_counter()
        exec(args, self.globals, self.locals)
        elapsed = (time.perf_counter() - start) * 1000
        print(f"Execution time: {elapsed:.2f}ms")
    
    async def _magic_timeit(self, args: str) -> None:
        """Time with repetition."""
        if not args:
            print("Usage: %timeit <code>")
            return
        
        import timeit
        result = timeit.timeit(args, globals=self.locals, number=1000)
        print(f"1000 iterations: {result:.4f}s ({result:.4f}ms per iteration)")
    
    async def _magic_pdb(self, args: str) -> None:
        """Start debugger."""
        import pdb
        pdb.set_trace()
    
    async def _magic_debug(self, args: str) -> None:
        """Toggle debug mode."""
        import sys
        if sys.flags.debug:
            sys.flags.debug = False
            print("Debug mode disabled")
        else:
            sys.flags.debug = True
            print("Debug mode enabled")
    
    async def _magic_clear(self, args: str) -> None:
        """Clear screen."""
        os.system("cls" if os.name == "nt" else "clear")
    
    async def _magic_reset(self, args: str) -> None:
        """Reset namespace."""
        self.locals.clear()
        self.globals.clear()
        print("Namespace reset")
    
    async def _magic_env(self, args: str) -> None:
        """Show environment."""
        print(f"Python: {sys.version}")
        print(f"Platform: {sys.platform}")
        print(f"CWD: {os.getcwd()}")
        print(f"Path entries: {len(sys.path)}")
    
    async def _magic_cd(self, args: str) -> None:
        """Change directory."""
        if not args:
            os.chdir(Path.home())
        else:
            os.chdir(args)
        print(f"CWD: {os.getcwd()}")
    
    async def _magic_pwd(self, args: str) -> None:
        """Print working directory."""
        print(os.getcwd())
    
    async def _magic_history(self, args: str) -> None:
        """Show command history."""
        for i, cmd in enumerate(self.history.commands, 1):
            print(f"  {i}: {cmd}")
    
    async def _magic_doc(self, args: str) -> None:
        """Show documentation."""
        if not args:
            print("Usage: %doc <object>")
            return
        
        obj = self.locals.get(args) or self.globals.get(args)
        if obj:
            print(inspect.getdoc(obj) or "No documentation")
        else:
            print(f"'{args}' not found")
    
    async def _magic_source(self, args: str) -> None:
        """Show source code."""
        if not args:
            print("Usage: %source <object>")
            return
        
        obj = self.locals.get(args) or self.globals.get(args)
        if obj:
            try:
                print(inspect.getsource(obj))
            except:
                print("Could not get source")
        else:
            print(f"'{args}' not found")


class REPLCompletor:
    """Tab completion for REPL."""
    
    def __init__(self, locals: dict, globals: dict):
        self.locals = locals
        self.globals = globals
        self._setup_completions()
    
    def _setup_completions(self) -> None:
        """Setup completion candidates."""
        import keyword
        import builtins
        
        self._keywords = keyword.kwlist
        self._builtins = dir(builtins)
    
    def complete(self, text: str) -> list[str]:
        """Get completions for text."""
        results = []
        
        # Keywords
        if text in self._keywords:
            results.extend(self._keywords)
        
        # Builtins
        if text in self._builtins:
            results.extend(self._builtins)
        
        # Local variables
        for name in self.locals:
            if name.startswith(text):
                results.append(name)
        
        # Global variables
        for name in self.globals:
            if name.startswith(text):
                results.append(name)
        
        return sorted(set(results))
