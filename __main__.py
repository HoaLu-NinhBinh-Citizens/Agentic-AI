"""CLI entry point for AI_support package."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.application.api.app.embedded_agent import EmbeddedCAgent


def _agent_factory(project_root: str, model: str):
    """Factory function for creating agents."""
    return EmbeddedCAgent(project_root=project_root, model=model, bootstrap_rag=False)


def main():
    """Run the CLI."""
    from src.application.api.app.cli import run_cli
    asyncio.run(run_cli(_agent_factory))


if __name__ == "__main__":
    main()
