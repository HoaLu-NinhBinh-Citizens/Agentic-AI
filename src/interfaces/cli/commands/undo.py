"""Undo/redo command for AI_SUPPORT.
Provides multi-file undo/redo capabilities.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path

from src.infrastructure.refactoring.undo_manager import UndoManager, Change


def register(subparsers) -> None:
    """Register the undo command and subcommands.
    
    Args:
        subparsers: ArgumentParser subparsers
    """
    p = subparsers.add_parser(
        "undo",
        help="Undo/redo changes",
        description="Multi-file undo/redo manager for AI_SUPPORT",
    )
    sub = p.add_subparsers(dest="undo_cmd", required=True)
    
    # Undo command
    undo_cmd = sub.add_parser("undo", help="Undo last change")
    undo_cmd.add_argument(
        "--steps",
        type=int,
        default=1,
        help="Number of steps to undo (default: 1)"
    )
    undo_cmd.set_defaults(handler=undo_handler)
    
    # Redo command
    redo_cmd = sub.add_parser("redo", help="Redo last undone change")
    redo_cmd.add_argument(
        "--steps",
        type=int,
        default=1,
        help="Number of steps to redo (default: 1)"
    )
    redo_cmd.set_defaults(handler=redo_handler)
    
    # History command
    history_cmd = sub.add_parser("history", help="Show undo history")
    history_cmd.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Number of history entries to show (default: 10)"
    )
    history_cmd.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON"
    )
    history_cmd.set_defaults(handler=history_handler)
    
    # Clear command
    clear_cmd = sub.add_parser("clear", help="Clear undo history")
    clear_cmd.add_argument(
        "--force",
        action="store_true",
        help="Skip confirmation prompt"
    )
    clear_cmd.set_defaults(handler=clear_handler)
    
    # Status command
    status_cmd = sub.add_parser("status", help="Show undo/redo status")
    status_cmd.set_defaults(handler=status_handler)


async def undo_handler(args: argparse.Namespace) -> int:
    """Handle undo command.
    
    Args:
        args: Parsed command-line arguments
        
    Returns:
        Exit code
    """
    try:
        manager = UndoManager(Path.cwd())
        
        if not manager.can_undo():
            print("Nothing to undo.")
            return 1
        
        print(f"Undoing last {args.steps} checkpoint(s)...")
        
        for i in range(args.steps):
            result = manager.undo()
            if result:
                print(f"  Undone: {result.description}")
                print(f"  Files: {len(result.changes)}")
                for change in result.changes:
                    print(f"    - {change.path}")
            else:
                print(f"  Nothing more to undo after {i} step(s).")
                break
        
        return 0
        
    except Exception as e:
        print(f"Undo error: {e}", file=sys.stderr)
        return 1


async def redo_handler(args: argparse.Namespace) -> int:
    """Handle redo command.
    
    Args:
        args: Parsed command-line arguments
        
    Returns:
        Exit code
    """
    try:
        manager = UndoManager(Path.cwd())
        
        if not manager.can_redo():
            print("Nothing to redo.")
            return 1
        
        print(f"Redoing last {args.steps} checkpoint(s)...")
        
        for i in range(args.steps):
            result = manager.redo()
            if result:
                print(f"  Redone: {result.description}")
                print(f"  Files: {len(result.changes)}")
                for change in result.changes:
                    print(f"    - {change.path}")
            else:
                print(f"  Nothing more to redo after {i} step(s).")
                break
        
        return 0
        
    except Exception as e:
        print(f"Redo error: {e}", file=sys.stderr)
        return 1


async def history_handler(args: argparse.Namespace) -> int:
    """Handle history command.
    
    Args:
        args: Parsed command-line arguments
        
    Returns:
        Exit code
    """
    try:
        import json
        
        manager = UndoManager(Path.cwd())
        history = manager.get_history()
        
        if not history:
            print("No history yet.")
            return 0
        
        if args.json:
            # JSON output
            output = history[:args.limit]
            print(json.dumps(output, indent=2))
            return 0
        
        # Human-readable output
        print(f"\n{'='*60}")
        print("Undo History")
        print(f"{'='*60}\n")
        
        print(f"Current position: {manager.current_index + 1} of {len(history)}")
        print()
        
        for i, item in enumerate(history[:args.limit]):
            marker = ">>>" if item["is_current"] else "   "
            timestamp = datetime.fromisoformat(item["timestamp"])
            time_str = timestamp.strftime("%H:%M:%S")
            
            print(f"{marker} [{i}] {time_str} - {item['description']}")
            print(f"       {item['file_count']} file(s)")
            
            if item["is_current"]:
                print("       (current)")
            print()
        
        if len(history) > args.limit:
            print(f"... and {len(history) - args.limit} more entries")
        
        # Show available operations
        print(f"\nCommands:")
        if manager.can_undo():
            print("  ai-support undo undo    - Undo last change")
        if manager.can_redo():
            print("  ai-support undo redo   - Redo last undone")
        print("  ai-support undo status - Check status")
        
        return 0
        
    except Exception as e:
        print(f"History error: {e}", file=sys.stderr)
        return 1


async def clear_handler(args: argparse.Namespace) -> int:
    """Handle clear command.
    
    Args:
        args: Parsed command-line arguments
        
    Returns:
        Exit code
    """
    try:
        manager = UndoManager(Path.cwd())
        
        if not args.force:
            print("This will clear ALL undo history. Continue? (y/N): ", end="")
            response = input().strip().lower()
            if response != 'y':
                print("Cancelled.")
                return 1
        
        manager.clear_history()
        print("Undo history cleared.")
        
        return 0
        
    except Exception as e:
        print(f"Clear error: {e}", file=sys.stderr)
        return 1


async def status_handler(args: argparse.Namespace) -> int:
    """Handle status command.
    
    Args:
        args: Parsed command-line arguments
        
    Returns:
        Exit code
    """
    try:
        manager = UndoManager(Path.cwd())
        history = manager.get_history()
        
        print(f"\n{'='*40}")
        print("Undo/Redo Status")
        print(f"{'='*40}\n")
        
        print(f"Total checkpoints: {len(history)}")
        print(f"Current position:  {manager.current_index + 1}")
        print(f"Can undo:         {'Yes' if manager.can_undo() else 'No'}")
        print(f"Can redo:         {'Yes' if manager.can_redo() else 'No'}")
        print(f"Max checkpoints:  {manager.max_checkpoints}")
        
        if history:
            print(f"\nLatest checkpoint:")
            latest = history[-1]
            print(f"  ID:          {latest['id']}")
            print(f"  Description: {latest['description']}")
            print(f"  Files:       {latest['file_count']}")
        
        return 0
        
    except Exception as e:
        print(f"Status error: {e}", file=sys.stderr)
        return 1


def main() -> int:
    """Entry point for the undo command."""
    parser = argparse.ArgumentParser(description="Undo/redo manager")
    register(parser.add_subparsers())
    args = parser.parse_args()
    return asyncio.run(args.handler(args))


if __name__ == "__main__":
    sys.exit(main())
