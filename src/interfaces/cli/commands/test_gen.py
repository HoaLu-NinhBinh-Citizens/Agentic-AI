"""Test generation command - /test for AI_SUPPORT CLI.

This command generates unit tests for Python functions and classes using AST analysis.

Usage:
    ai-support test src/my_module.py
    ai-support test src/my_module.py --symbol MyFunction
    ai-support test src/my_module.py --symbol MyClass --framework unittest
    ai-support test src/my_module.py --apply
    ai-support test src/my_module.py --symbol MyFunction --apply

Supports:
    - pytest (default)
    - unittest
    - doctest
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Optional

def register(subparsers: argparse._SubParsersAction) -> None:
    """Register the test generation command."""
    p = subparsers.add_parser(
        "test",
        help="Generate unit tests for a Python file or symbol",
        description="Generate pytest/unittest tests from Python code using AST analysis",
    )
    p.add_argument(
        "file",
        help="Python file to generate tests for",
    )
    p.add_argument(
        "--symbol", "-s",
        dest="symbol",
        help="Function or class name to generate tests for (auto-detect if not specified)",
    )
    p.add_argument(
        "--framework", "-f",
        choices=["pytest", "unittest", "doctest"],
        default="pytest",
        help="Test framework to use (default: pytest)",
    )
    p.add_argument(
        "--output", "-o",
        dest="output",
        help="Output file for generated tests (default: test_<original_file>.py)",
    )
    p.add_argument(
        "--apply",
        action="store_true",
        help="Write generated tests to output file",
    )
    p.add_argument(
        "--no-fixtures",
        dest="no_fixtures",
        action="store_true",
        help="Don't include pytest fixtures",
    )
    p.add_argument(
        "--no-edge-cases",
        dest="no_edge_cases",
        action="store_true",
        help="Don't generate edge case tests",
    )
    p.add_argument(
        "--workspace", "-w",
        default=".",
        help="Workspace root directory (default: current directory)",
    )
    p.set_defaults(handler=run_test_command)


async def run_test_command(args: argparse.Namespace) -> int:
    """Run the test generation command."""
    return await cmd_test(args)


async def cmd_test(args: argparse.Namespace) -> int:
    """Generate unit tests for a Python file.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code (0 for success, 1 for error)
    """
    from src.infrastructure.testing.test_generator import TestGenerator

    file_path = Path(args.file)
    workspace_root = Path(args.workspace)

    # Validate file
    if not file_path.exists():
        print(f"Error: File not found: {file_path}", file=sys.stderr)
        return 1

    if file_path.suffix != ".py":
        print(f"Warning: File does not have .py extension: {file_path}", file=sys.stderr)

    # Create generator
    generator = TestGenerator(
        project_root=workspace_root,
        default_framework=args.framework,
    )

    try:
        # Generate tests
        result = await generator.generate_tests(
            file_path=file_path,
            symbol_name=args.symbol,
            framework=args.framework,
            include_fixtures=not args.no_fixtures,
            include_edge_cases=not args.no_edge_cases,
        )

        # Display results
        print("\n" + "=" * 60)
        print("TEST GENERATION RESULTS")
        print("=" * 60)
        print(f"  Symbol:      {result.symbol_name or '(auto-detected)'}")
        print(f"  Type:        {result.symbol_type}")
        print(f"  Framework:   {result.framework}")
        print(f"  Test count:  {result.test_count}")
        print(f"  Coverage:     ~{result.coverage_estimate:.0%}")
        print(f"  Output:      {result.filename}")
        print()

        print("Generated tests:")
        print("-" * 60)
        print(result.content)
        print("-" * 60)

        # Apply if requested
        if args.apply:
            output_path = Path(args.output) if args.output else Path(result.filename)
            output_path.write_text(result.content, encoding="utf-8")
            print(f"\n[OK] Tests written to: {output_path}")
        else:
            output_hint = args.output or result.filename
            print(f"\nTo apply tests: ai-support test {args.file} --apply")
            print(f"To write to file: ai-support test {args.file} --output {output_hint} --apply")

        return 0

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except SyntaxError as e:
        print(f"Syntax error in source file: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error generating tests: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


async def cmd_test_slash(ctx) -> "CommandResult":
    """Slash command handler for /test.

    This is called from the slash command parser.

    Args:
        ctx: Command context from slash parser

    Returns:
        CommandResult with output and metadata
    """
    from src.infrastructure.testing.test_generator import TestGenerator
    from src.interfaces.cli.commands.slash import CommandContext, CommandResult

    # Cast to proper type (for type checker)
    ctx = ctx  # type: CommandContext

    # Get file from context
    file_path_str = ctx.raw_args.strip().split()[0] if ctx.raw_args.strip() else ""

    if not file_path_str:
        return CommandResult(
            success=False,
            output="Usage: /test @filename[:symbol] [--framework=pytest]\n"
                   "  /test src/my_module.py\n"
                   "  /test src/my_module.py:MyFunction\n"
                   "  /test src/my_module.py --framework=unittest",
        )

    # Parse file path and optional symbol
    parts = file_path_str.split(":")
    file_path = Path(parts[0])
    symbol_name = parts[1] if len(parts) > 1 else None

    # Override with explicit symbol if provided
    if ctx.raw_args.strip():
        # Check for --symbol flag
        if "--symbol" in ctx.raw_args or "-s" in ctx.raw_args:
            for part in ctx.raw_args.split():
                if part.startswith("--symbol="):
                    symbol_name = part.split("=", 1)[1]
                elif part == "-s" and part != parts[0]:
                    # Next part is symbol
                    pass

    # Get framework
    framework = "pytest"
    if "--framework" in ctx.raw_args or "-f" in ctx.raw_args:
        for part in ctx.raw_args.split():
            if part.startswith("--framework="):
                framework = part.split("=", 1)[1]
            elif part == "-f" and part != parts[0]:
                framework = part

    # Validate file
    if not file_path.exists():
        return CommandResult(
            success=False,
            output=f"Error: File not found: {file_path}",
        )

    # Create generator
    generator = TestGenerator(
        project_root=ctx.workspace_root,
        default_framework=framework,
    )

    try:
        result = await generator.generate_tests(
            file_path=file_path,
            symbol_name=symbol_name,
            framework=framework,
        )

        output_lines = [
            "## Test Generation Results",
            "",
            f"| Property | Value |",
            f"|----------|-------|",
            f"| Symbol | {result.symbol_name or '(auto-detected)'} |",
            f"| Type | {result.symbol_type} |",
            f"| Framework | {result.framework} |",
            f"| Test count | {result.test_count} |",
            f"| Coverage | ~{result.coverage_estimate:.0%} |",
            "",
            "### Generated Tests",
            "",
            "```python",
            result.content,
            "```",
            "",
            f"To apply: `ai-support test {file_path} --apply`",
        ]

        return CommandResult(
            success=True,
            output="\n".join(output_lines),
            data={
                "filename": result.filename,
                "test_count": result.test_count,
                "framework": result.framework,
                "symbol_name": result.symbol_name,
                "symbol_type": result.symbol_type,
            },
        )

    except Exception as e:
        return CommandResult(
            success=False,
            output=f"Error generating tests: {e}",
            errors=[str(e)],
        )
