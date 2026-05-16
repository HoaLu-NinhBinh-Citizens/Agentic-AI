"""Server main stub."""

from typing import Any


async def start_server(host: str = "0.0.0.0", port: int = 8766) -> None:
    """Start the API server."""
    print(f"Starting server at {host}:{port}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(start_server())
