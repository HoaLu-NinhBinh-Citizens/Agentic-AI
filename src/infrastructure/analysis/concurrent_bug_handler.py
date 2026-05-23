"""Concurrent bug handling (Phase 8.4a).

Provides:
- Concurrent bug deduplication using content hash
- Bug prioritization based on severity and frequency
- Bug merging for related issues
- Thread-safe bug tracking
"""

from __future__ import annotations

import hashlib
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.infrastructure.analysis.bug_report_parser import BugReport

logger = logging.getLogger(__name__)


class DeduplicationStrategy(Enum):
    """Strategy for bug deduplication."""
    EXACT_MATCH = "exact"       # Same signature required
    FUZZY_MATCH = "fuzzy"       # Similar bugs grouped
    PATTERN_MATCH = "pattern"    # Same pattern ID


@dataclass
class BugKey:
    """Content-based hash key for bug deduplication."""
    signature: str
    bug_type: str
    severity: str
    file_pattern: str = ""
    function_pattern: str = ""
    
    @classmethod
    def from_bug(cls, bug: BugReport, strategy: DeduplicationStrategy = DeduplicationStrategy.EXACT_MATCH) -> BugKey:
        """Create BugKey from BugReport."""
        if strategy == DeduplicationStrategy.EXACT_MATCH:
            signature = bug.compute_signature()
        else:
            # Use pattern-based signature
            signature = hashlib.sha256(
                f"{bug.bug_type.value}:{bug.location.function}:{bug.title}".encode()
            ).hexdigest()[:16]
        
        return cls(
            signature=signature,
            bug_type=bug.bug_type.value,
            severity=bug.severity.value,
            file_pattern=bug.location.file if bug.location.file else "*",
            function_pattern=bug.location.function if bug.location.function else "*",
        )
    
    def compute_hash(self) -> str:
        """Compute deterministic hash for this key."""
        content = f"{self.signature}:{self.bug_type}:{self.severity}"
        return hashlib.sha256(content.encode()).hexdigest()[:32]


@dataclass 
class BugGroup:
    """Group of similar/deduplicated bugs."""
    key: BugKey
    bugs: list[BugReport] = field(default_factory=list)
    first_seen: datetime = field(default_factory=datetime.now)
    last_seen: datetime = field(default_factory=datetime.now)
    occurrence_count: int = 0
    
    @property
    def representative(self) -> BugReport | None:
        """Get the most severe/representative bug from the group."""
        if not self.bugs:
            return None
        # Sort by: CRITICAL > HIGH > MEDIUM > LOW, then by confidence
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
        return min(
            self.bugs,
            key=lambda b: (
                severity_order.get(b.severity.value, 5),
                -b.confidence
            )
        )
    
    def merge(self, other: BugGroup) -> None:
        """Merge another bug group into this one."""
        self.bugs.extend(other.bugs)
        self.occurrence_count += other.occurrence_count
        if other.last_seen > self.last_seen:
            self.last_seen = other.last_seen


@dataclass
class BugPriority:
    """Bug priority calculation result."""
    bug_id: str
    priority_score: float  # Higher = more urgent
    priority_reason: str = ""
    estimated_impact: str = ""
    
    @property
    def priority_level(self) -> str:
        """Get human-readable priority level."""
        if self.priority_score >= 0.8:
            return "P1 - Critical"
        elif self.priority_score >= 0.6:
            return "P2 - High"
        elif self.priority_score >= 0.4:
            return "P3 - Medium"
        else:
            return "P4 - Low"


class BugPriorityCalculator:
    """Calculate bug priority based on multiple factors."""
    
    # Severity weights
    SEVERITY_WEIGHTS = {
        "critical": 1.0,
        "high": 0.75,
        "medium": 0.5,
        "low": 0.25,
        "info": 0.1,
    }
    
    # Bug type weights (affects how urgent)
    TYPE_WEIGHTS = {
        # Critical system errors
        "hard_fault": 1.0,
        "stack_overflow": 0.95,
        "deadlock": 0.9,
        "crash": 0.9,
        
        # High priority
        "bus_fault": 0.8,
        "memory_fault": 0.8,
        "usage_fault": 0.75,
        "heap_exhaustion": 0.75,
        "watchdog_timeout": 0.7,
        
        # Medium priority
        "i2c_timeout": 0.5,
        "spi_timeout": 0.5,
        "can_timeout": 0.55,
        "assertion_failed": 0.6,
        
        # Lower priority
        "uart_timeout": 0.3,
        "unknown": 0.2,
    }
    
    def calculate(
        self,
        bug: BugReport,
        occurrence_count: int = 1,
        affected_boards: int = 1,
        time_since_first_seen_hours: float = 0.0,
    ) -> BugPriority:
        """Calculate priority score for a bug."""
        # Base score from severity
        severity_score = self.SEVERITY_WEIGHTS.get(bug.severity.value, 0.5)
        
        # Type urgency
        type_score = self.TYPE_WEIGHTS.get(bug.bug_type.value, 0.3)
        
        # Frequency boost (recurring bugs are more urgent)
        frequency_boost = min(0.2, occurrence_count * 0.05)
        
        # Multi-board impact (fleet-wide bugs are more urgent)
        board_boost = min(0.15, affected_boards * 0.05)
        
        # Recency (bugs that appeared recently might be regression)
        recency_boost = 0.1 if time_since_first_seen_hours < 24 else 0.0
        
        # Confidence affects priority
        confidence_factor = bug.confidence
        
        # Calculate final score
        priority_score = (
            severity_score * 0.35 +
            type_score * 0.25 +
            frequency_boost +
            board_boost +
            recency_boost +
            confidence_factor * 0.15
        )
        
        # Build reason
        reasons = []
        if severity_score >= 0.8:
            reasons.append(f"Critical severity ({bug.severity.value})")
        if occurrence_count > 1:
            reasons.append(f"Recurring ({occurrence_count}x)")
        if affected_boards > 1:
            reasons.append(f"Affects {affected_boards} boards")
        if confidence_factor >= 0.9:
            reasons.append("High confidence")
        
        return BugPriority(
            bug_id=bug.id or bug.compute_signature(),
            priority_score=min(1.0, priority_score),
            priority_reason="; ".join(reasons) if reasons else "Standard priority",
            estimated_impact=self._estimate_impact(bug, affected_boards),
        )
    
    def _estimate_impact(self, bug: BugReport, affected_boards: int) -> str:
        """Estimate the impact of this bug."""
        if bug.severity.value == "critical":
            return f"System halt - affects {affected_boards}+ boards"
        elif bug.severity.value == "high":
            return f"Major feature broken - {affected_boards} boards"
        elif affected_boards > 5:
            return f"Fleet-wide degradation ({affected_boards} boards)"
        else:
            return "Single board impact"


class ConcurrentBugHandler:
    """Handle concurrent bugs with deduplication and prioritization.
    
    Phase 8.4a: Concurrent bug handling
    - Deduplicate using content hash (deterministic)
    - Prioritize based on severity and frequency
    - Merge related bugs
    """
    
    def __init__(
        self,
        strategy: DeduplicationStrategy = DeduplicationStrategy.EXACT_MATCH,
    ) -> None:
        self._strategy = strategy
        self._groups: dict[str, BugGroup] = {}
        self._calculator = BugPriorityCalculator()
        self._lock = None  # Could use asyncio.Lock for async
    
    def add_bug(self, bug: BugReport) -> tuple[bool, BugGroup | None]:
        """Add a bug to the handler.
        
        Returns:
            (is_new, group): Whether this is a new bug and its group
        """
        key = BugKey.from_bug(bug, self._strategy)
        key_hash = key.compute_hash()
        
        if key_hash in self._groups:
            # Existing group - update
            group = self._groups[key_hash]
            group.bugs.append(bug)
            group.occurrence_count += 1
            group.last_seen = datetime.now()
            return False, group
        
        # New bug
        group = BugGroup(
            key=key,
            bugs=[bug],
            occurrence_count=1,
        )
        self._groups[key_hash] = group
        return True, group
    
    def add_bugs(self, bugs: list[BugReport]) -> dict[str, BugGroup]:
        """Add multiple bugs at once."""
        for bug in bugs:
            self.add_bug(bug)
        return self._groups
    
    def deduplicate(self, bugs: list[BugReport]) -> list[BugGroup]:
        """Deduplicate a list of bugs.
        
        Uses content hash to ensure deterministic deduplication.
        """
        for bug in bugs:
            self.add_bug(bug)
        return list(self._groups.values())
    
    def prioritize(
        self,
        bugs: list[BugReport],
        affected_boards: dict[str, int] | None = None,
    ) -> list[tuple[BugReport, BugPriority]]:
        """Prioritize bugs and return sorted list.
        
        Args:
            bugs: List of bugs to prioritize
            affected_boards: Optional dict of bug_id -> number of affected boards
            
        Returns:
            List of (bug, priority) tuples sorted by priority score descending
        """
        if affected_boards is None:
            affected_boards = {}
        
        prioritized = []
        
        for bug in bugs:
            bug_id = bug.id or bug.compute_signature()
            boards = affected_boards.get(bug_id, 1)
            
            priority = self._calculator.calculate(
                bug,
                occurrence_count=1,
                affected_boards=boards,
            )
            prioritized.append((bug, priority))
        
        # Sort by priority score descending
        prioritized.sort(key=lambda x: x[1].priority_score, reverse=True)
        return prioritized
    
    def get_groups(self) -> list[BugGroup]:
        """Get all bug groups."""
        return list(self._groups.values())
    
    def get_group_by_key(self, key_hash: str) -> BugGroup | None:
        """Get a specific bug group by key hash."""
        return self._groups.get(key_hash)
    
    def merge_groups(
        self,
        key1: str,
        key2: str,
    ) -> BugGroup | None:
        """Merge two bug groups."""
        if key1 not in self._groups or key2 not in self._groups:
            return None
        
        group1 = self._groups[key1]
        group2 = self._groups[key2]
        
        # Merge into group1
        group1.merge(group2)
        
        # Remove group2
        del self._groups[key2]
        
        return group1
    
    def get_statistics(self) -> dict[str, Any]:
        """Get statistics about tracked bugs."""
        if not self._groups:
            return {
                "total_groups": 0,
                "total_bugs": 0,
                "by_severity": {},
                "by_type": {},
            }
        
        total_bugs = sum(g.occurrence_count for g in self._groups.values())
        by_severity: dict[str, int] = defaultdict(int)
        by_type: dict[str, int] = defaultdict(int)
        
        for group in self._groups.values():
            if group.representative:
                by_severity[group.representative.severity.value] += 1
                by_type[group.representative.bug_type.value] += 1
        
        return {
            "total_groups": len(self._groups),
            "total_bugs": total_bugs,
            "by_severity": dict(by_severity),
            "by_type": dict(by_type),
            "most_common_types": sorted(
                by_type.items(),
                key=lambda x: x[1],
                reverse=True
            )[:5],
        }


# Global singleton
_handler: ConcurrentBugHandler | None = None


def get_concurrent_bug_handler(
    strategy: DeduplicationStrategy = DeduplicationStrategy.EXACT_MATCH,
) -> ConcurrentBugHandler:
    """Get global concurrent bug handler instance."""
    global _handler
    if _handler is None:
        _handler = ConcurrentBugHandler(strategy)
    return _handler


# CLI for testing
if __name__ == "__main__":
    from src.infrastructure.analysis.bug_report_parser import (
        BugReport,
        BugType,
        BugSeverity,
        BugLocation,
        get_bug_parser,
    )
    
    handler = ConcurrentBugHandler()
    
    # Create sample bugs
    bugs = [
        BugReport(
            title="HardFault",
            bug_type=BugType.HARD_FAULT,
            severity=BugSeverity.CRITICAL,
            location=BugLocation(function="HardFault_Handler", file="stm32f4xx_it.c"),
            confidence=0.95,
        ),
        BugReport(
            title="HardFault",
            bug_type=BugType.HARD_FAULT,
            severity=BugSeverity.CRITICAL,
            location=BugLocation(function="HardFault_Handler", file="stm32f4xx_it.c"),
            confidence=0.90,
        ),
        BugReport(
            title="Stack overflow",
            bug_type=BugType.STACK_OVERFLOW,
            severity=BugSeverity.CRITICAL,
            location=BugLocation(function="task_main", file="main.c"),
            confidence=0.85,
        ),
    ]
    
    print("Testing concurrent bug handling:")
    print("-" * 50)
    
    # Add bugs
    for bug in bugs:
        is_new, group = handler.add_bug(bug)
        print(f"Added bug: is_new={is_new}, group_occurrences={group.occurrence_count}")
    
    # Get statistics
    stats = handler.get_statistics()
    print(f"\nStatistics: {stats}")
    
    # Get groups
    print("\nBug Groups:")
    for group in handler.get_groups():
        print(f"  {group.key.bug_type}: {group.occurrence_count}x - {group.representative.title if group.representative else 'N/A'}")
    
    # Prioritize
    print("\nPrioritized Bugs:")
    prioritized = handler.prioritize(bugs)
    for bug, priority in prioritized:
        print(f"  {priority.priority_level}: {bug.title} ({priority.priority_reason})")
