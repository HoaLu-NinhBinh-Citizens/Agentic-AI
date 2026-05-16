"""Migration manager stub."""

from typing import Any, Callable


class MigrationManager:
    """Manages database schema migrations."""
    
    def __init__(self):
        self._migrations: list[Callable] = []
    
    def register(self, version: str, migration: Callable) -> None:
        """Register a migration."""
        self._migrations.append(migration)
    
    async def migrate(self, from_version: str, to_version: str) -> None:
        """Run migrations between versions."""
        for migration in self._migrations:
            await migration()
