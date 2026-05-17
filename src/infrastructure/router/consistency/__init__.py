"""Consistency module for semantic router."""

from src.infrastructure.router.consistency.read_after_write import ReadAfterWriteGuard

__all__ = ["ReadAfterWriteGuard"]
