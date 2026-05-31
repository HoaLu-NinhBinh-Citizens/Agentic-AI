"""Local LLM management commands for the CLI.

Provides commands for:
- Checking local LLM server status
- Listing available models
- Pulling new models from Ollama registry
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Any, Callable, Coroutine

HELP_TEXT = """Local LLM management commands.

Use these commands to check if Ollama is running and manage models.
"""


def register(subparsers: argparse._SubParsersAction) -> None:
    """Register local LLM subcommands.

    Args:
        subparsers: Parent subparsers action from argparse
    """
    parser = subparsers.add_parser(
        "llm",
        help="Local LLM (Ollama) management",
        description=HELP_TEXT,
    )
    sub = parser.add_subparsers(dest="llm_command", required=True)

    # Status command
    status_parser = sub.add_parser("status", help="Check if local LLM is running")
    status_parser.set_defaults(handler=_status_handler)

    # Models command
    models_parser = sub.add_parser("models", help="List available models")
    models_parser.add_argument(
        "--refresh",
        action="store_true",
        help="Refresh model list from server",
    )
    models_parser.set_defaults(handler=_models_handler)

    # Pull command
    pull_parser = sub.add_parser("pull", help="Pull a model from Ollama registry")
    pull_parser.add_argument(
        "model",
        help="Model name (e.g., llama3.2, codellama, mistral)",
    )
    pull_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be pulled without pulling",
    )
    pull_parser.set_defaults(handler=_pull_handler)

    # Info command
    info_parser = sub.add_parser("info", help="Show information about a model")
    info_parser.add_argument("model", help="Model name")
    info_parser.set_defaults(handler=_info_handler)

    # Check command - quick availability check
    check_parser = sub.add_parser("check", help="Quick availability check")
    check_parser.set_defaults(handler=_check_handler)


async def _status_handler(args: argparse.Namespace) -> int:
    """Check local LLM server status.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code (0 = running, 1 = not running)
    """
    from src.infrastructure.llm.local_provider import LocalLLMProvider

    provider = LocalLLMProvider()
    print(f"Checking local LLM at {provider.config.base_url}...")

    available = await provider.health_check()

    if available:
        print("\033[92m[OK]\033[0m Local LLM is running")

        # Try to list models
        try:
            from src.infrastructure.llm.ollama_adapter import OllamaAdapter
            adapter = OllamaAdapter()
            models = await adapter.list_models()
            if models:
                print(f"\nAvailable models ({len(models)}):")
                for m in models:
                    name = m.get("name", "unknown")
                    size = m.get("size", 0)
                    size_str = _format_size(size)
                    modified = m.get("modified_at", "")
                    print(f"  - {name} ({size_str})")
                    if modified:
                        print(f"    Modified: {modified[:10] if len(modified) >= 10 else modified}")
            await adapter.close()
        except Exception as e:
            print(f"Warning: Could not list models: {e}")

        await provider.close()
        return 0
    else:
        print("\033[91m[X]\033[0m Local LLM is not running")
        print("\nTo start Ollama, run:")
        print("  ollama serve")
        print("\nOr install Ollama from: https://ollama.ai")
        await provider.close()
        return 1


async def _models_handler(args: argparse.Namespace) -> int:
    """List available models.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code
    """
    from src.infrastructure.llm.ollama_adapter import OllamaAdapter

    adapter = OllamaAdapter()

    print("Fetching models from Ollama...")
    models = await adapter.list_models()

    if models:
        print(f"\nAvailable models ({len(models)}):\n")
        for m in models:
            name = m.get("name", "unknown")
            size = m.get("size", 0)
            size_str = _format_size(size)
            modified = m.get("modified_at", "")

            print(f"  {name}")
            print(f"    Size: {size_str}")
            if modified:
                print(f"    Modified: {modified[:10] if len(modified) >= 10 else modified}")
            print()
    else:
        print("\033[93mNo models found.\033[0m")
        print("\nTo pull a model, run:")
        print("  python -m ai_support llm pull llama3.2")

    await adapter.close()
    return 0


async def _pull_handler(args: argparse.Namespace) -> int:
    """Pull a model from Ollama registry.

    Args:
        args: Parsed command-line arguments with 'model' attribute

    Returns:
        Exit code
    """
    from src.infrastructure.llm.ollama_adapter import OllamaAdapter

    model_name = args.model

    if args.dry_run:
        print(f"[Dry Run] Would pull model: {model_name}")
        print("\nTo actually pull, run without --dry-run:")
        print(f"  python -m ai_support llm pull {model_name}")
        return 0

    adapter = OllamaAdapter()

    # Check if already available
    existing = await adapter.list_models()
    existing_names = [m.get("name", "") for m in existing]

    if model_name in existing_names:
        print(f"\033[93mModel '{model_name}' is already installed.\033[0m")
        response = input("Re-pull anyway? [y/N] ").strip().lower()
        if response != "y":
            print("Cancelled.")
            await adapter.close()
            return 0

    print(f"\nPulling model: {model_name}")
    print("(This may take several minutes depending on model size and network)\n")

    try:
        status_count = 0
        async for status in adapter.pull_model(model_name):
            status_count += 1
            # Print status without newline, clear previous line
            if status_count > 1:
                print("\033[2K", end="")  # Clear line
                print("\033[1A", end="")  # Move cursor up
            print(f"  {status}", end="\r")

        print("\n\033[92mModel pulled successfully!\033[0m")
        print(f"\nUse it with:")
        print(f"  # Set in config")
        print(f"  local_provider:")
        print(f"    default_model: \"{model_name}\"")

        await adapter.close()
        return 0

    except Exception as e:
        print(f"\n\033[91mFailed to pull model: {e}\033[0m")
        await adapter.close()
        return 1


async def _info_handler(args: argparse.Namespace) -> int:
    """Show information about a model.

    Args:
        args: Parsed command-line arguments with 'model' attribute

    Returns:
        Exit code
    """
    from src.infrastructure.llm.ollama_adapter import OllamaAdapter

    model_name = args.model
    adapter = OllamaAdapter()

    print(f"Fetching info for: {model_name}...")

    info = await adapter.get_model_info(model_name)

    if info:
        print("\nModel Information:")
        print("-" * 40)

        if "modelfile" in info:
            print("\nModelfile:")
            modelfile = info["modelfile"]
            for line in modelfile.split("\n")[:20]:
                print(f"  {line}")
            if len(modelfile.split("\n")) > 20:
                print("  ... (truncated)")

        if "parameters" in info:
            print("\nParameters:")
            print(f"  {info['parameters']}")

        if "template" in info:
            print("\nTemplate:")
            print(f"  {info['template'][:200]}...")

    else:
        print(f"\033[91mModel '{model_name}' not found.\033[0m")
        print("\nTo list available models:")
        print("  python -m ai_support llm models")

    await adapter.close()
    return 0


async def _check_handler(args: argparse.Namespace) -> int:
    """Quick availability check.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code (0 = available, 1 = not available)
    """
    from src.infrastructure.llm.ollama_adapter import check_ollama_status

    available, models = await check_ollama_status()

    if available:
        print(f"\033[92mOK\033[0m Local LLM is running ({len(models)} models)")
        return 0
    else:
        print(f"\033[91mFAIL\033[0m Local LLM is not available")
        return 1


def _format_size(size_bytes: int) -> str:
    """Format bytes as human-readable string.

    Args:
        size_bytes: Size in bytes

    Returns:
        Formatted string like "1.5 GB"
    """
    if size_bytes == 0:
        return "unknown"

    units = ["B", "KB", "MB", "GB", "TB"]
    unit_idx = 0
    size = float(size_bytes)

    while size >= 1024 and unit_idx < len(units) - 1:
        size /= 1024
        unit_idx += 1

    if unit_idx == 0:
        return f"{int(size)} {units[unit_idx]}"
    return f"{size:.1f} {units[unit_idx]}"


async def main(argv: list[str] | None = None) -> int:
    """Run local LLM command from CLI.

    Args:
        argv: Optional command-line arguments

    Returns:
        Exit code
    """
    parser = argparse.ArgumentParser(
        prog="ai-support llm",
        description="Local LLM management commands",
    )
    sub = parser.add_subparsers(dest="llm_command", required=True)
    register(sub)

    args = parser.parse_args(argv)
    handler: Callable[[argparse.Namespace], Coroutine[Any, Any, int]] | None = getattr(
        args, "handler", None
    )
    if handler is None:
        parser.print_help()
        return 1

    return await handler(args)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
