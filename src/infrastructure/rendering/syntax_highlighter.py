"""Syntax highlighting for code output using Pygments."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from dataclasses import dataclass


logger = logging.getLogger(__name__)

# Try to import pygments, provide fallback if not available
try:
    from pygments import highlight
    from pygments.lexers import get_lexer_by_name, guess_lexer
    from pygments.formatters import Terminal256Formatter, HtmlFormatter
    from pygments.token import Token

    PYGMENTS_AVAILABLE = True
except ImportError:
    PYGMENTS_AVAILABLE = False
    logger.warning("pygments not installed. Install with: pip install pygments")


# ANSI color codes for terminal
ANSI_COLORS = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    # Colors
    "black": "\033[30m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "magenta": "\033[35m",
    "cyan": "\033[36m",
    "white": "\033[37m",
    # Light colors
    "light_red": "\033[91m",
    "light_green": "\033[92m",
    "light_yellow": "\033[93m",
    "light_blue": "\033[94m",
    "light_magenta": "\033[95m",
    "light_cyan": "\033[96m",
}


# Keyword sets for different languages
LANGUAGE_KEYWORDS = {
    "python": [
        "def", "class", "if", "else", "elif", "for", "while", "try", "except",
        "finally", "with", "return", "yield", "import", "from", "as", "raise",
        "pass", "break", "continue", "lambda", "and", "or", "not", "in", "is",
        "True", "False", "None", "async", "await", "global", "nonlocal",
        "assert", "del", "assert", "match", "case",
    ],
    "javascript": [
        "function", "const", "let", "var", "if", "else", "for", "while",
        "try", "catch", "finally", "return", "class", "extends", "new",
        "this", "import", "export", "from", "async", "await", "typeof",
        "instanceof", "delete", "void", "switch", "case", "default", "break",
        "continue", "throw", "yield", "async",
    ],
    "typescript": [
        "function", "const", "let", "var", "if", "else", "for", "while",
        "interface", "type", "enum", "class", "extends", "implements",
        "public", "private", "protected", "async", "await", "import", "export",
        "namespace", "module", "declare", "abstract", "readonly", "as", "is",
        "keyof", "infer", "never", "unknown", "any",
    ],
    "c": [
        "auto", "break", "case", "char", "const", "continue", "default", "do",
        "double", "else", "enum", "extern", "float", "for", "goto", "if",
        "int", "long", "register", "return", "short", "signed", "sizeof",
        "static", "struct", "switch", "typedef", "union", "unsigned", "void",
        "volatile", "while", "NULL",
    ],
    "cpp": [
        "alignas", "alignof", "and", "and_eq", "asm", "auto", "bitand", "bitor",
        "bool", "break", "case", "catch", "char", "char8_t", "char16_t",
        "char32_t", "class", "compl", "concept", "const", "consteval",
        "constexpr", "constinit", "const_cast", "continue", "co_await",
        "co_return", "co_yield", "decltype", "default", "delete", "do", "double",
        "dynamic_cast", "else", "enum", "explicit", "export", "extern", "false",
        "float", "for", "friend", "goto", "if", "inline", "int", "long",
        "mutable", "namespace", "new", "noexcept", "not", "not_eq", "nullptr",
        "operator", "or", "or_eq", "private", "protected", "public",
        "register", "reinterpret_cast", "requires", "return", "short",
        "signed", "sizeof", "static", "static_assert", "static_cast", "struct",
        "switch", "template", "this", "thread_local", "throw", "true", "try",
        "typedef", "typeid", "typename", "union", "unsigned", "using",
        "virtual", "void", "volatile", "wchar_t", "while", "xor", "xor_eq",
    ],
}


class SyntaxHighlighter:
    """Add syntax highlighting to code blocks.

    Uses Pygments for syntax highlighting with ANSI colors for terminal output.
    Falls back to manual highlighting if Pygments is not available.
    """

    # Theme colors for terminal
    THEME = {
        Token.Keyword: ANSI_COLORS["cyan"],
        Token.Keyword.Constant: ANSI_COLORS["cyan"],
        Token.Keyword.Declaration: ANSI_COLORS["cyan"],
        Token.Name.Builtin: ANSI_COLORS["cyan"],
        Token.Name.Function: ANSI_COLORS["green"],
        Token.Name.Class: ANSI_COLORS["green"],
        Token.Name.Decorator: ANSI_COLORS["magenta"],
        Token.String: ANSI_COLORS["yellow"],
        Token.Number: ANSI_COLORS["magenta"],
        Token.Comment: ANSI_COLORS["dim"] + ANSI_COLORS["white"],
        Token.Operator: ANSI_COLORS["white"],
        Token.Punctuation: ANSI_COLORS["white"],
        Token.Generic: ANSI_COLORS["white"],
    }

    def __init__(self, theme: str = "default"):
        """Initialize highlighter.

        Args:
            theme: Color theme name ('default', 'monokai', 'github')
        """
        self.theme = theme
        self._formatter = None

        if PYGMENTS_AVAILABLE:
            self._formatter = Terminal256Formatter(style="monokai")

    def highlight(self, code: str, language: str = "") -> str:
        """Highlight code with syntax colors.

        Args:
            code: Source code to highlight
            language: Programming language (python, javascript, etc.)

        Returns:
            Highlighted code string with ANSI colors
        """
        if not PYGMENTS_AVAILABLE:
            return code  # Return plain code if pygments not available

        try:
            # Try to get lexer by language
            if language:
                try:
                    lexer = get_lexer_by_name(language)
                except Exception:
                    lexer = guess_lexer(code)
            else:
                lexer = guess_lexer(code)

            # Highlight with formatter
            if self._formatter:
                return highlight(code, lexer, self._formatter)
            else:
                # Fallback to manual highlighting
                return self._manual_highlight(code, language)

        except Exception as e:
            logger.debug(f"Highlighting failed: {e}")
            return code

    def _manual_highlight(self, code: str, language: str) -> str:
        """Manual fallback highlighting without pygments."""
        result = code
        keywords = LANGUAGE_KEYWORDS.get(language, LANGUAGE_KEYWORDS.get("python", []))

        # Highlight keywords
        for word in keywords:
            pattern = rf"\b({re.escape(word)})\b"
            result = re.sub(
                pattern,
                f"{ANSI_COLORS['cyan']}\\1{ANSI_COLORS['reset']}",
                result,
            )

        # Highlight strings (double and single quotes)
        string_pattern = r'("""|[\'"])(?:(?!\1)[^\\]|\\.)*\1'
        result = re.sub(
            string_pattern,
            f"{ANSI_COLORS['yellow']}\\0{ANSI_COLORS['reset']}",
            result,
        )

        # Highlight numbers
        number_pattern = r"\b(\d+\.?\d*(?:[eE][+-]?\d+)?)\b"
        result = re.sub(
            number_pattern,
            f"{ANSI_COLORS['magenta']}\\1{ANSI_COLORS['reset']}",
            result,
        )

        # Highlight comments
        if language in ("python", "c", "cpp"):
            comment_pattern = r"(#.*)$"
            result = re.sub(
                comment_pattern,
                f"{ANSI_COLORS['dim']}\\1{ANSI_COLORS['reset']}",
                result,
                flags=re.MULTILINE,
            )
        elif language in ("javascript", "typescript"):
            comment_pattern = r"(//.*)$"
            result = re.sub(
                comment_pattern,
                f"{ANSI_COLORS['dim']}\\1{ANSI_COLORS['reset']}",
                result,
                flags=re.MULTILINE,
            )

        return result

    def format_finding(
        self,
        finding: dict,
        context: "CodeContext",
    ) -> str:
        """Format a finding with highlighted code.

        Args:
            finding: The finding to format
            context: Code context with surrounding code

        Returns:
            Formatted string with highlighted code
        """
        lines = []

        # Header
        rule_id = finding.get("rule_id", "UNKNOWN")
        message = finding.get("message", "No message")
        lines.append(f"## {rule_id}: {message}")
        lines.append("")
        lines.append(f"**File:** `{finding.get('file', 'unknown')}:{finding.get('line', '?')}`")

        severity = finding.get("severity", "info")
        if isinstance(severity, str):
            lines.append(f"**Severity:** {severity}")
        else:
            lines.append(f"**Severity:** {severity}")

        confidence = finding.get("confidence")
        if confidence:
            lines.append(f"**Confidence:** {confidence:.0%}")
        lines.append("")

        # Old code (problematic)
        old_code = finding.get("old_code")
        if old_code:
            lines.append("### Before (problematic)")
            lines.append("```" + context.language)
            lines.append(self.highlight(old_code, context.language))
            lines.append("```")
            lines.append("")

        # New code (fixed)
        new_code = finding.get("new_code")
        if new_code:
            lines.append("### After (fixed)")
            lines.append("```" + context.language)
            lines.append(self.highlight(new_code, context.language))
            lines.append("```")
            lines.append("")

        # Explanation
        explanation = finding.get("explanation")
        if explanation:
            lines.append(f"**Explanation:** {explanation}")

        return "\n".join(lines)

    def wrap_in_markdown(self, code: str, language: str = "") -> str:
        """Wrap highlighted code in markdown code block.

        Args:
            code: Source code
            language: Language for syntax highlighting

        Returns:
            Markdown formatted code block
        """
        highlighted = self.highlight(code, language)
        return f"```{language}\n{highlighted}\n```"


class CodeContext:
    """Context information for formatting findings."""

    def __init__(
        self,
        file_path: str,
        language: str = "",
        start_line: int = 1,
        end_line: int = 1,
        source: str = "",
    ):
        self.file = file_path
        self.language = language or self._detect_language(file_path)
        self.start_line = start_line
        self.end_line = end_line
        self.source = source

    @staticmethod
    def _detect_language(file_path: str) -> str:
        """Detect programming language from file extension."""
        ext_map = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".jsx": "javascript",
            ".tsx": "typescript",
            ".c": "c",
            ".cpp": "cpp",
            ".cc": "cpp",
            ".cxx": "cpp",
            ".h": "c",
            ".hpp": "cpp",
            ".java": "java",
            ".rs": "rust",
            ".go": "go",
            ".rb": "ruby",
            ".swift": "swift",
            ".kt": "kotlin",
            ".scala": "scala",
            ".cs": "csharp",
            ".php": "php",
            ".sh": "bash",
            ".bash": "bash",
            ".zsh": "bash",
            ".ps1": "powershell",
            ".sql": "sql",
            ".html": "html",
            ".htm": "html",
            ".css": "css",
            ".scss": "scss",
            ".json": "json",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".xml": "xml",
            ".md": "markdown",
            ".rst": "rst",
            ".dockerfile": "dockerfile",
            ".toml": "toml",
            ".ini": "ini",
            ".cfg": "ini",
        }
        ext = Path(file_path).suffix.lower()
        return ext_map.get(ext, "text")


class HtmlSyntaxHighlighter(SyntaxHighlighter):
    """HTML syntax highlighter for web output."""

    def __init__(self):
        super().__init__()
        if PYGMENTS_AVAILABLE:
            self._formatter = HtmlFormatter(style="monokai", full=True)

    def highlight_html(self, code: str, language: str = "") -> str:
        """Highlight code and wrap in HTML."""
        if not PYGMENTS_AVAILABLE:
            return f"<pre><code>{code}</code></pre>"

        try:
            if language:
                lexer = get_lexer_by_name(language)
            else:
                lexer = guess_lexer(code)

            return highlight(code, lexer, self._formatter)
        except Exception:
            return f"<pre><code>{code}</code></pre>"
