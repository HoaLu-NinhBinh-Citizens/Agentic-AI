"""Completion command - display AI-powered code completions in terminal.

Usage:
    python -m src.interfaces.cli.main complete src/file.py --line 42 --col 10
    python -m src.interfaces.cli.main complete src/file.py --prefix "def hello"
    python -m src.interfaces.cli.main complete src/file.py --interactive
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Optional


def register(subparsers: argparse._SubParsersAction) -> None:
    """Register the completion command.

    Args:
        subparsers: Parent subparsers action from argparse
    """
    p = subparsers.add_parser(
        "complete",
        help="Get AI-powered code completions",
        description="Display code completions with preview and scoring",
    )
    p.add_argument(
        "file",
        type=Path,
        help="File to complete",
    )
    p.add_argument(
        "--line", "-l",
        type=int,
        default=None,
        help="Cursor line number (1-indexed)",
    )
    p.add_argument(
        "--col", "-c",
        type=int,
        default=0,
        help="Cursor column position",
    )
    p.add_argument(
        "--prefix", "-p",
        type=str,
        default="",
        help="Prefix text before cursor",
    )
    p.add_argument(
        "--suffix", "-s",
        type=str,
        default="",
        help="Suffix text after cursor",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Max completions to show (default: 5)",
    )
    p.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="Interactive selection mode",
    )
    p.add_argument(
        "--no-ai",
        action="store_true",
        help="Skip AI-powered completions (faster)",
    )
    p.set_defaults(handler=run_complete)


async def run_complete(args: argparse.Namespace) -> int:
    """Run completion with optional interactive display.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code (0 = success)
    """
    file_path = args.file

    # Validate file
    if not file_path.exists():
        print(f"Error: File not found: {file_path}", file=sys.stderr)
        return 1

    if not file_path.is_file():
        print(f"Error: Not a file: {file_path}", file=sys.stderr)
        return 1

    # Read file content
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"Error reading file: {e}", file=sys.stderr)
        return 1

    lines = content.split("\n")

    # Determine cursor position
    if args.line is not None:
        line_idx = args.line - 1  # Convert to 0-indexed
        if line_idx < 0 or line_idx >= len(lines):
            print(f"Error: Line {args.line} out of range", file=sys.stderr)
            return 1
        cursor_line = lines[line_idx]
        prefix = cursor_line[:args.col]
        suffix = cursor_line[args.col:]
    else:
        prefix = args.prefix or ""
        suffix = args.suffix or ""

    # Display header
    print(f"\n[ Completions for: {file_path} ]")
    print(f"  Prefix: {repr(prefix)}")
    print(f"  Suffix: {repr(suffix)}")
    print("-" * 60)

    # Get completions
    completions = await _get_completions(
        file_path=str(file_path),
        prefix=prefix,
        suffix=suffix,
        language=file_path.suffix.lstrip("."),
        limit=args.limit,
        use_ai=not args.no_ai,
    )

    if not completions:
        print("No completions available for this context.")
        return 0

    # Display completions
    _display_completions(completions, interactive=args.interactive)

    print()
    if args.interactive:
        print("=" * 60)
        print("Tip: Use Tab or number [1-N] to select, Esc to cancel")
    else:
        print("=" * 60)
        print(f"Tip: Use --interactive for selection mode")

    return 0


async def _get_completions(
    file_path: str,
    prefix: str,
    suffix: str,
    language: str,
    limit: int = 5,
    use_ai: bool = True,
) -> list[dict]:
    """Get completions from completion engine.

    Args:
        file_path: Current file path
        prefix: Text before cursor
        suffix: Text after cursor
        language: File language/extension
        limit: Max completions to return
        use_ai: Whether to include AI completions

    Returns:
        List of completion dicts with text, score, source, label, detail
    """
    try:
        from src.infrastructure.codegen.completion_engine import CompletionEngine
    except ImportError:
        return _get_fallback_completions(prefix, language)

    engine = CompletionEngine()
    cursor_line = 1
    cursor_col = len(prefix)

    try:
        completions = await engine.get_completions(
            file_path=file_path,
            cursor_line=cursor_line,
            cursor_col=cursor_col,
            prefix=prefix,
            trigger=None,
        )

        return [
            {
                "text": c.text,
                "label": c.label,
                "detail": c.detail,
                "score": c.score,
                "source": c.source,
            }
            for c in completions[:limit]
        ]
    except Exception as e:
        print(f"Warning: Completion engine error: {e}", file=sys.stderr)
        return _get_fallback_completions(prefix, language)


def _get_fallback_completions(prefix: str, language: str) -> list[dict]:
    """Get basic completions without AI.

    Args:
        prefix: Text prefix
        language: Programming language

    Returns:
        List of basic completions
    """
    completions = []

    templates = {
        "py": [
            ("def ", "def function_name(params):", 0.9),
            ("async ", "async def function(params):", 0.85),
            ("class ", "class ClassName:", 0.85),
            ("if ", "if condition:", 0.8),
            ("for ", "for item in iterable:", 0.8),
            ("with ", "with open(path) as f:", 0.75),
            ("import ", "from module import name", 0.7),
        ],
        "js": [
            ("const ", "const name = value;", 0.9),
            ("let ", "let name = value;", 0.85),
            ("function ", "function name(params) {}", 0.85),
            ("async ", "async function name(params) {}", 0.8),
            ("if ", "if (condition) {}", 0.8),
            ("for ", "for (let i = 0; i < n; i++) {}", 0.75),
        ],
        "ts": [
            ("const ", "const name: Type = value;", 0.9),
            ("interface ", "interface IName {}", 0.85),
            ("type ", "type Name = Type;", 0.85),
            ("function ", "function name(params): ReturnType {}", 0.8),
        ],
        "c": [
            ("#i", "#include <header.h>", 0.9),
            ("if ", "if (condition) {}", 0.8),
            ("for ", "for (int i = 0; i < n; i++) {}", 0.8),
            ("while ", "while (condition) {}", 0.75),
            ("switch", "switch (value) {\n  case :\n    break;\n  default:\n    break;\n}", 0.7),
        ],
    }

    lang_templates = templates.get(language.lower(), templates["py"])

    for match, text, score in lang_templates:
        if prefix.lower().startswith(match.lower()) or match.startswith(prefix):
            completions.append({
                "text": text,
                "label": text.split("\n")[0][:40],
                "detail": f"Template ({language})",
                "score": score,
                "source": "template",
            })

    return completions


def _display_completions(completions: list[dict], interactive: bool = False) -> None:
    """Display completions to console.

    Args:
        completions: List of completion dicts
        interactive: Whether to enable interactive selection hints
    """
    for i, comp in enumerate(completions, 1):
        score = comp.get("score", 0)
        source = comp.get("source", "unknown")
        label = comp.get("label", "")
        detail = comp.get("detail", "")
        text = comp.get("text", "")

        print(f"\n[{i}] Score: {score:.2f} | Source: {source}")
        print(f"    Label: {label}")
        if detail:
            print(f"    Detail: {detail}")

        # Show preview
        preview = text[:80] + "..." if len(text) > 80 else text
        print(f"    Preview: {repr(preview)}")

        # Show full for short completions
        if len(text) <= 150 and "\n" not in text:
            print(f"    Full: {text}")


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.

    Args:
        argv: Optional command-line arguments

    Returns:
        Exit code
    """
    parser = argparse.ArgumentParser(
        prog="ai-support complete",
        description="AI-powered code completions",
    )
    sub = parser.add_subparsers(dest="subcommand")
    register(sub)
    args = parser.parse_args(argv)

    if hasattr(args, "handler"):
        return asyncio.run(args.handler(args))
    return 0


if __name__ == "__main__":
    sys.exit(main())
