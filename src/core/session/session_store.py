"""Session store stub."""

import json
from pathlib import Path
from typing import Any


class SessionStore:
    """Persistent storage for sessions."""
    
    def __init__(self, path: str = "data/sessions"):
        self._path = Path(path)
        self._path.mkdir(parents=True, exist_ok=True)
    
    def save(self, session_id: str, data: dict[str, Any]) -> None:
        """Save session data."""
        file_path = self._path / f"{session_id}.json"
        file_path.write_text(json.dumps(data, default=str))
    
    def load(self, session_id: str) -> dict[str, Any] | None:
        """Load session data."""
        file_path = self._path / f"{session_id}.json"
        if file_path.exists():
            return json.loads(file_path.read_text())
        return None
