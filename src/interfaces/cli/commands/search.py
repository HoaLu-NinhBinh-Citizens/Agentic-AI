"""Search command - semantic code search."""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from src.infrastructure.search.semantic_search import SemanticSearch


def register(subparsers) -> None:
    """Register the search command.
    
    Args:
        subparsers: ArgumentParser subparsers
    """
    p = subparsers.add_parser(
        "search",
        help="Search codebase semantically",
        description="Search the codebase by meaning, not just text",
    )
    p.add_argument("query", help="Search query")
    p.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of results (default: 20)"
    )
    p.add_argument(
        "--type",
        choices=["all", "symbol", "comment", "code"],
        default="all",
        help="Filter by result type (default: all)"
    )
    p.add_argument(
        "--no-index",
        action="store_true",
        help="Skip indexing (use existing index)"
    )
    p.add_argument(
        "--reindex",
        action="store_true",
        help="Force reindex before searching"
    )
    p.set_defaults(handler=run_search)


async def run_search(args: argparse.Namespace) -> int:
    """Run semantic search.
    
    Args:
        args: Parsed command-line arguments
        
    Returns:
        Exit code (0 for success, 1 for no results, 2 for error)
    """
    try:
        project_root = Path.cwd()
        
        print(f"\n{'='*60}")
        print(f"Semantic Search: {args.query}")
        print(f"{'='*60}\n")
        
        # Initialize searcher
        searcher = SemanticSearch(project_root)
        
        # Index if needed
        if args.reindex:
            print("Reindexing project...")
            searcher.reindex()
        elif not args.no_index:
            print("Indexing project (first run may take a moment)...")
            searcher.index_project()
        
        # Perform search
        results = searcher.search(
            args.query,
            limit=args.limit,
            match_type=args.type if args.type != "all" else None,
        )
        
        # Display results
        if not results:
            print("No results found.")
            return 1
        
        print(f"\nFound {len(results)} results:\n")
        
        for i, r in enumerate(results, 1):
            print(f"{i}. {r.file}:{r.line}")
            print(f"   [{r.match_type}] Score: {r.score:.2f}")
            print(f"   {r.snippet[:80]}...")
            
            if r.context_before:
                print(f"   ...{r.context_before.strip()}")
            if r.context_after:
                print(f"   {r.context_after.strip()}...")
            print()
        
        return 0
        
    except Exception as e:
        print(f"Search error: {e}", file=sys.stderr)
        return 2


def main() -> int:
    """Entry point for the search command."""
    parser = argparse.ArgumentParser(description="Semantic search")
    register(parser.add_subparsers())
    args = parser.parse_args()
    return asyncio.run(args.handler(args))


if __name__ == "__main__":
    sys.exit(main())
