"""Command parser for virtual commands.

This module provides parsing for Cursor-style virtual commands:
- `/fix @filename.py line:123` - Fix specific line
- `/fix @filename.py` - Fix all issues in file
- `/explain @filename.py line:123` - Explain code at line
- `/refactor @filename.py` - Refactor entire file

Supports:
- File references with @ prefix
- Line numbers with : separator
- Optional flags like --dry-run, --apply
- Focus area filters like --focus=security
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class CommandType(Enum):
    """Types of virtual commands."""
    FIX = "fix"
    EXPLAIN = "explain"
    REFACTOR = "refactor"
    SEARCH = "search"
    TEST = "test"
    DOCS = "docs"
    UNKNOWN = "unknown"


@dataclass
class ParsedCommand:
    """Parsed virtual command."""
    command_type: CommandType
    file_path: str
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    flags: dict[str, str] = field(default_factory=dict)
    raw_command: str = ""
    
    @property
    def has_line_spec(self) -> bool:
        """Check if command specifies a line number."""
        return self.line_start is not None


class CommandParser:
    """Parser for virtual commands like /fix, /explain, /refactor."""
    
    # Command pattern: /command @file[:line[:end]] [flags]
    COMMAND_PATTERN = re.compile(
        r"^/(?P<command>\w+)"
        r"(?:\s+@(?P<file>[^\s:]+))?"
        r"(?::(?P<line>\d+))?"
        r"(?::(?P<end_line>\d+))?"
        r"(?:\s+(?P<options>.*))?$"
    )
    
    # Flag patterns
    FLAG_PATTERNS = {
        "dry_run": re.compile(r"--dry-run\b"),
        "apply": re.compile(r"--apply\b"),
        "interactive": re.compile(r"--interactive\b|--i\b"),
        "focus": re.compile(r"--focus=([\w,]+)"),
        "rule": re.compile(r"--rule=([\w]+)"),
        "scope": re.compile(r"--scope=([\w]+)"),
        "auto_fix": re.compile(r"--auto-fix(?:=([a-z]+))?"),
        "severity": re.compile(r"--severity=([\w]+)"),
        "generate": re.compile(r"--generate\b"),
        "run": re.compile(r"--run\b"),
    }
    
    # Command aliases
    COMMAND_ALIASES: dict[str, CommandType] = {
        "fix": CommandType.FIX,
        "explain": CommandType.EXPLAIN,
        "refactor": CommandType.REFACTOR,
        "search": CommandType.SEARCH,
        "test": CommandType.TEST,
        "docs": CommandType.DOCS,
        "doc": CommandType.DOCS,
        "goto": CommandType.SEARCH,
        "find": CommandType.SEARCH,
    }
    
    def parse(self, raw: str) -> Optional[ParsedCommand]:
        """Parse a virtual command string.
        
        Args:
            raw: Raw command string like "/fix @src/main.py:42 --dry-run"
            
        Returns:
            ParsedCommand if parsing succeeds, None otherwise
        """
        raw = raw.strip()
        if not raw.startswith("/"):
            return None
        
        match = self.COMMAND_PATTERN.match(raw)
        if not match:
            return None
        
        groups = match.groupdict()
        
        # Parse command type
        cmd_str = groups.get("command", "").lower()
        command_type = self.COMMAND_ALIASES.get(cmd_str, CommandType.UNKNOWN)
        
        # Parse file path
        file_path = groups.get("file") or ""
        
        # Parse line numbers
        line_start = None
        line_end = None
        if groups.get("line"):
            line_start = int(groups["line"])
        if groups.get("end_line"):
            line_end = int(groups["end_line"])
        
        # Parse options/flags
        options_str = groups.get("options") or ""
        flags = self._parse_flags(options_str)
        
        return ParsedCommand(
            command_type=command_type,
            file_path=file_path,
            line_start=line_start,
            line_end=line_end,
            flags=flags,
            raw_command=raw,
        )
    
    def _parse_flags(self, options: str) -> dict[str, str]:
        """Parse flag options from options string.
        
        Args:
            options: Options string like "--dry-run --focus=security"
            
        Returns:
            Dict of flag name to flag value
        """
        flags: dict[str, str] = {}
        
        for flag_name, pattern in self.FLAG_PATTERNS.items():
            match = pattern.search(options)
            if match:
                # Check if pattern has capture group
                if match.lastindex and match.lastindex >= 1:
                    flags[flag_name] = match.group(1) or "true"
                else:
                    flags[flag_name] = "true"
        
        return flags
    
    def parse_shorthand(self, raw: str) -> Optional[ParsedCommand]:
        """Parse shorthand command format like "@file:line".
        
        Args:
            raw: Raw string like "@src/main.py:42"
            
        Returns:
            ParsedCommand if parsing succeeds, None otherwise
        """
        raw = raw.strip()
        
        # Pattern: @file[:line[:end_line]]
        shorthand_pattern = re.compile(
            r"^@(?P<file>[^:]+)"
            r"(?::(?P<line>\d+))?"
            r"(?::(?P<end_line>\d+))?$"
        )
        
        match = shorthand_pattern.match(raw)
        if not match:
            return None
        
        groups = match.groupdict()
        
        file_path = groups.get("file", "")
        line_start = int(groups["line"]) if groups.get("line") else None
        line_end = int(groups["end_line"]) if groups.get("end_line") else None
        
        return ParsedCommand(
            command_type=CommandType.UNKNOWN,
            file_path=file_path,
            line_start=line_start,
            line_end=line_end,
            raw_command=raw,
        )
    
    def get_command_help(self, command_type: CommandType) -> str:
        """Get help text for a command type.
        
        Args:
            command_type: Type of command
            
        Returns:
            Help text string
        """
        help_texts = {
            CommandType.FIX: """
/fix @filename[:line] [flags]
    Fix issues in a file or at a specific line.
    
    Flags:
      --dry-run       Show what would be fixed without applying
      --apply         Apply fixes automatically
      --interactive   Ask for confirmation before each fix
      --rule=RULE     Fix only specific rule (e.g., ML001, SEC001)
      --focus=AREA    Focus on specific area (security, quality, ml, embedded)
    
    Examples:
      /fix @src/main.py:42
      /fix @src/main.py --dry-run
      /fix @src/main.py --rule=ML001
""",
            CommandType.EXPLAIN: """
/explain @filename[:line] [flags]
    Explain code at a specific line or entire file.
    
    Flags:
      --context=N     Show N lines of context (default: 5)
    
    Examples:
      /explain @src/main.py:42
      /explain @src/main.py --context=10
""",
            CommandType.REFACTOR: """
/refactor @filename[:start[:end]] [flags]
    Refactor code in a file or line range.
    
    Flags:
      --dry-run       Show what would change without applying
      --apply         Apply refactoring automatically
      --mode=MODE     Refactor mode (extract, inline, move, rename)
    
    Examples:
      /refactor @src/main.py
      /refactor @src/main.py:42:60
      /refactor @src/main.py --mode=extract
""",
            CommandType.SEARCH: """
/search @filename[:line] pattern [flags]
    Search for pattern in file or at line.
    
    Examples:
      /search @src/main.py TODO
      /search @src/main.py:42 function_name
""",
            CommandType.TEST: """
/test @filename[:line] [flags]
    Generate or run tests for code.
    
    Flags:
      --generate      Generate test cases
      --run           Run existing tests
    
    Examples:
      /test @src/main.py
      /test @src/main.py:42 --generate
""",
            CommandType.DOCS: """
/docs @filename[:line] [flags]
    Show documentation for code.
    
    Examples:
      /docs @src/main.py:42
      /docs @src/main.py
""",
        }
        
        return help_texts.get(command_type, "Unknown command type.")


def parse_virtual_command(raw: str) -> Optional[ParsedCommand]:
    """Parse a virtual command string.
    
    This is a convenience function that creates a CommandParser
    and uses it to parse the command.
    
    Args:
        raw: Raw command string
        
    Returns:
        ParsedCommand if parsing succeeds, None otherwise
    """
    parser = CommandParser()
    
    # Try full command first
    result = parser.parse(raw)
    if result:
        return result
    
    # Try shorthand format
    return parser.parse_shorthand(raw)
