"""Rule Severity → Action Mapper.

This module provides automatic mapping from rule severity to actions,
enabling intelligent auto-fix decisions based on issue severity.

Features:
- Auto-apply LOW severity fixes
- Queue HIGH severity for review
- Warn on CRITICAL severity (require explicit approval)
- Configurable thresholds via CLI flags

Usage:
    mapper = SeverityActionMapper()
    action = mapper.get_action(issue)
    
    # Or with auto-fix configuration
    mapper = SeverityActionMapper(auto_fix_level="low")
    action = mapper.get_action(issue)
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from src.domain.models.review_issue import ReviewIssue

logger = logging.getLogger(__name__)


class ActionType(Enum):
    """Types of actions for handling issues."""
    AUTO_FIX = "auto_fix"
    REVIEW_REQUIRED = "review_required"
    WARN_CRITICAL = "warn_critical"
    SKIP = "skip"


@dataclass
class SeverityAction:
    """Action to take for an issue based on its severity."""
    action_type: ActionType
    should_apply: bool
    requires_confirmation: bool
    priority: int
    message: str


@dataclass
class SeverityMapping:
    """Configuration for severity → action mapping."""
    auto_fix_threshold: str = "low"  # low, medium, high, critical
    warn_on_critical: bool = True
    queue_for_review: list[str] = field(default_factory=list)  # rule IDs to always queue
    auto_apply_rules: list[str] = field(default_factory=list)  # rule IDs to always auto-apply
    skip_rules: list[str] = field(default_factory=list)  # rule IDs to always skip


class SeverityActionMapper:
    """Maps issue severity to recommended actions.
    
    This class provides intelligent routing of issues to appropriate
    handling strategies based on their severity level.
    
    Usage:
        mapper = SeverityActionMapper()
        action = mapper.get_action(issue)
        
        if action.should_apply:
            apply_fix(issue)
        elif action.requires_confirmation:
            prompt_user(issue, action)
    """
    
    # Severity weights for comparison
    SEVERITY_WEIGHTS = {
        "critical": 4,
        "high": 3,
        "medium": 2,
        "low": 1,
        "info": 0,
    }
    
    # Priority levels
    PRIORITY_CRITICAL = 4
    PRIORITY_HIGH = 3
    PRIORITY_MEDIUM = 2
    PRIORITY_LOW = 1
    
    def __init__(self, mapping: Optional[SeverityMapping] = None):
        """
        Args:
            mapping: Severity mapping configuration
        """
        self.mapping = mapping or SeverityMapping()
        self._build_threshold_weight()
    
    def _build_threshold_weight(self) -> None:
        """Build weight from auto_fix_threshold."""
        self._threshold_weight = self.SEVERITY_WEIGHTS.get(
            self.mapping.auto_fix_threshold, 1
        )
    
    def get_action(self, issue: ReviewIssue) -> SeverityAction:
        """Get the recommended action for an issue.
        
        Args:
            issue: The issue to evaluate
            
        Returns:
            SeverityAction with recommended action
        """
        # Check explicit rule mappings first
        if issue.rule_id in self.mapping.skip_rules:
            return SeverityAction(
                action_type=ActionType.SKIP,
                should_apply=False,
                requires_confirmation=False,
                priority=0,
                message=f"Rule {issue.rule_id} is configured to skip",
            )
        
        if issue.rule_id in self.mapping.auto_apply_rules:
            return SeverityAction(
                action_type=ActionType.AUTO_FIX,
                should_apply=True,
                requires_confirmation=False,
                priority=self._get_priority(issue.severity),
                message=f"Rule {issue.rule_id} is configured to auto-apply",
            )
        
        # Get severity level
        severity_str = self._get_severity_string(issue.severity)
        severity_weight = self.SEVERITY_WEIGHTS.get(severity_str, 0)
        
        # CRITICAL severity: always warn and require explicit approval
        if severity_weight >= self.SEVERITY_WEIGHTS["critical"]:
            return SeverityAction(
                action_type=ActionType.WARN_CRITICAL,
                should_apply=False,
                requires_confirmation=True,
                priority=self.PRIORITY_CRITICAL,
                message=f"CRITICAL issue detected: {issue.rule_id}",
            )
        
        # HIGH severity: queue for review
        if severity_weight >= self.SEVERITY_WEIGHTS["high"]:
            return SeverityAction(
                action_type=ActionType.REVIEW_REQUIRED,
                should_apply=False,
                requires_confirmation=True,
                priority=self.PRIORITY_HIGH,
                message=f"High severity issue: {issue.rule_id}",
            )
        
        # Below threshold: skip
        if severity_weight < self._threshold_weight:
            return SeverityAction(
                action_type=ActionType.SKIP,
                should_apply=False,
                requires_confirmation=False,
                priority=0,
                message=f"Below auto-fix threshold: {issue.rule_id}",
            )
        
        # At or above threshold: auto-fix
        return SeverityAction(
            action_type=ActionType.AUTO_FIX,
            should_apply=True,
            requires_confirmation=False,
            priority=self._get_priority(issue.severity),
            message=f"Auto-fix eligible: {issue.rule_id}",
        )
    
    def _get_severity_string(self, severity) -> str:
        """Get severity as string."""
        if hasattr(severity, "value"):
            return severity.value.lower()
        return str(severity).lower()
    
    def _get_priority(self, severity) -> int:
        """Get priority from severity."""
        severity_str = self._get_severity_string(severity)
        weights = {
            "critical": self.PRIORITY_CRITICAL,
            "high": self.PRIORITY_HIGH,
            "medium": self.PRIORITY_MEDIUM,
            "low": self.PRIORITY_LOW,
        }
        return weights.get(severity_str, 0)
    
    def categorize_issues(
        self,
        issues: list[ReviewIssue],
    ) -> dict[ActionType, list[ReviewIssue]]:
        """Categorize issues by recommended action.
        
        Args:
            issues: List of issues to categorize
            
        Returns:
            Dict mapping ActionType to list of issues
        """
        categorized: dict[ActionType, list[ReviewIssue]] = {
            ActionType.AUTO_FIX: [],
            ActionType.REVIEW_REQUIRED: [],
            ActionType.WARN_CRITICAL: [],
            ActionType.SKIP: [],
        }
        
        for issue in issues:
            action = self.get_action(issue)
            categorized[action.action_type].append(issue)
        
        return categorized
    
    def get_auto_fix_summary(
        self,
        issues: list[ReviewIssue],
    ) -> dict[str, int]:
        """Get summary of actions for issues.
        
        Args:
            issues: List of issues
            
        Returns:
            Dict with counts by action type
        """
        categorized = self.categorize_issues(issues)
        
        return {
            "auto_fix": len(categorized[ActionType.AUTO_FIX]),
            "review_required": len(categorized[ActionType.REVIEW_REQUIRED]),
            "warn_critical": len(categorized[ActionType.WARN_CRITICAL]),
            "skip": len(categorized[ActionType.SKIP]),
            "total": len(issues),
        }


class SeverityActionMapperCLI:
    """CLI helper for severity action mapping.
    
    Provides command-line interface integration for severity-based routing.
    """
    
    # CLI flag to severity threshold mapping
    AUTO_FIX_LEVELS = {
        "none": None,
        "low": "low",
        "medium": "medium",
        "high": "high",
        "all": "critical",
    }
    
    @classmethod
    def from_cli_args(cls, args) -> SeverityActionMapper:
        """Create mapper from CLI arguments.
        
        Args:
            args: argparse.Namespace with CLI arguments
            
        Returns:
            Configured SeverityActionMapper
        """
        # Determine auto-fix level from CLI flags
        auto_fix_level = "low"  # Default
        
        if hasattr(args, "auto_fix"):
            if args.auto_fix is True:
                auto_fix_level = "low"
            elif isinstance(args.auto_fix, str):
                auto_fix_level = args.auto_fix.lower()
        
        if hasattr(args, "auto_fix_level"):
            auto_fix_level = args.auto_fix_level
        
        # Build mapping
        mapping = SeverityMapping(
            auto_fix_threshold=auto_fix_level,
            warn_on_critical=getattr(args, "warn_critical", True),
        )
        
        return cls(mapping)
    
    @classmethod
    def add_cli_args(cls, parser) -> None:
        """Add CLI arguments for severity mapping.
        
        Args:
            parser: argparse.ArgumentParser
        """
        parser.add_argument(
            "--auto-fix",
            nargs="?",
            const="low",
            default=None,
            help="Auto-fix level: none, low, medium, high, all. "
                 "Use --auto-fix=low to auto-fix low severity issues.",
        )
        
        parser.add_argument(
            "--auto-fix-level",
            choices=["none", "low", "medium", "high", "all"],
            default="low",
            help="Severity level for auto-fix (default: low)",
        )


async def apply_auto_fixes(
    issues: list[ReviewIssue],
    mapper: SeverityActionMapper,
    apply_tool,
) -> dict[str, int]:
    """Apply fixes automatically based on severity mapping.
    
    Args:
        issues: List of issues to process
        mapper: SeverityActionMapper for routing decisions
        apply_tool: Tool to apply fixes
        
    Returns:
        Dict with counts of applied/skipped/failed
    """
    results = {"applied": 0, "skipped": 0, "failed": 0}
    
    categorized = mapper.categorize_issues(issues)
    
    # Apply auto-fix issues
    for issue in categorized[ActionType.AUTO_FIX]:
        if not issue.is_fixable or not issue.fixes:
            results["skipped"] += 1
            continue
        
        try:
            fix_result = apply_tool.apply_fix(issue)
            if fix_result.success:
                results["applied"] += 1
            else:
                results["failed"] += 1
        except Exception as e:
            logger.warning("Failed to apply fix: %s", e)
            results["failed"] += 1
    
    # Skip remaining issues
    for action_type in [ActionType.REVIEW_REQUIRED, ActionType.WARN_CRITICAL, ActionType.SKIP]:
        results["skipped"] += len(categorized[action_type])
    
    return results


def format_action_summary(
    issues: list[ReviewIssue],
    mapper: SeverityActionMapper,
) -> str:
    """Format action summary for display.
    
    Args:
        issues: List of issues
        mapper: SeverityActionMapper
        
    Returns:
        Formatted summary string
    """
    summary = mapper.get_auto_fix_summary(issues)
    
    lines = [
        "",
        "=" * 50,
        "ISSUE ACTION SUMMARY",
        "=" * 50,
        "",
        f"Total Issues:    {summary['total']}",
        f"Auto-fix:        {summary['auto_fix']}",
        f"Review Required:  {summary['review_required']}",
        f"Critical Warning: {summary['warn_critical']}",
        f"Skipped:         {summary['skip']}",
        "",
    ]
    
    if summary["auto_fix"] > 0:
        lines.append(f"  → {summary['auto_fix']} issue(s) will be auto-fixed")
    
    if summary["warn_critical"] > 0:
        lines.append(f"  ⚠ {summary['warn_critical']} CRITICAL issue(s) require explicit approval")
    
    if summary["review_required"] > 0:
        lines.append(f"  → {summary['review_required']} issue(s) queued for review")
    
    lines.append("=" * 50)
    
    return "\n".join(lines)
