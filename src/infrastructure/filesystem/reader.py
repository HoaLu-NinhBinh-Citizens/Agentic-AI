"""File reader stub."""

from pathlib import Path
from typing import Any


class FileReader:
    """Reads files from filesystem."""
    
    async def read(self, path: str) -> str:
        """Read file content."""
        file_path = Path(path)
        if file_path.exists():
            return file_path.read_text()
        raise FileNotFoundError(f"File not found: {path}")
    
    async def exists(self, path: str) -> bool:
        """Check if file exists."""
        return Path(path).exists()
    
    async def list_directory(self, path: str) -> list[str]:
        """List directory contents."""
        dir_path = Path(path)
        if dir_path.exists() and dir_path.is_dir():
            return [str(f) for f in dir_path.iterdir()]
        return []
