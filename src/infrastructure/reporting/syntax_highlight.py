"""Syntax highlighting for code snippets in CLI output.

Uses Pygments for token-based colorization with graceful fallback
to plain text when Pygments is unavailable or terminal doesn't support colors.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

# Extension → Pygments lexer name mapping
_EXT_LEXER_MAP: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".rb": "ruby",
    ".swift": "swift",
    ".kt": "kotlin",
    ".scala": "scala",
    ".sh": "bash",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".toml": "toml",
    ".sql": "sql",
    ".html": "html",
    ".css": "css",
}


def _supports_color() -> bool:
    """Check if the terminal supports ANSI colors."""
    # NO_COLOR convention: https://no-color.org/
    if os.environ.get("NO_COLOR"):
        return False
    # Non-interactive (piped output)
    if not hasattr(sys.stdout, "isatty") or not sys.stdout.isatty():
        return False
    # Windows without ANSI support
    if sys.platform == "win32":
        # Windows 10+ supports ANSI via virtual terminal processing
        return os.environ.get("ANSICON") is not None or "WT_SESSION" in os.environ
    return True


def detect_language(file_path: str) -> str:
    """Detect programming language from file extension.

    Args:
        file_path: Path to the source file

    Returns:
        Pygments lexer name or empty string if unknown
    """
    ext = Path(file_path).suffix.lower()
    return _EXT_LEXER_MAP.get(ext, "")


def highlight_code(
    code: str,
    language: str = "",
    file_path: str = "",
    line_numbers: bool = True,
    start_line: int = 1,
) -> str:
    """Apply syntax highlighting to a code snippet.

    Uses Pygments if available and terminal supports colors.
    Falls back to plain text with line numbers otherwise.

    Args:
        code: The code snippet to highlight
        language: Pygments lexer name (e.g., "python", "javascript")
        file_path: File path for auto-detecting language
        line_numbers: Whether to include line numbers
        start_line: Starting line number for display

    Returns:
        Highlighted code string with ANSI escape codes, or plain text
    """
    if not _supports_color():
        return _plain_with_line_numbers(code, start_line) if line_numbers else code

    # Auto-detect language from file path if not specified
    if not language and file_path:
        language = detect_language(file_path)

    if not language:
        return _plain_with_line_numbers(code, start_line) if line_numbers else code

    try:
        from pygments import highlight as pyg_highlight
        from pygments.lexers import get_lexer_by_name
        from pygments.formatters import Terminal256Formatter

        lexer = get_lexer_by_name(language, stripall=True)
        formatter = Terminal256Formatter(style="monokai", linenos=line_numbers)
        result = pyg_highlight(code, lexer, formatter)
        return result.rstrip()
    except ImportError:
        # Pygments not installed — fallback to plain text
        return _plain_with_line_numbers(code, start_line) if line_numbers else code
    except Exception:
        # Unknown lexer or other error — fallback
        return _plain_with_line_numbers(code, start_line) if line_numbers else code


def highlight_diff(
    old_code: str,
    new_code: str,
    terminal_width: int = 80,
) -> str:
    """Render a side-by-side diff or unified diff based on terminal width.

    Args:
        old_code: Original code
        new_code: Fixed code
        terminal_width: Current terminal width

    Returns:
        Formatted diff string with color coding
    """
    if not _supports_color():
        return _plain_diff(old_code, new_code)

    if terminal_width >= 120:
        return _side_by_side_diff(old_code, new_code, terminal_width)
    else:
        return _unified_diff(old_code, new_code)


def _plain_with_line_numbers(code: str, start_line: int = 1) -> str:
    """Add line numbers to code without highlighting."""
    lines = code.split("\n")
    width = len(str(start_line + len(lines)))
    result = []
    for i, line in enumerate(lines):
        num = str(start_line + i).rjust(width)
        result.append(f"  {num} │ {line}")
    return "\n".join(result)


def _plain_diff(old_code: str, new_code: str) -> str:
    """Plain text diff without colors."""
    lines = []
    lines.append("  ─── Before ───")
    for line in old_code.split("\n"):
        lines.append(f"  - {line}")
    lines.append("  ─── After ───")
    for line in new_code.split("\n"):
        lines.append(f"  + {line}")
    return "\n".join(lines)


def _side_by_side_diff(old_code: str, new_code: str, width: int) -> str:
    """Render side-by-side diff with color coding."""
    RED_BG = "\033[41m"
    GREEN_BG = "\033[42m"
    RESET = "\033[0m"
    DIM = "\033[2m"

    half_width = (width - 3) // 2  # 3 for separator " │ "

    old_lines = old_code.split("\n")
    new_lines = new_code.split("\n")
    max_lines = max(len(old_lines), len(new_lines))

    result = []
    result.append(f"  {'─── Before ───'.ljust(half_width)} │ {'─── After ───'.ljust(half_width)}")

    for i in range(min(max_lines, 50)):  # Cap at 50 lines
        left = old_lines[i] if i < len(old_lines) else ""
        right = new_lines[i] if i < len(new_lines) else ""

        # Truncate long lines
        left_display = left[:half_width - 2]
        right_display = right[:half_width - 2]

        if left != right:
            left_fmt = f"{RED_BG}{left_display.ljust(half_width)}{RESET}"
            right_fmt = f"{GREEN_BG}{right_display.ljust(half_width)}{RESET}"
        else:
            left_fmt = f"{DIM}{left_display.ljust(half_width)}{RESET}"
            right_fmt = f"{DIM}{right_display.ljust(half_width)}{RESET}"

        result.append(f"  {left_fmt} │ {right_fmt}")

    if max_lines > 50:
        result.append(f"  ... ({max_lines - 50} more lines)")

    return "\n".join(result)


def _unified_diff(old_code: str, new_code: str) -> str:
    """Render unified diff with color coding."""
    RED = "\033[91m"
    GREEN = "\033[92m"
    RESET = "\033[0m"
    DIM = "\033[2m"

    import difflib

    old_lines = old_code.split("\n")
    new_lines = new_code.split("\n")

    diff = difflib.unified_diff(
        old_lines, new_lines,
        fromfile="before", tofile="after",
        lineterm=""
    )

    result = []
    line_count = 0
    for line in diff:
        if line_count >= 50:
            result.append(f"{DIM}  ... (truncated){RESET}")
            break
        if line.startswith("---") or line.startswith("+++"):
            result.append(f"{DIM}  {line}{RESET}")
        elif line.startswith("-"):
            result.append(f"{RED}  {line}{RESET}")
        elif line.startswith("+"):
            result.append(f"{GREEN}  {line}{RESET}")
        elif line.startswith("@@"):
            result.append(f"{DIM}  {line}{RESET}")
        else:
            result.append(f"  {line}")
        line_count += 1

    return "\n".join(result) if result else _plain_diff(old_code, new_code)
