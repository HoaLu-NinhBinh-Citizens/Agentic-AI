"""
Context Budget Enforcement

Provides intelligent context management and budget enforcement for LLM interactions.
This module monitors token usage, prunes context when needed, and ensures
the system stays within context window limits.

Features:
- Token budget tracking
- Smart context pruning
- Priority-based retention
- Cost estimation
- Budget alerts

Usage:
    from src.infrastructure.retrieval.context_budget import ContextBudget, BudgetConfig

    budget = ContextBudget(config=BudgetConfig(max_tokens=100000))
    budget.track_context("system", 5000)
    budget.track_context("conversation", 8000)

    if budget.is_over_budget():
        pruned = budget.smart_prune()
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class BudgetAction(Enum):
    """Actions to take when budget is exceeded."""
    NONE = "none"
    WARN = "warn"
    PRUNE = "prune"
    TRUNCATE = "truncate"
    REJECT = "reject"


class ContentPriority(Enum):
    """Priority levels for context content."""
    CRITICAL = 0    # System prompts, core instructions
    HIGH = 1        # Important user context
    NORMAL = 2      # Regular conversation
    LOW = 3         # Auxiliary information
    EPHEMERAL = 4   # Can be discarded first


@dataclass
class ContextEntry:
    """A single context entry with budget tracking."""
    key: str
    content: str
    tokens: int
    priority: ContentPriority = ContentPriority.NORMAL
    created_at: datetime = field(default_factory=datetime.now)
    accessed_at: datetime = field(default_factory=datetime.now)
    access_count: int = 0
    is_mutable: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def touch(self) -> None:
        """Update access time and count."""
        self.accessed_at = datetime.now()
        self.access_count += 1


@dataclass
class BudgetConfig:
    """Configuration for context budget."""
    max_tokens: int = 100000
    warning_threshold: float = 0.8      # Warn at 80%
    prune_threshold: float = 0.9         # Start pruning at 90%
    critical_threshold: float = 0.95    # Force prune at 95%
    min_retention_tokens: int = 5000     # Never prune below this
    enable_auto_prune: bool = True
    strategy: str = "priority"           # priority, lru, hybrid


@dataclass
class BudgetStatus:
    """Current budget status."""
    total_tokens: int
    max_tokens: int
    utilization_percent: float
    entry_count: int
    over_budget: bool
    action_needed: BudgetAction
    warnings: List[str] = field(default_factory=list)


class ContextBudget:
    """
    Context budget manager with smart pruning.

    Tracks token usage across all context sources and provides
    intelligent pruning when budget limits are approached.

    Usage:
        budget = ContextBudget(
            config=BudgetConfig(max_tokens=100000)
        )

        budget.add_entry("system", system_prompt, tokens=5000)
        budget.add_entry("user_context", project_context, tokens=8000)

        if budget.is_over_budget():
            budget.smart_prune()
    """

    def __init__(self, config: Optional[BudgetConfig] = None):
        self.config = config or BudgetConfig()
        self._entries: Dict[str, ContextEntry] = {}
        self._total_tokens = 0
        self._prune_history: List[Dict[str, Any]] = []

        # Callbacks
        self._warning_callbacks: List[Callable[[BudgetStatus], None]] = []
        self._prune_callbacks: List[Callable[[List[str], int], None]] = []

    def add_entry(
        self,
        key: str,
        content: str,
        tokens: int,
        priority: ContentPriority = ContentPriority.NORMAL,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Add a context entry.

        Args:
            key: Unique identifier for the entry
            content: The actual content
            tokens: Token count for the content
            priority: Priority level (higher = keep longer)
            metadata: Optional metadata

        Returns:
            True if added, False if rejected due to budget
        """
        # Check if adding would exceed critical threshold
        projected_total = self._total_tokens + tokens
        projected_util = projected_total / self.config.max_tokens

        if projected_util >= self.config.critical_threshold:
            logger.warning(
                f"Rejecting entry '{key}': would exceed critical threshold "
                f"({projected_util:.1%})"
            )
            return False

        # Remove existing entry with same key
        if key in self._entries:
            self.remove_entry(key)

        # Add new entry
        entry = ContextEntry(
            key=key,
            content=content,
            tokens=tokens,
            priority=priority,
            metadata=metadata or {},
        )
        self._entries[key] = entry
        self._total_tokens += tokens

        # Check thresholds and trigger callbacks
        status = self.get_status()

        if status.utilization_percent >= self.config.critical_threshold:
            self._trigger_prune_callbacks()

        logger.debug(
            f"Added entry '{key}': {tokens} tokens, "
            f"total: {self._total_tokens}/{self.config.max_tokens}"
        )

        return True

    def remove_entry(self, key: str) -> bool:
        """Remove a context entry."""
        if key not in self._entries:
            return False

        entry = self._entries.pop(key)
        self._total_tokens -= entry.tokens
        logger.debug(f"Removed entry '{key}': freed {entry.tokens} tokens")
        return True

    def get_entry(self, key: str) -> Optional[ContextEntry]:
        """Get a context entry."""
        entry = self._entries.get(key)
        if entry:
            entry.touch()
        return entry

    def update_entry(self, key: str, content: str, tokens: int) -> bool:
        """Update an existing entry."""
        if key not in self._entries:
            return False

        old_entry = self._entries[key]
        if not old_entry.is_mutable:
            logger.warning(f"Entry '{key}' is not mutable")
            return False

        self._total_tokens -= old_entry.tokens
        old_entry.content = content
        old_entry.tokens = tokens
        self._total_tokens += tokens
        old_entry.touch()

        return True

    def is_over_budget(self, threshold: float = 1.0) -> bool:
        """Check if budget exceeds threshold."""
        return (self._total_tokens / self.config.max_tokens) >= threshold

    def get_status(self) -> BudgetStatus:
        """Get current budget status."""
        utilization = self._total_tokens / self.config.max_tokens

        warnings = []
        action = BudgetAction.NONE

        if utilization >= self.config.critical_threshold:
            action = BudgetAction.TRUNCATE
            warnings.append("Critical: Context budget exceeded 95%")
        elif utilization >= self.config.prune_threshold:
            action = BudgetAction.PRUNE
            warnings.append("Warning: Context budget exceeded 90%")
        elif utilization >= self.config.warning_threshold:
            action = BudgetAction.WARN
            warnings.append("Info: Context budget exceeded 80%")

        return BudgetStatus(
            total_tokens=self._total_tokens,
            max_tokens=self.config.max_tokens,
            utilization_percent=utilization * 100,
            entry_count=len(self._entries),
            over_budget=utilization >= 1.0,
            action_needed=action,
            warnings=warnings,
        )

    def smart_prune(
        self,
        target_tokens: Optional[int] = None,
    ) -> List[str]:
        """
        Intelligently prune context to fit budget.

        Args:
            target_tokens: Target token count (default: 80% of max)

        Returns:
            List of pruned entry keys
        """
        if target_tokens is None:
            target_tokens = int(self.config.max_tokens * 0.8)

        if self._total_tokens <= target_tokens:
            return []

        pruned_keys = []
        tokens_to_free = self._total_tokens - target_tokens

        logger.info(f"Smart pruning: need to free {tokens_to_free} tokens")

        # Get entries sorted by strategy
        entries = self._get_sorted_entries_for_pruning()

        for entry in entries:
            # Never prune critical priority
            if entry.priority == ContentPriority.CRITICAL:
                continue

            # Never prune below minimum
            if self._total_tokens - entry.tokens < self.config.min_retention_tokens:
                continue

            self.remove_entry(entry.key)
            pruned_keys.append(entry.key)
            tokens_to_free -= entry.tokens

            if tokens_to_free <= 0:
                break

        # Record prune history
        self._prune_history.append({
            "timestamp": datetime.now(),
            "pruned_count": len(pruned_keys),
            "tokens_freed": sum(self._entries.get(k).tokens for k in pruned_keys if k in self._entries),
            "remaining_tokens": self._total_tokens,
        })

        # Trigger callbacks
        self._trigger_prune_callbacks(pruned_keys, len(pruned_keys))

        logger.info(f"Pruned {len(pruned_keys)} entries, freed ~{self._total_tokens - target_tokens} tokens")

        return pruned_keys

    def _get_sorted_entries_for_pruning(self) -> List[ContextEntry]:
        """Get entries sorted for pruning based on strategy."""
        entries = list(self._entries.values())

        if self.config.strategy == "priority":
            # Sort by priority (low first), then by access time (old first)
            return sorted(
                entries,
                key=lambda e: (e.priority.value, e.accessed_at)
            )
        elif self.config.strategy == "lru":
            # Sort by access time (old first)
            return sorted(entries, key=lambda e: e.accessed_at)
        elif self.config.strategy == "hybrid":
            # Priority + LRU + access count
            return sorted(
                entries,
                key=lambda e: (
                    e.priority.value,
                    e.accessed_at,
                    e.access_count,
                )
            )
        else:
            return entries

    def force_prune(self, entries_to_prune: List[str]) -> int:
        """Force prune specific entries."""
        freed = 0
        for key in entries_to_prune:
            if key in self._entries:
                freed += self._entries[key].tokens
                self.remove_entry(key)
        return freed

    def get_context_summary(self) -> Dict[str, Any]:
        """Get summary of current context."""
        by_priority: Dict[str, int] = {}
        by_keyword: Dict[str, int] = {}

        for entry in self._entries.values():
            priority_name = entry.priority.name
            by_priority[priority_name] = by_priority.get(priority_name, 0) + entry.tokens

        return {
            "total_tokens": self._total_tokens,
            "max_tokens": self.config.max_tokens,
            "utilization": f"{self.get_status().utilization_percent:.1f}%",
            "entry_count": len(self._entries),
            "by_priority": by_priority,
            "entries": [
                {
                    "key": e.key,
                    "tokens": e.tokens,
                    "priority": e.priority.name,
                    "access_count": e.access_count,
                }
                for e in sorted(self._entries.values(), key=lambda x: x.priority.value)
            ],
        }

    def register_warning_callback(
        self,
        callback: Callable[[BudgetStatus], None]
    ) -> None:
        """Register callback for budget warnings."""
        self._warning_callbacks.append(callback)

    def register_prune_callback(
        self,
        callback: Callable[[List[str], int], None]
    ) -> None:
        """Register callback for prune events."""
        self._prune_callbacks.append(callback)

    def _trigger_prune_callbacks(
        self,
        pruned_keys: Optional[List[str]] = None,
        tokens_freed: int = 0,
    ) -> None:
        """Trigger registered prune callbacks."""
        for callback in self._prune_callbacks:
            try:
                callback(pruned_keys or [], tokens_freed)
            except Exception as e:
                logger.error(f"Prune callback error: {e}")

    def reset(self) -> None:
        """Reset all context."""
        self._entries.clear()
        self._total_tokens = 0
        self._prune_history.clear()


class TokenEstimator:
    """Estimate token count for text."""

    CHARS_PER_TOKEN = 4.0  # Rough average for English

    @classmethod
    def estimate(cls, text: str) -> int:
        """Estimate token count."""
        return int(len(text) / cls.CHARS_PER_TOKEN)

    @classmethod
    def estimate_messages(cls, messages: List[Dict[str, str]]) -> int:
        """Estimate tokens for a message history."""
        total = 0
        for msg in messages:
            # Count content
            total += cls.estimate(msg.get("content", ""))
            # Add overhead for role
            total += cls.estimate(msg.get("role", "user"))
        return total
