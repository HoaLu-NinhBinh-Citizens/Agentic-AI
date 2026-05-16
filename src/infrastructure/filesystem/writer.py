"""File writer stub."""

from pathlib import Path
from typing import Any


class FileWriter:
    """Writes files to filesystem."""
    
    async def write(self, path: str, content: str) -> None:
        """Write file content."""
        file_path = Path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)
    
    async def append(self, path: str, content: str) -> None:
        """Append to file."""
        file_path = Path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(file_path.read_text() + content)
    
    async def delete(self, path: str) -> None:
        """Delete file."""
        file_path = Path(path)
        if file_path.exists():
            file_path.unlink()
