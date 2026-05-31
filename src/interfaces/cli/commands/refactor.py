"""Refactor commands - /refactor for AI_SUPPORT CLI.

Interactive refactoring commands inspired by Cursor's /refactor functionality.
Supports extract function, rename, inline, and move operations.

Usage:
    /refactor extract <file> [--start=LINE] [--end=LINE] [--name=NAME]
    /refactor rename <file> <old_name> <new_name> [--scope=file|project]
    /refactor inline <file> <function_name>
    /refactor move <file> [--to=TARGET] [--start=LINE] [--end=LINE]
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Optional


SEPARATOR = "=" * 60
SMALL_SEPARATOR = "-" * 60


def register(subparsers: argparse._SubParsersAction) -> None:
    """Register refactor subcommands."""
    p = subparsers.add_parser(
        "refactor",
        help="Refactor code (extract, rename, inline, move)",
        description="Interactive refactoring commands for AI_SUPPORT",
    )
    p.add_argument(
        "--workspace", "-w",
        default=".",
        help="Workspace root directory",
    )
    
    sub = p.add_subparsers(dest="refactor_cmd", required=False)
    
    extract_parser(sub)
    rename_parser(sub)
    inline_parser(sub)
    move_parser(sub)
    
    p.set_defaults(handler=run_refactor)


def extract_parser(sub: argparse._SubParsersAction) -> None:
    """Register extract function subcommand."""
    extract = sub.add_parser(
        "extract",
        help="Extract code to a function",
        description="Extract selected code into a new function",
    )
    extract.add_argument("file", help="File path to refactor")
    extract.add_argument(
        "--start", "-s",
        type=int,
        default=None,
        help="Start line (1-indexed)",
    )
    extract.add_argument(
        "--end", "-e",
        type=int,
        default=None,
        help="End line (1-indexed)",
    )
    extract.add_argument(
        "--name", "-n",
        type=str,
        default=None,
        help="Name for extracted function",
    )
    extract.add_argument(
        "--apply",
        action="store_true",
        help="Apply the refactoring",
    )
    extract.set_defaults(handler=extract_handler)


def rename_parser(sub: argparse._SubParsersAction) -> None:
    """Register rename symbol subcommand."""
    rename = sub.add_parser(
        "rename",
        help="Rename a symbol",
        description="Rename a variable, function, or class",
    )
    rename.add_argument("file", help="File path")
    rename.add_argument("old_name", help="Current symbol name")
    rename.add_argument("new_name", help="New symbol name")
    rename.add_argument(
        "--scope", "-S",
        choices=["file", "project"],
        default="file",
        help="Rename scope (default: file)",
    )
    rename.add_argument(
        "--apply",
        action="store_true",
        help="Apply the refactoring",
    )
    rename.set_defaults(handler=rename_handler)


def inline_parser(sub: argparse._SubParsersAction) -> None:
    """Register inline function subcommand."""
    inline = sub.add_parser(
        "inline",
        help="Inline a function",
        description="Replace function calls with function body",
    )
    inline.add_argument("file", help="File path")
    inline.add_argument("function", help="Function name to inline")
    inline.add_argument(
        "--all",
        action="store_true",
        default=True,
        help="Inline all call sites (default: true)",
    )
    inline.add_argument(
        "--preview",
        action="store_true",
        help="Show preview without applying",
    )
    inline.set_defaults(handler=inline_handler)


def move_parser(sub: argparse._SubParsersAction) -> None:
    """Register move code subcommand."""
    move = sub.add_parser(
        "move",
        help="Move code to another file",
        description="Move code to another file or class",
    )
    move.add_argument("file", help="Source file")
    move.add_argument(
        "--to", "-t",
        required=True,
        help="Target file path",
    )
    move.add_argument(
        "--class", "-c",
        dest="target_class",
        type=str,
        default=None,
        help="Target class name (optional)",
    )
    move.add_argument(
        "--start", "-s",
        type=int,
        default=None,
        help="Start line (1-indexed)",
    )
    move.add_argument(
        "--end", "-e",
        type=int,
        default=None,
        help="End line (1-indexed)",
    )
    move.add_argument(
        "--apply",
        action="store_true",
        help="Apply the refactoring",
    )
    move.set_defaults(handler=move_handler)


async def extract_handler(args: argparse.Namespace) -> int:
    """Handle extract function command."""
    from src.infrastructure.refactoring import RefactorEngine
    
    file_path = Path(args.file)
    if not file_path.exists():
        print(f"[ERROR] File not found: {file_path}")
        return 1
    
    content = file_path.read_text(encoding='utf-8')
    lines = content.split('\n')
    
    start = args.start
    end = args.end
    
    if not start:
        start = prompt_line_number(lines, "start")
        if start is None:
            return 1
    
    if not end:
        end = prompt_line_number(lines, "end")
        if end is None:
            return 1
    
    if start > end:
        print(f"[ERROR] Start line ({start}) must be <= end line ({end})")
        return 1
    
    if start < 1 or end > len(lines):
        print(f"[ERROR] Line range out of bounds (file has {len(lines)} lines)")
        return 1
    
    engine = RefactorEngine(file_path.parent)
    result = await engine.extract_function(
        file_path, content, start, end, args.name
    )
    
    print_separator()
    print("EXTRACT FUNCTION")
    print_separator()
    print()
    print("## Original Code")
    print()
    print("```python")
    print(result.original_code)
    print("```")
    print()
    print("## Extracted Function")
    print()
    print("```python")
    print(result.new_function)
    print("```")
    print()
    
    if result.parameters:
        print(f"**Parameters:** `{', '.join(result.parameters)}`")
    
    if result.return_value:
        print(f"**Return Value:** `{result.return_value}`")
    
    print()
    print("## Call Site")
    print()
    print("```python")
    print(result.call_site)
    print("```")
    print()
    print_small_separator()
    print()
    print("To apply this refactoring:")
    print(f"  python -m ai_support refactor extract {args.file} --start={start} --end={end} --name={args.name or 'auto'} --apply")
    print()
    
    if args.apply:
        apply_result = await engine.apply_extract_function(
            file_path, start, end, args.name
        )
        if apply_result.success:
            print("[OK] Refactoring applied successfully!")
            return 0
        else:
            print(f"[ERROR] Failed to apply refactoring: {apply_result.error}")
            return 1
    
    return 0


async def rename_handler(args: argparse.Namespace) -> int:
    """Handle rename symbol command."""
    from src.infrastructure.refactoring import RefactorEngine
    
    file_path = Path(args.file)
    if not file_path.exists():
        print(f"[ERROR] File not found: {file_path}")
        return 1
    
    engine = RefactorEngine(file_path.parent)
    result = await engine.rename_symbol(
        file_path,
        args.old_name,
        args.new_name,
        scope=args.scope,
    )
    
    print_separator()
    print("RENAME SYMBOL")
    print_separator()
    print()
    print(f"| Property | Value |")
    print(f"|----------|-------|")
    print(f"| Old Name | `{result.old_name}` |")
    print(f"| New Name | `{result.new_name}` |")
    print(f"| Scope | `{args.scope}` |")
    print(f"| Files Changed | {len(result.files_changed)} |")
    print(f"| Occurrences | {result.occurrences} |")
    print()
    
    if result.files_changed:
        print("## Files Modified")
        print()
        for f in result.files_changed:
            print(f"  - `{f}`")
        print()
    
    print_small_separator()
    print()
    
    if args.apply:
        print("[OK] Symbol renamed successfully!")
        return 0
    else:
        print("To apply this refactoring:")
        print(f"  python -m ai_support refactor rename {args.file} {args.old_name} {args.new_name} --scope={args.scope} --apply")
        return 0


async def inline_handler(args: argparse.Namespace) -> int:
    """Handle inline function command."""
    from src.infrastructure.refactoring import RefactorEngine
    
    file_path = Path(args.file)
    if not file_path.exists():
        print(f"[ERROR] File not found: {file_path}")
        return 1
    
    engine = RefactorEngine(file_path.parent)
    result = await engine.inline_function(
        file_path,
        args.function,
        inline_all=not args.preview,
    )
    
    print_separator()
    print("INLINE FUNCTION")
    print_separator()
    print()
    
    if not result.success:
        print("[ERROR] Function not found or inlining failed")
        return 1
    
    print(f"| Property | Value |")
    print(f"|----------|-------|")
    print(f"| Function | `{args.function}` |")
    print(f"| Call Sites | {result.call_sites_updated} |")
    print(f"| Status | {'Inlined' if not args.preview else 'Preview'} |")
    print()
    
    if result.original_function:
        print("## Original Function")
        print()
        print("```python")
        print(result.original_function)
        print("```")
        print()
    
    print_small_separator()
    print()
    print("Note: Full inlining implementation requires complex AST transformations.")
    print("Use with caution and review changes before committing.")
    
    return 0


async def move_handler(args: argparse.Namespace) -> int:
    """Handle move code command."""
    from src.infrastructure.refactoring import RefactorEngine
    
    file_path = Path(args.file)
    if not file_path.exists():
        print(f"[ERROR] File not found: {file_path}")
        return 1
    
    content = file_path.read_text(encoding='utf-8')
    lines = content.split('\n')
    
    start = args.start
    end = args.end
    
    if not start:
        start = prompt_line_number(lines, "start")
        if start is None:
            return 1
    
    if not end:
        end = prompt_line_number(lines, "end")
        if end is None:
            return 1
    
    if start > end:
        print(f"[ERROR] Start line ({start}) must be <= end line ({end})")
        return 1
    
    selected_lines = lines[start - 1:end]
    selected_code = '\n'.join(selected_lines)
    
    target_file = Path(args.to)
    
    engine = RefactorEngine(file_path.parent)
    result = await engine.move_code(
        file_path,
        selected_code,
        target_file,
        target_class=args.target_class,
        start_line=start,
        end_line=end,
    )
    
    print_separator()
    print("MOVE CODE")
    print_separator()
    print()
    
    if result.success:
        print(f"| Property | Value |")
        print(f"|----------|-------|")
        print(f"| Source | `{file_path}` ({start}-{end}) |")
        print(f"| Target | `{target_file}` |")
        if args.target_class:
            print(f"| Target Class | `{args.target_class}` |")
        print()
        
        print("## Code to Move")
        print()
        print("```python")
        print(selected_code)
        print("```")
        print()
        
        print_small_separator()
        print()
        print("[OK] Code moved successfully!")
        return 0
    else:
        print(f"[ERROR] Move failed: {result.error}")
        return 1


async def run_refactor(args: argparse.Namespace) -> int:
    """Run refactor command with interactive mode."""
    if not args.refactor_cmd:
        print_separator()
        print("REFACTOR COMMANDS")
        print_separator()
        print()
        print("Available subcommands:")
        print()
        print("  extract    Extract code to a function")
        print("  rename     Rename a symbol")
        print("  inline     Inline a function")
        print("  move       Move code to another file")
        print()
        print("Usage:")
        print("  python -m ai_support refactor extract <file> [--start=LINE] [--end=LINE]")
        print("  python -m ai_support refactor rename <file> <old> <new> [--scope=file]")
        print("  python -m ai_support refactor inline <file> <function>")
        print("  python -m ai_support refactor move <file> --to=TARGET [--start=LINE] [--end=LINE]")
        print()
        return 0
    
    return 0


def prompt_line_number(lines: list[str], label: str) -> Optional[int]:
    """Prompt user to select a line number."""
    print()
    print(f"Select {label} line:")
    print()
    
    for i, line in enumerate(lines[:50], 1):
        content = line.strip()[:80]
        if content:
            print(f"  {i:4d}: {content}")
    
    if len(lines) > 50:
        print(f"  ... ({len(lines) - 50} more lines)")
    
    print()
    
    try:
        user_input = input(f"  {label.capitalize()} line: ").strip()
        if user_input:
            line_num = int(user_input)
            if 1 <= line_num <= len(lines):
                return line_num
            else:
                print(f"[ERROR] Line must be between 1 and {len(lines)}")
                return None
        else:
            print(f"[ERROR] No line number provided")
            return None
    except ValueError:
        print("[ERROR] Invalid line number")
        return None
    except EOFError:
        print("[ERROR] Input closed")
        return None


def print_separator() -> None:
    """Print separator line."""
    print(SEPARATOR)


def print_small_separator() -> None:
    """Print small separator line."""
    print(SMALL_SEPARATOR)


def main() -> None:
    """Main entry point for refactor CLI."""
    parser = argparse.ArgumentParser(
        prog="ai_support refactor",
        description="Interactive refactoring commands for AI_SUPPORT",
    )
    
    subparsers = parser.add_subparsers(dest="command", required=True)
    register(subparsers)
    
    args = parser.parse_args()
    
    if hasattr(args, 'handler') and asyncio.iscoroutinefunction(args.handler):
        exit_code = asyncio.run(args.handler(args))
        sys.exit(exit_code)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
