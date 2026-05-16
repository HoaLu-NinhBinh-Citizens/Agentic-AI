"""Idempotency stub."""

import hashlib
import time
from typing import Any


class IdempotencyManager:
    """Manages idempotency keys for tasks."""
    
    def __init__(self, ttl: int = 3600):
        self._keys: dict[str, tuple[Any, float]] = {}
        self._ttl = ttl
    
    def _make_key(self, task: dict[str, Any]) -> str:
        """Generate idempotency key from task."""
        return hashlib.sha256(str(task).encode()).hexdigest()[:16]
    
    def check(self, task: dict[str, Any]) -> bool:
        """Check if task was already processed."""
        key = self._make_key(task)
        if key in self._keys:
            _, timestamp = self._keys[key]
            if time.time() - timestamp < self._ttl:
                return True
        return False
    
    def store(self, task: dict[str, Any], result: Any) -> None:
        """Store task result."""
        key = self._make_key(task)
        self._keys[key] = (result, time.time())
