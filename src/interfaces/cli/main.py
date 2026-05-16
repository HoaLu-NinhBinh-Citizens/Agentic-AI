"""CLI main entry point."""

import asyncio
import sys
from typing import Any


async def main() -> int:
    """Main CLI entry point."""
    print("AI_support CLI")
    print("Usage: ai-support <command> [options]")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
