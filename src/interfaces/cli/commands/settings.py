"""Settings command - interactive configuration management.

Usage:
    ai-support settings list
    ai-support settings list --format json
    ai-support settings get ai_support.review.max_file_size_kb
    ai-support settings set ai_support.review.max_file_size_kb 1000
    ai-support settings edit
    ai-support settings reset
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any, Optional

import yaml


DEFAULT_SETTINGS_FILE = Path("configs/ai_support_rules.yaml")


def register(subparsers: argparse._SubParsersAction) -> None:
    """Register the settings command.

    Args:
        subparsers: Parent subparsers action from argparse
    """
    parser = subparsers.add_parser(
        "settings",
        help="Manage AI_SUPPORT settings",
        description="Interactive settings management with YAML storage",
    )
    sub = parser.add_subparsers(dest="settings_cmd", required=True)

    # List settings
    list_p = sub.add_parser("list", help="List current settings")
    list_p.add_argument(
        "--format", "-f",
        choices=["yaml", "json", "table"],
        default="table",
        help="Output format (default: table)",
    )
    list_p.set_defaults(handler=run_settings)

    # Get setting
    get_p = sub.add_parser("get", help="Get a setting value")
    get_p.add_argument("key", help="Setting key (dot notation)")
    get_p.set_defaults(handler=run_settings)

    # Set setting
    set_p = sub.add_parser("set", help="Set a setting value")
    set_p.add_argument("key", help="Setting key (dot notation)")
    set_p.add_argument("value", help="New value")
    set_p.set_defaults(handler=run_settings)

    # Interactive edit
    edit_p = sub.add_parser("edit", help="Interactive settings editor")
    edit_p.set_defaults(handler=run_settings)

    # Reset
    reset_p = sub.add_parser("reset", help="Reset settings to defaults")
    reset_p.add_argument(
        "--confirm",
        action="store_true",
        help="Skip confirmation prompt",
    )
    reset_p.set_defaults(handler=run_settings)


def load_settings(path: Optional[Path] = None) -> dict[str, Any]:
    """Load settings from YAML file.

    Args:
        path: Optional custom settings file path

    Returns:
        Settings dictionary
    """
    settings_file = path or DEFAULT_SETTINGS_FILE

    if not settings_file.exists():
        return _default_settings()

    try:
        content = settings_file.read_text(encoding="utf-8")
        settings = yaml.safe_load(content)
        return settings if settings else {}
    except yaml.YAMLError as e:
        print(f"Warning: Error parsing YAML: {e}", file=sys.stderr)
        return {}


def save_settings(settings: dict[str, Any], path: Optional[Path] = None) -> None:
    """Save settings to YAML file.

    Args:
        settings: Settings dictionary to save
        path: Optional custom settings file path
    """
    settings_file = path or DEFAULT_SETTINGS_FILE
    settings_file.parent.mkdir(parents=True, exist_ok=True)

    content = yaml.dump(settings, default_flow_style=False, sort_keys=False)
    settings_file.write_text(content, encoding="utf-8")


def _default_settings() -> dict[str, Any]:
    """Get default settings.

    Returns:
        Default settings dictionary
    """
    return {
        "ai_support": {
            "rules": {
                "severity_threshold": "MEDIUM",
                "max_findings_per_file": 50,
            },
            "ml": {
                "confidence_threshold": 0.5,
                "auto_fix": False,
            },
            "review": {
                "max_file_size_kb": 500,
                "parallel_workers": 4,
            },
            "ui": {
                "theme": "default",
                "show_line_numbers": True,
                "emoji_enabled": True,
            },
        },
    }


async def run_settings(args: argparse.Namespace) -> int:
    """Run settings command.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code
    """
    cmd = getattr(args, "settings_cmd", "list")

    if cmd == "list":
        return await list_settings(args)
    elif cmd == "get":
        return await get_setting(args)
    elif cmd == "set":
        return await set_setting(args)
    elif cmd == "edit":
        return await edit_settings()
    elif cmd == "reset":
        return await reset_settings(args)

    return 0


async def list_settings(args: argparse.Namespace) -> int:
    """List all settings.

    Args:
        args: Parsed arguments with format option

    Returns:
        Exit code
    """
    settings = load_settings()

    fmt = getattr(args, "format", "table")

    if fmt == "yaml":
        print(yaml.dump(settings, default_flow_style=False, sort_keys=False))
    elif fmt == "json":
        import json
        print(json.dumps(settings, indent=2))
    else:
        _print_table(settings)

    return 0


def _print_table(settings: dict, prefix: str = "") -> None:
    """Print settings as a formatted table.

    Args:
        settings: Settings dictionary
        prefix: Key prefix for nested settings
    """
    for key, value in settings.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            _print_table(value, full_key)
        else:
            print(f"  {full_key:45} = {value}")


async def get_setting(args: argparse.Namespace) -> int:
    """Get a specific setting value.

    Args:
        args: Parsed arguments with key

    Returns:
        Exit code
    """
    settings = load_settings()
    keys = args.key.split(".")

    value = settings
    for k in keys:
        if isinstance(value, dict):
            value = value.get(k)
        else:
            value = None
        if value is None:
            print(f"Setting not found: {args.key}")
            return 1

    print(f"{args.key} = {value}")
    return 0


async def set_setting(args: argparse.Namespace) -> int:
    """Set a specific setting value.

    Args:
        args: Parsed arguments with key and value

    Returns:
        Exit code
    """
    settings = load_settings()
    keys = args.key.split(".")

    # Navigate to parent
    current = settings
    for k in keys[:-1]:
        if k not in current:
            current[k] = {}
        current = current[k]

    # Set value
    current[keys[-1]] = _parse_value(args.value)
    save_settings(settings)

    print(f"Set {args.key} = {args.value}")
    return 0


def _parse_value(value: str) -> Any:
    """Parse a string value to appropriate type.

    Args:
        value: String value from command line

    Returns:
        Parsed value (bool, int, float, or string)
    """
    # Boolean
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False

    # None
    if value.lower() in ("null", "none"):
        return None

    # Number
    try:
        return int(value)
    except ValueError:
        pass

    try:
        return float(value)
    except ValueError:
        pass

    # String
    return value


async def edit_settings() -> int:
    """Interactive settings editor.

    Returns:
        Exit code
    """
    settings = load_settings()

    print("\n[ AI_SUPPORT Settings Editor ]")
    print("=" * 50)
    print("Commands:")
    print("  key=value    Set a value")
    print("  key          Show nested keys")
    print("  save         Save and exit")
    print("  quit         Exit without saving")
    print("  list         Show all settings")
    print("=" * 50)

    while True:
        try:
            line = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting (unsaved changes may be lost).")
            break

        if not line:
            continue

        if line == "quit":
            print("Exiting editor.")
            break

        if line == "save":
            save_settings(settings)
            print("Settings saved.")
            break

        if line == "list":
            _print_table(settings)
            continue

        if "=" not in line:
            # Show nested keys
            keys = line.split(".")
            value = settings
            for k in keys:
                if isinstance(value, dict):
                    value = value.get(k)
                else:
                    value = None
                    break

            if value is None:
                print(f"Key not found: {line}")
            elif isinstance(value, dict):
                print(f"Nested keys under '{line}':")
                for k in value.keys():
                    print(f"  {k}")
            else:
                print(f"{line} = {value}")
            continue

        # Set value
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        # Parse and set
        keys = key.split(".")
        current = settings
        for k in keys[:-1]:
            if k not in current:
                current[k] = {}
            current = current[k]
        current[keys[-1]] = _parse_value(value)
        print(f"Set {key} = {value}")

    return 0


async def reset_settings(args: argparse.Namespace) -> int:
    """Reset settings to defaults.

    Args:
        args: Parsed arguments

    Returns:
        Exit code
    """
    if not getattr(args, "confirm", False):
        print("This will reset ALL settings to defaults.")
        try:
            confirm = input("Continue? (y/N): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            confirm = "n"

        if confirm != "y":
            print("Cancelled.")
            return 0

    save_settings(_default_settings())
    print("Settings reset to defaults.")
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.

    Args:
        argv: Optional command-line arguments

    Returns:
        Exit code
    """
    parser = argparse.ArgumentParser(
        prog="ai-support settings",
        description="AI_SUPPORT settings manager",
    )
    sub = parser.add_subparsers(dest="subcommand")
    register(sub)
    args = parser.parse_args(argv)

    if hasattr(args, "handler"):
        return asyncio.run(args.handler(args))
    return 0


if __name__ == "__main__":
    sys.exit(main())
