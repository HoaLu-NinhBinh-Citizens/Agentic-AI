"""
Memory Conflict Detector - Detects and resolves rule conflicts in AI_SUPPORT memory.

This module prevents AI from learning contradictory rules like:
- "Add 5ms delay" vs "No delay in ISR"
- "Use polling" vs "Use interrupts"

Usage:
    detector = ConflictDetector()
    
    # Check before adding a new rule
    conflicts = detector.check_conflicts(
        new_rule="Add delay 5ms after init",
        existing_rules=["No delay in interrupt handlers"],
        context={"domain": "firmware", "scope": "isr"}
    )
    
    if conflicts:
        resolution = detector.resolve_conflict(conflicts)
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple

from src.core.config.agent_prompts import GENERIC_QUERY_STOPWORDS


class ConflictSeverity(Enum):
    """Severity level of a rule conflict."""
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    BLOCKING = "blocking"


class ResolutionStrategy(Enum):
    """Strategy for resolving conflicts."""
    KEEP_BOTH = "keep_both"
    KEEP_NEW = "keep_new"
    KEEP_OLD = "keep_old"
    MERGE = "merge"
    ESCALATE = "escalate"  # Requires human review
    REJECT_NEW = "reject_new"


@dataclass
class RuleConflict:
    """Represents a conflict between rules."""
    conflict_id: str
    new_rule: str
    existing_rule: str
    severity: ConflictSeverity
    conflict_type: str  # "contradiction", "overlap", "obsolescence"
    affected_fields: List[str] = field(default_factory=list)
    evidence: List[str] = field(default_factory=list)
    timestamp: str = ""
    resolution: Optional[ResolutionStrategy] = None
    resolution_reason: str = ""


@dataclass
class ConflictCheckResult:
    """Result of conflict detection."""
    has_conflicts: bool
    conflicts: List[RuleConflict] = field(default_factory=list)
    blocking_conflicts: List[RuleConflict] = field(default_factory=list)
    severity: ConflictSeverity = ConflictSeverity.NONE
    recommendation: str = ""
    requires_human_review: bool = False


@dataclass
class ConflictResolution:
    """Resolution for a set of conflicts."""
    strategy: ResolutionStrategy
    conflicts_resolved: int
    rules_to_add: List[str] = field(default_factory=list)
    rules_to_modify: List[Dict] = field(default_factory=list)
    rules_to_reject: List[str] = field(default_factory=list)
    requires_human_review: bool = False
    reasoning: str = ""


class ConflictDetector:
    """
    Detects and resolves conflicts in AI_SUPPORT memory rules.
    
    Prevents AI from learning contradictory rules that would cause
    confusion during code generation.
    """

    # Contradictory keyword pairs
    CONTRADICTION_PAIRS = [
        # Timing conflicts
        (r"\bdelay\b", r"\bno\s+delay\b"),
        (r"\bpolling\b", r"\binterrupt\b"),
        (r"\bblocking\b", r"\bnon.?blocking\b"),
        # DMA vs Interrupt
        (r"\bdma\b", r"\binterrupt.?driven\b"),
        # Synchronous vs Async
        (r"\bsync\b", r"\basync\b"),
        # Conservative vs Aggressive
        (r"\bconservative\b", r"\baggressive\b"),
        # Check vs Skip
        (r"\bcheck\b", r"\bskip\b"),
        # Memory allocation
        (r"\bmalloc\b", r"\bstatic\b"),
        (r"\bdynamic\b.*\balloc\b", r"\bno\s+alloc\b"),
        # Error handling
        (r"\bretry\b", r"\bfail\s+fast\b"),
    ]

    # Critical fields that trigger HIGH severity when conflicting
    CRITICAL_FIELDS = {
        "voltage", "current", "pinout", "power", "timing",
        "interrupt", "dma", "memory", "clock", "register"
    }

    # Context keywords that affect resolution strategy
    CONTEXT_RULES = {
        "isr": {"keywords": [r"\bisr\b", r"\binterrupt\b", r"\bhandler\b"]},
        "firmware": {"keywords": [r"\bfirmware\b", r"\bdriver\b", r"\bregister\b"]},
        "performance": {"keywords": [r"\boptimize\b", r"\bperformance\b", r"\bspeed\b"]},
        "safety": {"keywords": [r"\bsafe\b", r"\breliable\b", r"\bcheck\b"]},
    }

    def __init__(self):
        self._history: List[ConflictCheckResult] = []
        self._cached_conflicts: Dict[str, List[RuleConflict]] = {}

    def check_conflicts(
        self,
        new_rule: str,
        existing_rules: List[str],
        context: Optional[Dict] = None,
    ) -> ConflictCheckResult:
        """
        Check if a new rule conflicts with existing rules.
        
        Args:
            new_rule: The rule to be added
            existing_rules: List of existing approved rules
            context: Optional context (domain, scope, priority)
            
        Returns:
            ConflictCheckResult with all detected conflicts
        """
        context = context or {}
        conflicts: List[RuleConflict] = []
        
        for existing in existing_rules:
            conflict = self._detect_pairwise_conflict(new_rule, existing, context)
            if conflict and conflict.severity != ConflictSeverity.NONE:
                conflicts.append(conflict)

        # Deduplicate by conflict type
        unique_conflicts = self._deduplicate_conflicts(conflicts)
        
        # Determine overall severity
        blocking = [c for c in unique_conflicts if c.severity == ConflictSeverity.BLOCKING]
        high = [c for c in unique_conflicts if c.severity == ConflictSeverity.HIGH]
        
        if blocking:
            overall_severity = ConflictSeverity.BLOCKING
            requires_review = True
        elif high:
            overall_severity = ConflictSeverity.HIGH
            requires_review = True
        elif unique_conflicts:
            overall_severity = ConflictSeverity.MEDIUM
            requires_review = False
        else:
            overall_severity = ConflictSeverity.NONE
            requires_review = False

        result = ConflictCheckResult(
            has_conflicts=len(unique_conflicts) > 0,
            conflicts=unique_conflicts,
            blocking_conflicts=blocking,
            severity=overall_severity,
            requires_human_review=requires_review,
            recommendation=self._generate_recommendation(unique_conflicts, overall_severity),
        )
        
        self._history.append(result)
        return result

    def _detect_pairwise_conflict(
        self,
        new_rule: str,
        existing_rule: str,
        context: Dict,
    ) -> Optional[RuleConflict]:
        """Detect conflict between two rules."""
        new_lower = new_rule.lower()
        existing_lower = existing_rule.lower()
        
        # Skip if rules are identical
        if new_lower == existing_lower:
            return None

        # Check for direct contradictions
        for pattern_a, pattern_b in self.CONTRADICTION_PAIRS:
            has_a_new = bool(re.search(pattern_a, new_lower))
            has_a_existing = bool(re.search(pattern_a, existing_lower))
            has_b_new = bool(re.search(pattern_b, new_lower))
            has_b_existing = bool(re.search(pattern_b, existing_lower))
            
            # Direct contradiction: new says A, existing says B
            if (has_a_new and has_b_existing) or (has_b_new and has_a_existing):
                severity = self._assess_conflict_severity(
                    new_rule, existing_rule, context
                )
                return RuleConflict(
                    conflict_id=self._generate_conflict_id(new_rule, existing_rule),
                    new_rule=new_rule,
                    existing_rule=existing_rule,
                    severity=severity,
                    conflict_type="contradiction",
                    affected_fields=self._extract_affected_fields(new_rule, existing_rule),
                    evidence=[f"Contradictory patterns: '{pattern_a}' vs '{pattern_b}'"],
                    timestamp=datetime.now().isoformat(),
                )

        # Check for semantic overlap that might cause issues
        overlap = self._check_semantic_overlap(new_lower, existing_lower)
        if overlap > 0.8:  # High overlap might indicate redundant/conflicting rules
            return RuleConflict(
                conflict_id=self._generate_conflict_id(new_rule, existing_rule),
                new_rule=new_rule,
                existing_rule=existing_rule,
                severity=ConflictSeverity.LOW,
                conflict_type="overlap",
                affected_fields=self._extract_affected_fields(new_rule, existing_rule),
                evidence=[f"High semantic overlap: {overlap:.1%}"],
                timestamp=datetime.now().isoformat(),
            )

        return None

    def _assess_conflict_severity(
        self,
        new_rule: str,
        existing_rule: str,
        context: Dict,
    ) -> ConflictSeverity:
        """Assess how severe a conflict is."""
        combined = f"{new_rule} {existing_rule}".lower()
        
        # Check for critical field conflicts
        critical_hits = sum(1 for field in self.CRITICAL_FIELDS if field in combined)
        if critical_hits >= 2:
            return ConflictSeverity.BLOCKING
        if critical_hits == 1:
            return ConflictSeverity.HIGH
            
        # Check context-specific rules
        scope = context.get("scope", "").lower()
        domain = context.get("domain", "").lower()
        
        if scope == "isr":
            if any(kw in combined for kw in ["delay", "block", "alloc", "malloc"]):
                return ConflictSeverity.HIGH
                
        if domain == "firmware":
            if any(kw in combined for kw in ["register", "dma", "interrupt"]):
                return ConflictSeverity.HIGH
                
        return ConflictSeverity.MEDIUM

    def _check_semantic_overlap(self, text_a: str, text_b: str) -> float:
        """Calculate semantic overlap between two text strings."""
        tokens_a = set(self._tokenize(text_a))
        tokens_b = set(self._tokenize(text_b))
        
        if not tokens_a or not tokens_b:
            return 0.0
            
        intersection = tokens_a & tokens_b
        union = tokens_a | tokens_b
        
        return len(intersection) / len(union) if union else 0.0

    def _tokenize(self, text: str) -> Set[str]:
        """Extract meaningful tokens from text."""
        tokens = re.findall(r"[a-z0-9_]+", text.lower())
        return {
            t for t in tokens 
            if len(t) >= 3 and t not in GENERIC_QUERY_STOPWORDS
        }

    def _extract_affected_fields(self, rule_a: str, rule_b: str) -> List[str]:
        """Extract which fields/aspects are affected by the conflict."""
        combined = f"{rule_a} {rule_b}".lower()
        fields = []
        
        field_keywords = {
            "timing": ["delay", "timing", "wait", "sleep"],
            "interrupt": ["interrupt", "isr", "handler", "irq", "nvic"],
            "memory": ["malloc", "alloc", "free", "heap", "stack", "static"],
            "dma": ["dma", "transfer", "channel"],
            "polling": ["poll", "blocking", "sync"],
        }
        
        for field, keywords in field_keywords.items():
            if any(kw in combined for kw in keywords):
                fields.append(field)
                
        return fields

    def _generate_conflict_id(self, rule_a: str, rule_b: str) -> str:
        """Generate unique ID for a conflict pair."""
        combined = f"{rule_a}|{rule_b}"
        return str(abs(hash(combined)))[:16]

    def _deduplicate_conflicts(self, conflicts: List[RuleConflict]) -> List[RuleConflict]:
        """Remove duplicate conflicts based on conflict_id."""
        seen = set()
        unique = []
        for conflict in conflicts:
            if conflict.conflict_id not in seen:
                seen.add(conflict.conflict_id)
                unique.append(conflict)
        return unique

    def _generate_recommendation(
        self,
        conflicts: List[RuleConflict],
        severity: ConflictSeverity,
    ) -> str:
        """Generate human-readable recommendation."""
        if severity == ConflictSeverity.NONE:
            return "No conflicts detected. Rule can be added."
        if severity == ConflictSeverity.BLOCKING:
            return "BLOCKING conflict detected. Human review required before adding rule."
        if severity == ConflictSeverity.HIGH:
            return "HIGH severity conflict. Consider resolution strategy before adding."
        return f"Found {len(conflicts)} conflict(s). Review recommended."

    def resolve_conflict(
        self,
        conflicts: List[RuleConflict],
        strategy: Optional[ResolutionStrategy] = None,
    ) -> ConflictResolution:
        """
        Resolve a set of conflicts using the specified or optimal strategy.
        
        Args:
            conflicts: List of conflicts to resolve
            strategy: Optional manual strategy selection
            
        Returns:
            ConflictResolution with actions to take
        """
        if not conflicts:
            return ConflictResolution(
                strategy=ResolutionStrategy.KEEP_BOTH,
                conflicts_resolved=0,
                reasoning="No conflicts to resolve.",
            )

        # Auto-select strategy based on severity
        if strategy is None:
            max_severity = max(c.severity for c in conflicts)
            blocking = any(c.severity == ConflictSeverity.BLOCKING for c in conflicts)
            
            if blocking:
                strategy = ResolutionStrategy.ESCALATE
            elif max_severity == ConflictSeverity.HIGH:
                strategy = ResolutionStrategy.ESCALATE
            elif max_severity == ConflictSeverity.MEDIUM:
                strategy = ResolutionStrategy.MERGE
            else:
                strategy = ResolutionStrategy.KEEP_BOTH

        rules_to_add = []
        rules_to_reject = []
        rules_to_modify = []

        for conflict in conflicts:
            conflict.resolution = strategy
            conflict.resolution_reason = self._get_resolution_reason(strategy)
            
            if strategy == ResolutionStrategy.KEEP_NEW:
                rules_to_reject.append(conflict.existing_rule)
                rules_to_add.append(conflict.new_rule)
            elif strategy == ResolutionStrategy.KEEP_OLD:
                rules_to_reject.append(conflict.new_rule)
            elif strategy == ResolutionStrategy.MERGE:
                merged = self._merge_rules(conflict.new_rule, conflict.existing_rule)
                rules_to_add.append(merged)
                rules_to_modify.append({
                    "original": [conflict.new_rule, conflict.existing_rule],
                    "merged": merged,
                })
            elif strategy == ResolutionStrategy.ESCALATE:
                # Mark for human review
                pass

        return ConflictResolution(
            strategy=strategy,
            conflicts_resolved=len(conflicts),
            rules_to_add=rules_to_add,
            rules_to_modify=rules_to_modify,
            rules_to_reject=rules_to_reject,
            requires_human_review=strategy == ResolutionStrategy.ESCALATE,
            reasoning=self._get_resolution_reason(strategy),
        )

    def _merge_rules(self, rule_a: str, rule_b: str) -> str:
        """Merge two conflicting rules into one coherent rule."""
        # Simple merge: take the more conservative option
        merged = rule_a
        if "no " in rule_b.lower() or "never" in rule_b.lower():
            # Prefer the more restrictive rule
            if len(rule_b) < len(rule_a):
                merged = rule_b
        return merged

    def _get_resolution_reason(self, strategy: ResolutionStrategy) -> str:
        """Get human-readable reason for a resolution strategy."""
        reasons = {
            ResolutionStrategy.KEEP_BOTH: "Low severity - rules can coexist",
            ResolutionStrategy.KEEP_NEW: "Newer rule takes precedence",
            ResolutionStrategy.KEEP_OLD: "Existing rule is more established",
            ResolutionStrategy.MERGE: "Rules merged into a unified statement",
            ResolutionStrategy.ESCALATE: "Human review required due to high severity",
            ResolutionStrategy.REJECT_NEW: "New rule rejected to preserve consistency",
        }
        return reasons.get(strategy, "Unknown resolution strategy")

    def check_before_insert(
        self,
        new_rule: str,
        memory_store,
        context: Optional[Dict] = None,
    ) -> Tuple[bool, ConflictCheckResult]:
        """
        Check for conflicts before inserting a new rule into memory.
        
        Args:
            new_rule: The rule to be inserted
            memory_store: AgentMemory store instance
            context: Optional context dict
            
        Returns:
            Tuple of (can_insert, conflict_result)
        """
        # Get existing rules from memory
        existing_rules = memory_store.get_recent_lessons(limit=50)
        existing_rules.extend([
            str(item.get("rule", "")) 
            for item in memory_store.data.get("rules", [])
        ])
        
        # Also check pattern_kb and project_kb
        for layer in ["pattern_kb", "project_kb"]:
            for item in memory_store.data.get(layer, []):
                if isinstance(item, dict):
                    rule = item.get("rule") or item.get("new_value") or ""
                    if rule:
                        existing_rules.append(str(rule))

        result = self.check_conflicts(new_rule, existing_rules, context)
        
        can_insert = (
            not result.has_conflicts or 
            result.severity in (ConflictSeverity.NONE, ConflictSeverity.LOW)
        )
        
        return can_insert, result

    def get_conflict_history(self) -> List[ConflictCheckResult]:
        """Get history of conflict checks."""
        return self._history.copy()

    def clear_history(self) -> None:
        """Clear conflict check history."""
        self._history.clear()
        self._cached_conflicts.clear()
