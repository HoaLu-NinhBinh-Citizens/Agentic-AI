"""Disk cache stub."""

from pathlib import Path
import json
from typing import Any


class DiskCache:
    """Disk-backed cache."""
    
    def __init__(self, path: str = "data/cache"):
        self._path = Path(path)
        self._path.mkdir(parents=True, exist_ok=True)
    
    def set(self, key: str, value: Any) -> None:
        """Set cache value."""
        file_path = self._path / f"{key}.json"
        file_path.write_text(json.dumps(value))
    
    def get(self, key: str) -> Any | None:
        """Get cache value."""
        file_path = self._path / f"{key}.json"
        if file_path.exists():
            return json.loads(file_path.read_text())
        return None
