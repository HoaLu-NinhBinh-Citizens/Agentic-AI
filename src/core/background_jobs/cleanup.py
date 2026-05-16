"""Cleanup job stub."""

import asyncio
from pathlib import Path


class CleanupJob:
    """Periodic cleanup of temporary files."""
    
    def __init__(self, paths: list[str], max_age_hours: int = 24):
        self._paths = [Path(p) for p in paths]
        self._max_age = max_age_hours * 3600
    
    async def run(self) -> int:
        """Run cleanup and return count of deleted files."""
        count = 0
        for path in self._paths:
            if path.exists():
                for file in path.glob("**/*"):
                    if file.is_file():
                        import time
                        if time.time() - file.stat().st_mtime > self._max_age:
                            file.unlink()
                            count += 1
        return count
