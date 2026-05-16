"""
Memory Type Separation

Provides clear separation between different types of memory in src.
This module defines memory types, their boundaries, and interaction rules.

Memory Types:
- Episodic: Short-term session events and experiences
- Semantic: Long-term knowledge and facts
- Procedural: How to do things, skills
- Working: Active computation context

Critical Rule: DO NOT allow autonomous self-modifying memory early.

Usage:
    from src.core.memory.type_separation import MemorySystem, MemoryType

    memory = MemorySystem()
    memory.store(MemoryType.EPISODIC, "session_event", data)
    memory.store(MemoryType.SEMANTIC, "firmware_knowledge", data)
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, TypeVar, Generic

logger = logging.getLogger(__name__)


class MemoryType(Enum):
    """Types of memory with clear boundaries."""
    EPISODIC = "episodic"      # Session events, experiences
    SEMANTIC = "semantic"       # Facts, knowledge
    PROCEDURAL = "procedural"   # Skills, how-to
    WORKING = "working"         # Active computation
    FAILURE = "failure"         # Failure patterns
    PROJECT = "project"         # Project-specific context


class MemoryAccess(Enum):
    """Access control levels."""
    READ_WRITE = "read_write"
    READ_ONLY = "read_only"
    WRITE_ONLY = "write_only"
    PROTECTED = "protected"     # Requires approval


@dataclass
class MemoryEntry:
    """A memory entry with type classification."""
    id: str
    memory_type: MemoryType
    key: str
    content: Any
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    access_count: int = 0
    access_level: MemoryAccess = MemoryAccess.READ_WRITE
    ttl_seconds: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_expired(self) -> bool:
        """Check if entry has expired."""
        if self.ttl_seconds is None:
            return False
        age = (datetime.now() - self.created_at).total_seconds()
        return age > self.ttl_seconds

    def touch(self) -> None:
        """Update access time and count."""
        self.access_count += 1


@dataclass
class MemoryPolicy:
    """Policy for memory operations."""
    memory_type: MemoryType
    max_entries: int = 1000
    max_size_mb: float = 100.0
    default_ttl_seconds: Optional[float] = None
    auto_cleanup: bool = True
    requires_approval: bool = False
    promotion_rules: List[str] = field(default_factory=list)
    eviction_policy: str = "lru"  # lru, fifo, size


class MemorySystem:
    """
    Memory system with type separation.

    Provides clear boundaries between different memory types
    and enforces access policies.

    Usage:
        memory = MemorySystem()

        # Store in different types
        memory.store(MemoryType.EPISODIC, "task_123", event_data)
        memory.store(MemoryType.SEMANTIC, "stm32_facts", knowledge)
        memory.store(MemoryType.PROCEDURAL, "flash_pattern", skill)

        # Retrieve
        events = memory.get_by_type(MemoryType.EPISODIC)
        facts = memory.get_by_type(MemoryType.SEMANTIC)
    """

    # Default policies per memory type
    DEFAULT_POLICIES = {
        MemoryType.EPISODIC: MemoryPolicy(
            memory_type=MemoryType.EPISODIC,
            max_entries=5000,
            max_size_mb=50.0,
            default_ttl_seconds=3600,  # 1 hour
            auto_cleanup=True,
            eviction_policy="lru",
        ),
        MemoryType.SEMANTIC: MemoryPolicy(
            memory_type=MemoryType.SEMANTIC,
            max_entries=10000,
            max_size_mb=200.0,
            default_ttl_seconds=None,  # Never expire by default
            auto_cleanup=False,
            requires_approval=True,
            eviction_policy="size",
        ),
        MemoryType.PROCEDURAL: MemoryPolicy(
            memory_type=MemoryType.PROCEDURAL,
            max_entries=500,
            max_size_mb=50.0,
            default_ttl_seconds=None,
            auto_cleanup=False,
            requires_approval=True,
            eviction_policy="lru",
        ),
        MemoryType.WORKING: MemoryPolicy(
            memory_type=MemoryType.WORKING,
            max_entries=100,
            max_size_mb=10.0,
            default_ttl_seconds=300,  # 5 minutes
            auto_cleanup=True,
            eviction_policy="fifo",
        ),
        MemoryType.FAILURE: MemoryPolicy(
            memory_type=MemoryType.FAILURE,
            max_entries=1000,
            max_size_mb=20.0,
            default_ttl_seconds=86400 * 7,  # 1 week
            auto_cleanup=True,
            eviction_policy="lru",
        ),
        MemoryType.PROJECT: MemoryPolicy(
            memory_type=MemoryType.PROJECT,
            max_entries=5000,
            max_size_mb=100.0,
            default_ttl_seconds=3600 * 24,  # 1 day
            auto_cleanup=True,
            eviction_policy="lru",
        ),
    }

    def __init__(self, policies: Optional[Dict[MemoryType, MemoryPolicy]] = None):
        self.policies = {**self.DEFAULT_POLICIES}
        if policies:
            self.policies.update(policies)

        # Separate storage per type
        self._stores: Dict[MemoryType, Dict[str, MemoryEntry]] = {
            mtype: {} for mtype in MemoryType
        }

        # Statistics
        self._stats: Dict[MemoryType, Dict[str, Any]] = {
            mtype: {
                "total_entries": 0,
                "total_accesses": 0,
                "evictions": 0,
                "total_size_mb": 0.0,
            }
            for mtype in MemoryType
        }

        # Approval callbacks for protected memory
        self._approval_callbacks: List[Callable[[str, MemoryType, Any], bool]] = []

        # Modification restrictions (safety)
        self._allow_autonomous_modification = False

    @property
    def allow_autonomous_modification(self) -> bool:
        """Check if autonomous modification is allowed."""
        return self._allow_autonomous_modification

    def set_autonomous_modification(self, allowed: bool) -> None:
        """
        Enable/disable autonomous memory modification.

        WARNING: Enabling this allows the AI to modify its own memory
        without human approval. This should only be enabled after
        extensive testing.
        """
        if allowed:
            logger.warning(
                "ENABLING autonomous memory modification - "
                "ensure this is intentional and tested"
            )
        self._allow_autonomous_modification = allowed

    def store(
        self,
        memory_type: MemoryType,
        key: str,
        content: Any,
        ttl_seconds: Optional[float] = None,
        access_level: MemoryAccess = MemoryAccess.READ_WRITE,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Store content in a memory type.

        Args:
            memory_type: Type of memory
            key: Unique key
            content: Content to store
            ttl_seconds: Time to live (uses policy default if None)
            access_level: Access control
            metadata: Optional metadata

        Returns:
            True if stored, False if rejected
        """
        policy = self.policies[memory_type]

        # Check approval requirement
        if policy.requires_approval:
            if not self._check_approval(key, memory_type, content):
                logger.warning(f"Memory store rejected: requires approval for {key}")
                return False

        # Check autonomous modification
        if not self._allow_autonomous_modification:
            if memory_type in (MemoryType.SEMANTIC, MemoryType.PROCEDURAL):
                # These types should not be autonomously modified early
                existing = self._stores[memory_type].get(key)
                if existing is not None:
                    logger.warning(
                        f"Autonomous modification of {memory_type.value}/{key} blocked"
                    )
                    return False

        # Apply default TTL from policy
        if ttl_seconds is None:
            ttl_seconds = policy.default_ttl_seconds

        # Check capacity
        if self._is_at_capacity(memory_type):
            if not policy.auto_cleanup:
                logger.warning(f"Memory {memory_type.value} at capacity, rejecting store")
                return False
            self._evict(memory_type)

        # Create entry
        entry = MemoryEntry(
            id=f"{memory_type.value}_{key}",
            memory_type=memory_type,
            key=key,
            content=content,
            ttl_seconds=ttl_seconds,
            access_level=access_level,
            metadata=metadata or {},
        )

        # Store
        self._stores[memory_type][key] = entry
        self._update_stats(memory_type, "total_entries", 1)

        logger.debug(f"Stored: {memory_type.value}/{key}")
        return True

    def get(
        self,
        memory_type: MemoryType,
        key: str,
        default: Any = None,
    ) -> Any:
        """Get content from src.core.memory."""
        entry = self._stores[memory_type].get(key)

        if entry is None:
            return default

        # Check expiration
        if entry.is_expired():
            self.delete(memory_type, key)
            return default

        entry.touch()
        self._update_stats(memory_type, "total_accesses", 1)
        return entry.content

    def delete(self, memory_type: MemoryType, key: str) -> bool:
        """Delete entry from src.core.memory."""
        if key in self._stores[memory_type]:
            del self._stores[memory_type][key]
            self._update_stats(memory_type, "total_entries", -1)
            return True
        return False

    def get_by_type(
        self,
        memory_type: MemoryType,
        limit: Optional[int] = None,
    ) -> List[Any]:
        """Get all entries of a type."""
        entries = list(self._stores[memory_type].values())

        # Filter expired
        entries = [e for e in entries if not e.is_expired()]

        # Sort by access time (most recent first)
        entries.sort(key=lambda e: e.accessed_at, reverse=True)

        if limit:
            entries = entries[:limit]

        return [e.content for e in entries]

    def get_keys_by_type(self, memory_type: MemoryType) -> List[str]:
        """Get all keys of a type."""
        return list(self._stores[memory_type].keys())

    def get_stats(self, memory_type: Optional[MemoryType] = None) -> Dict[str, Any]:
        """Get memory statistics."""
        if memory_type:
            return self._stats[memory_type].copy()

        return {
            mtype.value: self._stats[mtype].copy()
            for mtype in MemoryType
        }

    def _is_at_capacity(self, memory_type: MemoryType) -> bool:
        """Check if memory type is at capacity."""
        policy = self.policies[memory_type]
        current = len(self._stores[memory_type])
        return current >= policy.max_entries

    def _evict(self, memory_type: MemoryType) -> int:
        """Evict entries based on policy."""
        policy = self.policies[memory_type]
        entries = list(self._stores[memory_type].values())

        if not entries:
            return 0

        evicted = 0

        if policy.eviction_policy == "lru":
            entries.sort(key=lambda e: e.accessed_at)
        elif policy.eviction_policy == "fifo":
            entries.sort(key=lambda e: e.created_at)
        elif policy.eviction_policy == "size":
            # Would need size estimation
            entries.sort(key=lambda e: e.access_count)

        # Evict oldest 10%
        evict_count = max(1, len(entries) // 10)
        for entry in entries[:evict_count]:
            self.delete(memory_type, entry.key)
            evicted += 1

        self._update_stats(memory_type, "evictions", evicted)
        logger.debug(f"Evicted {evicted} entries from {memory_type.value}")

        return evicted

    def _update_stats(self, memory_type: MemoryType, key: str, delta: int = 0) -> None:
        """Update statistics."""
        if key in self._stats[memory_type]:
            if isinstance(self._stats[memory_type][key], (int, float)):
                self._stats[memory_type][key] += delta

    def _check_approval(
        self,
        key: str,
        memory_type: MemoryType,
        content: Any,
    ) -> bool:
        """Check if operation is approved."""
        for callback in self._approval_callbacks:
            if callback(key, memory_type, content):
                return True
        return False

    def register_approval_callback(
        self,
        callback: Callable[[str, MemoryType, Any], bool]
    ) -> None:
        """Register approval callback."""
        self._approval_callbacks.append(callback)

    def cleanup_expired(self) -> int:
        """Clean up all expired entries."""
        total = 0
        for memory_type in MemoryType:
            expired = [
                key for key, entry in self._stores[memory_type].items()
                if entry.is_expired()
            ]
            for key in expired:
                self.delete(memory_type, key)
                total += 1
        return total

    def clear_type(self, memory_type: MemoryType) -> int:
        """Clear all entries of a type."""
        count = len(self._stores[memory_type])
        self._stores[memory_type].clear()
        self._stats[memory_type]["total_entries"] = 0
        return count

    def promote(
        self,
        from_type: MemoryType,
        to_type: MemoryType,
        key: str,
    ) -> bool:
        """
        Promote memory entry to a higher-tier type.

        This is used for learning: moving validated episodic
        memories to semantic memory.
        """
        content = self.get(from_type, key)
        if content is None:
            return False

        # Verify approval for promotion
        if self.policies[to_type].requires_approval:
            if not self._check_approval(key, to_type, content):
                return False

        # Store in new type
        if self.store(to_type, key, content):
            self.delete(from_type, key)
            return True
        return False

    def get_memory_summary(self) -> Dict[str, Any]:
        """Get summary of all memory types."""
        return {
            mtype.value: {
                "entries": len(self._stores[mtype]),
                "max_entries": self.policies[mtype].max_entries,
                "capacity_percent": (
                    len(self._stores[mtype]) / self.policies[mtype].max_entries * 100
                    if self.policies[mtype].max_entries > 0 else 0
                ),
                "total_accesses": self._stats[mtype]["total_accesses"],
                "evictions": self._stats[mtype]["evictions"],
                "requires_approval": self.policies[mtype].requires_approval,
            }
            for mtype in MemoryType
        }
