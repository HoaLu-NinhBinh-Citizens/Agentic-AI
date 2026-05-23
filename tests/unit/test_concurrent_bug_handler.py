"""Tests for concurrent bug handler (Phase 8.4a)."""

import pytest
from src.infrastructure.analysis.bug_report_parser import (
    BugReport,
    BugType,
    BugSeverity,
    BugLocation,
)
from src.infrastructure.analysis.concurrent_bug_handler import (
    BugGroup,
    BugKey,
    BugPriority,
    BugPriorityCalculator,
    ConcurrentBugHandler,
    DeduplicationStrategy,
    get_concurrent_bug_handler,
)


class TestBugKey:
    """Test BugKey for deduplication."""
    
    def test_exact_match(self):
        """Test exact matching strategy."""
        bug1 = BugReport(
            title="HardFault",
            bug_type=BugType.HARD_FAULT,
            severity=BugSeverity.CRITICAL,
            location=BugLocation(function="HardFault_Handler", file="stm32f4xx_it.c"),
        )
        bug2 = BugReport(
            title="HardFault",
            bug_type=BugType.HARD_FAULT,
            severity=BugSeverity.CRITICAL,
            location=BugLocation(function="HardFault_Handler", file="stm32f4xx_it.c"),
        )
        
        key1 = BugKey.from_bug(bug1, DeduplicationStrategy.EXACT_MATCH)
        key2 = BugKey.from_bug(bug2, DeduplicationStrategy.EXACT_MATCH)
        
        assert key1.compute_hash() == key2.compute_hash()
    
    def test_different_bugs_different_keys(self):
        """Test that different bugs have different keys."""
        bug1 = BugReport(
            title="HardFault",
            bug_type=BugType.HARD_FAULT,
            severity=BugSeverity.CRITICAL,
            location=BugLocation(function="HardFault_Handler"),
        )
        bug2 = BugReport(
            title="Stack overflow",
            bug_type=BugType.STACK_OVERFLOW,
            severity=BugSeverity.CRITICAL,
            location=BugLocation(function="task_main"),
        )
        
        key1 = BugKey.from_bug(bug1)
        key2 = BugKey.from_bug(bug2)
        
        assert key1.compute_hash() != key2.compute_hash()


class TestBugGroup:
    """Test BugGroup for grouping similar bugs."""
    
    def test_representative_selection(self):
        """Test that representative bug is the most severe."""
        bug_low = BugReport(
            title="Bug A",
            bug_type=BugType.I2C_TIMEOUT,
            severity=BugSeverity.LOW,
            confidence=0.9,
        )
        bug_critical = BugReport(
            title="Bug B",
            bug_type=BugType.HARD_FAULT,
            severity=BugSeverity.CRITICAL,
            confidence=0.95,
        )
        
        group = BugGroup(
            key=BugKey.from_bug(bug_low),
            bugs=[bug_low, bug_critical],
        )
        
        # Critical bug should be representative
        assert group.representative == bug_critical
    
    def test_merge(self):
        """Test merging two bug groups."""
        bug1 = BugReport(
            title="HardFault",
            bug_type=BugType.HARD_FAULT,
            severity=BugSeverity.CRITICAL,
        )
        bug2 = BugReport(
            title="HardFault",
            bug_type=BugType.HARD_FAULT,
            severity=BugSeverity.CRITICAL,
        )
        
        group1 = BugGroup(
            key=BugKey.from_bug(bug1),
            bugs=[bug1],
            occurrence_count=1,
        )
        group2 = BugGroup(
            key=BugKey.from_bug(bug2),
            bugs=[bug2],
            occurrence_count=2,
        )
        
        group1.merge(group2)
        
        assert len(group1.bugs) == 2
        assert group1.occurrence_count == 3


class TestBugPriorityCalculator:
    """Test priority calculation."""
    
    def test_critical_bug_priority(self):
        """Test that critical bugs get high priority."""
        calculator = BugPriorityCalculator()
        
        bug = BugReport(
            title="HardFault",
            bug_type=BugType.HARD_FAULT,
            severity=BugSeverity.CRITICAL,
            confidence=0.9,
        )
        
        priority = calculator.calculate(bug, occurrence_count=1, affected_boards=1)
        
        assert priority.priority_score > 0.7
        assert priority.priority_level in ["P1 - Critical", "P2 - High"]
    
    def test_recurring_bug_boost(self):
        """Test that recurring bugs get priority boost."""
        calculator = BugPriorityCalculator()
        
        bug = BugReport(
            title="I2C timeout",
            bug_type=BugType.I2C_TIMEOUT,
            severity=BugSeverity.MEDIUM,
            confidence=0.7,
        )
        
        priority_once = calculator.calculate(bug, occurrence_count=1)
        priority_recurring = calculator.calculate(bug, occurrence_count=5)
        
        assert priority_recurring.priority_score > priority_once.priority_score
    
    def test_multi_board_impact(self):
        """Test that multi-board bugs get priority boost."""
        calculator = BugPriorityCalculator()
        
        bug = BugReport(
            title="Bug",
            bug_type=BugType.STACK_OVERFLOW,
            severity=BugSeverity.HIGH,
            confidence=0.8,
        )
        
        priority_single = calculator.calculate(bug, affected_boards=1)
        priority_multi = calculator.calculate(bug, affected_boards=10)
        
        assert priority_multi.priority_score > priority_single.priority_score


class TestConcurrentBugHandler:
    """Test concurrent bug handler."""
    
    def test_add_new_bug(self):
        """Test adding a new bug."""
        handler = ConcurrentBugHandler()
        
        bug = BugReport(
            title="HardFault",
            bug_type=BugType.HARD_FAULT,
            severity=BugSeverity.CRITICAL,
            location=BugLocation(function="HardFault_Handler"),
        )
        
        is_new, group = handler.add_bug(bug)
        
        assert is_new is True
        assert group is not None
        assert group.occurrence_count == 1
    
    def test_add_duplicate_bug(self):
        """Test adding a duplicate bug."""
        handler = ConcurrentBugHandler()
        
        bug1 = BugReport(
            title="HardFault",
            bug_type=BugType.HARD_FAULT,
            severity=BugSeverity.CRITICAL,
            location=BugLocation(function="HardFault_Handler"),
        )
        bug2 = BugReport(
            title="HardFault",
            bug_type=BugType.HARD_FAULT,
            severity=BugSeverity.CRITICAL,
            location=BugLocation(function="HardFault_Handler"),
        )
        
        handler.add_bug(bug1)
        is_new, group = handler.add_bug(bug2)
        
        assert is_new is False
        assert group is not None
        assert group.occurrence_count == 2
    
    def test_deduplicate_list(self):
        """Test deduplicating a list of bugs."""
        handler = ConcurrentBugHandler()
        
        bugs = [
            BugReport(
                title="HardFault",
                bug_type=BugType.HARD_FAULT,
                severity=BugSeverity.CRITICAL,
                location=BugLocation(function="HardFault_Handler"),
            ),
            BugReport(
                title="HardFault",
                bug_type=BugType.HARD_FAULT,
                severity=BugSeverity.CRITICAL,
                location=BugLocation(function="HardFault_Handler"),
            ),
            BugReport(
                title="Stack overflow",
                bug_type=BugType.STACK_OVERFLOW,
                severity=BugSeverity.CRITICAL,
                location=BugLocation(function="task_main"),
            ),
        ]
        
        groups = handler.deduplicate(bugs)
        
        # Should be 2 groups: HardFault and Stack overflow
        assert len(groups) == 2
    
    def test_prioritize_bugs(self):
        """Test bug prioritization."""
        handler = ConcurrentBugHandler()
        
        bugs = [
            BugReport(
                title="Low priority bug",
                bug_type=BugType.I2C_TIMEOUT,
                severity=BugSeverity.LOW,
                confidence=0.5,
            ),
            BugReport(
                title="Critical bug",
                bug_type=BugType.HARD_FAULT,
                severity=BugSeverity.CRITICAL,
                confidence=0.9,
            ),
        ]
        
        prioritized = handler.prioritize(bugs)
        
        # Critical bug should be first
        assert prioritized[0][0].bug_type == BugType.HARD_FAULT
        assert prioritized[0][1].priority_score > prioritized[1][1].priority_score
    
    def test_statistics(self):
        """Test statistics generation."""
        handler = ConcurrentBugHandler()
        
        bugs = [
            BugReport(
                title="HardFault",
                bug_type=BugType.HARD_FAULT,
                severity=BugSeverity.CRITICAL,
            ),
            BugReport(
                title="HardFault",
                bug_type=BugType.HARD_FAULT,
                severity=BugSeverity.CRITICAL,
            ),
            BugReport(
                title="Stack overflow",
                bug_type=BugType.STACK_OVERFLOW,
                severity=BugSeverity.CRITICAL,
            ),
        ]
        
        handler.deduplicate(bugs)
        stats = handler.get_statistics()
        
        assert stats["total_groups"] == 2
        assert stats["total_bugs"] == 3


class TestDeduplicationDeterminism:
    """Test that deduplication is deterministic."""
    
    def test_same_bug_always_deduplicates(self):
        """Test that the same bug always gets deduplicated."""
        handler = ConcurrentBugHandler()
        
        # Add bug 5 times
        bugs = []
        for i in range(5):
            bug = BugReport(
                title="HardFault",
                bug_type=BugType.HARD_FAULT,
                severity=BugSeverity.CRITICAL,
                location=BugLocation(function="HardFault_Handler"),
            )
            bugs.append(bug)
            handler.add_bug(bug)
        
        groups = handler.get_groups()
        assert len(groups) == 1
        assert groups[0].occurrence_count == 5
    
    def test_order_independence(self):
        """Test that order doesn't affect final result."""
        handler1 = ConcurrentBugHandler()
        handler2 = ConcurrentBugHandler()
        
        bugs = [
            BugReport(
                title="Bug A",
                bug_type=BugType.HARD_FAULT,
                severity=BugSeverity.CRITICAL,
            ),
            BugReport(
                title="Bug B",
                bug_type=BugType.STACK_OVERFLOW,
                severity=BugSeverity.HIGH,
            ),
            BugReport(
                title="Bug A",  # Duplicate of first
                bug_type=BugType.HARD_FAULT,
                severity=BugSeverity.CRITICAL,
            ),
        ]
        
        # Add in different orders
        handler1.deduplicate(bugs)
        handler2.deduplicate(list(reversed(bugs)))
        
        stats1 = handler1.get_statistics()
        stats2 = handler2.get_statistics()
        
        assert stats1["total_groups"] == stats2["total_groups"]
        assert stats1["total_bugs"] == stats2["total_bugs"]
