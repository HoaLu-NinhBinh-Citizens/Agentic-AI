"""Schema versioning stub."""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class SchemaVersion:
    """Version information for schemas."""
    
    version: str
    created_at: datetime
    description: str = ""
    
    @classmethod
    def current(cls) -> "SchemaVersion":
        """Get current schema version."""
        return cls(version="1.0.0", created_at=datetime.now())
