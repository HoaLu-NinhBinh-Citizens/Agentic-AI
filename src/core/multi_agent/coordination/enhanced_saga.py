"""
Enhanced Saga Compensation with SideEffectClassification and CompensationIrreversibilityPolicy.

This module addresses the reality that distributed saga compensation is:
- SEMANTIC compensation, not true rollback
- Handles irreversible operations (email sent, payments processed)
- Classifies side effects by reversibility
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class SideEffectType(str, Enum):
    """Classification of side effect types."""
    REVERSIBLE = "reversible"       # Can be fully undone
    PARTIALLY_REVERSIBLE = "partial" # Can be partially compensated
    IRREVERSIBLE = "irreversible"    # Cannot be undone
    INCREASING_COST = "increasing"  # Cost increases over time
    TIME_SENSITIVE = "time_sensitive" # Must be compensated quickly


class CompensationStrategy(str, Enum):
    """Strategy when full compensation is not possible."""
    COMPENSATE = "compensate"           # Do compensating action
    NOTIFY = "notify"                   # Notify for manual intervention
    ESCALATE = "escalate"               # Escalate to human
    IGNORE = "ignore"                  # Accept the side effect
    INSURANCE = "insurance"             # Insurance/guarantee coverage


@dataclass
class SideEffect:
    """Describes a side effect of a saga step."""
    step_id: str
    effect_type: SideEffectType
    resource_id: str
    description: str
    occurred_at: datetime
    compensation_possible: bool
    compensation_deadline: Optional[datetime] = None
    estimated_undo_cost: float = 0.0
    risk_level: str = "low"  # low, medium, high, critical


@dataclass
class CompensationIrreversibilityPolicy:
    """Policy for handling irreversible side effects."""
    side_effect_type: SideEffectType
    strategy: CompensationStrategy
    requires_approval: bool = False
    approval_timeout_seconds: int = 300
    notify_channels: List[str] = field(default_factory=list)
    max_retries: int = 0
    fallback_resource: Optional[str] = None


@dataclass
class CompensationResult:
    """Result of compensating a step."""
    step_id: str
    success: bool
    side_effect_classified: SideEffect
    strategy_used: CompensationStrategy
    compensation_completed: bool
    remaining_risk: List[str]
    manual_intervention_required: bool
    error: Optional[str] = None


class SideEffectClassifier:
    """
    Classifies side effects by reversibility.
    
    Production patterns:
    - REVERSIBLE: Refund processed, reservation cancelled, lock released
    - PARTIALLY_REVERSIBLE: Discount applied, partial refund, usage reduced
    - IRREVERSIBLE: Email sent, SMS delivered, webhook called
    - INCREASING_COST: Compute resources running, storage growing
    - TIME_SENSITIVE: Session tokens, temporary access, time-limited locks
    """
    
    # Patterns for side effect detection
    IRREVERSIBLE_PATTERNS = [
        ("email_sent", SideEffectType.IRREVERSIBLE),
        ("sms_sent", SideEffectType.IRREVERSIBLE),
        ("webhook_called", SideEffectType.IRREVERSIBLE),
        ("notification_pushed", SideEffectType.IRREVERSIBLE),
        ("log_written", SideEffectType.IRREVERSIBLE),
        ("audit_record", SideEffectType.IRREVERSIBLE),
        ("blockchain_tx", SideEffectType.IRREVERSIBLE),
        ("document_signed", SideEffectType.IRREVERSIBLE),
    ]
    
    PARTIALLY_REVERSIBLE_PATTERNS = [
        ("partial_refund", SideEffectType.PARTIALLY_REVERSIBLE),
        ("discount_applied", SideEffectType.PARTIALLY_REVERSIBLE),
        ("usage_started", SideEffectType.PARTIALLY_REVERSIBLE),
        ("license_granted", SideEffectType.PARTIALLY_REVERSIBLE),
    ]
    
    INCREASING_COST_PATTERNS = [
        ("compute_started", SideEffectType.INCREASING_COST),
        ("storage_allocated", SideEffectType.INCREASING_COST),
        ("bandwidth_consumed", SideEffectType.INCREASING_COST),
        ("api_quota_used", SideEffectType.INCREASING_COST),
    ]
    
    TIME_SENSITIVE_PATTERNS = [
        ("session_started", SideEffectType.TIME_SENSITIVE),
        ("lease_acquired", SideEffectType.TIME_SENSITIVE),
        ("rate_limit_token", SideEffectType.TIME_SENSITIVE),
        ("circuit_breaker_tripped", SideEffectType.TIME_SENSITIVE),
    ]
    
    def __init__(self):
        self._classification_cache: Dict[str, SideEffectType] = {}
    
    def classify(self, action_name: str, context: Dict[str, Any]) -> SideEffectType:
        """Classify side effect type from action name and context."""
        # Check cache
        if action_name in self._classification_cache:
            return self._classification_cache[action_name]
        
        # Check patterns
        action_lower = action_name.lower()
        
        for pattern, effect_type in self.IRREVERSIBLE_PATTERNS:
            if pattern in action_lower:
                self._classification_cache[action_name] = effect_type
                return effect_type
        
        for pattern, effect_type in self.PARTIALLY_REVERSIBLE_PATTERNS:
            if pattern in action_lower:
                self._classification_cache[action_name] = effect_type
                return effect_type
        
        for pattern, effect_type in self.INCREASING_COST_PATTERNS:
            if pattern in action_lower:
                self._classification_cache[action_name] = effect_type
                return effect_type
        
        for pattern, effect_type in self.TIME_SENSITIVE_PATTERNS:
            if pattern in action_lower:
                self._classification_cache[action_name] = effect_type
                return effect_type
        
        # Default to REVERSIBLE (optimistic)
        self._classification_cache[action_name] = SideEffectType.REVERSIBLE
        return SideEffectType.REVERSIBLE
    
    def classify_from_result(self, step_result: Any) -> SideEffectType:
        """Classify from step execution result."""
        # Check result type hints or patterns
        if isinstance(step_result, dict):
            if step_result.get("sent") or step_result.get("delivered"):
                return SideEffectType.IRREVERSIBLE
            if step_result.get("refund"):
                return SideEffectType.PARTIALLY_REVERSIBLE
            if step_result.get("allocated"):
                return SideEffectType.INCREASING_COST
        
        return SideEffectType.REVERSIBLE


class IrreversibilityPolicyEngine:
    """
    Engine for handling irreversible side effects.
    
    Applies CompensationIrreversibilityPolicy when full rollback is impossible.
    """
    
    def __init__(self):
        self._policies: Dict[SideEffectType, CompensationIrreversibilityPolicy] = {}
        self._pending_escalations: List[Dict[str, Any]] = []
        self._notification_queue: List[Dict[str, Any]] = []
        self._lock = asyncio.Lock()
        
        # Default policies
        self._set_defaults()
    
    def _set_defaults(self):
        """Set default policies for each side effect type."""
        self._policies = {
            SideEffectType.IRREVERSIBLE: CompensationIrreversibilityPolicy(
                side_effect_type=SideEffectType.IRREVERSIBLE,
                strategy=CompensationStrategy.NOTIFY,
                requires_approval=True,
                approval_timeout_seconds=300,
                notify_channels=["ops-alerts", "manual-review"],
            ),
            SideEffectType.PARTIALLY_REVERSIBLE: CompensationIrreversibilityPolicy(
                side_effect_type=SideEffectType.PARTIALLY_REVERSIBLE,
                strategy=CompensationStrategy.COMPENSATE,
                requires_approval=False,
            ),
            SideEffectType.INCREASING_COST: CompensationIrreversibilityPolicy(
                side_effect_type=SideEffectType.INCREASING_COST,
                strategy=CompensationStrategy.COMPENSATE,
                requires_approval=False,
            ),
            SideEffectType.TIME_SENSITIVE: CompensationIrreversibilityPolicy(
                side_effect_type=SideEffectType.TIME_SENSITIVE,
                strategy=CompensationStrategy.COMPENSATE,
                requires_approval=False,
                max_retries=3,
            ),
        }
    
    def set_policy(self, policy: CompensationIrreversibilityPolicy) -> None:
        """Set custom policy for side effect type."""
        self._policies[policy.side_effect_type] = policy
    
    def get_policy(self, side_effect_type: SideEffectType) -> CompensationIrreversibilityPolicy:
        """Get policy for side effect type."""
        return self._policies.get(
            side_effect_type,
            CompensationIrreversibilityPolicy(
                side_effect_type=side_effect_type,
                strategy=CompensationStrategy.IGNORE,
            )
        )
    
    async def handle_irreversibility(
        self,
        side_effect: SideEffect,
    ) -> CompensationResult:
        """Handle an irreversible side effect according to policy."""
        policy = self.get_policy(side_effect.effect_type)
        
        result = CompensationResult(
            step_id=side_effect.step_id,
            success=False,
            side_effect_classified=side_effect,
            strategy_used=policy.strategy,
            compensation_completed=False,
            remaining_risk=[],
            manual_intervention_required=False,
        )
        
        if policy.strategy == CompensationStrategy.COMPENSATE:
            # Try to compensate as much as possible
            result.success = True
            result.compensation_completed = side_effect.compensation_possible
            if not side_effect.compensation_possible:
                result.remaining_risk.append(f"{side_effect.effect_type.value}_uncompensated")
        
        elif policy.strategy == CompensationStrategy.NOTIFY:
            # Queue notification
            await self._queue_notification(side_effect, policy)
            result.manual_intervention_required = True
            result.success = True  # Acknowledged
        
        elif policy.strategy == CompensationStrategy.ESCALATE:
            # Escalate to human
            await self._escalate(side_effect, policy)
            result.manual_intervention_required = True
            result.success = True  # Escalated
        
        elif policy.strategy == CompensationStrategy.IGNORE:
            # Accept the side effect
            result.remaining_risk.append(f"{side_effect.effect_type.value}_accepted")
            result.success = True
        
        elif policy.strategy == CompensationStrategy.INSURANCE:
            # File insurance claim
            await self._file_insurance_claim(side_effect)
            result.success = True
        
        return result
    
    async def _queue_notification(
        self,
        side_effect: SideEffect,
        policy: CompensationIrreversibilityPolicy,
    ) -> None:
        """Queue notification for manual intervention."""
        async with self._lock:
            self._notification_queue.append({
                "side_effect": side_effect,
                "channels": policy.notify_channels,
                "queued_at": datetime.now(),
                "deadline": side_effect.compensation_deadline,
            })
    
    async def _escalate(
        self,
        side_effect: SideEffect,
        policy: CompensationIrreversibilityPolicy,
    ) -> None:
        """Escalate to human reviewer."""
        async with self._lock:
            self._pending_escalations.append({
                "side_effect": side_effect,
                "policy": policy,
                "escalated_at": datetime.now(),
                "timeout_at": datetime.now().timestamp() + policy.approval_timeout_seconds,
            })
    
    async def _file_insurance_claim(
        self,
        side_effect: SideEffect,
    ) -> None:
        """File insurance claim for irreversible loss."""
        logger.warning(
            f"Insurance claim filed for irreversible side effect: "
            f"step={side_effect.step_id}, cost={side_effect.estimated_undo_cost}"
        )
    
    async def get_pending_escalations(self) -> List[Dict[str, Any]]:
        """Get pending human escalations."""
        async with self._lock:
            # Filter out timed-out escalations
            now = datetime.now().timestamp()
            self._pending_escalations = [
                e for e in self._pending_escalations
                if e["timeout_at"] > now
            ]
            return self._pending_escalations.copy()


class EnhancedSagaCompensation:
    """
    Enhanced Saga with SideEffectClassification and IrreversibilityPolicy.
    
    Key insight: True distributed atomicity is impossible for external effects.
    This implementation provides:
    - Semantic compensation (not true rollback)
    - Side effect classification
    - Policy-driven irreversibility handling
    - Risk tracking and escalation
    """
    
    def __init__(
        self,
        saga_id: str,
        max_compensation_retries: int = 3,
    ):
        self.saga_id = saga_id
        self.max_retries = max_compensation_retries
        
        self._steps: List[Dict[str, Any]] = []
        self._completed_steps: List[str] = []
        self._side_effects: List[SideEffect] = []
        
        self._classifier = SideEffectClassifier()
        self._policy_engine = IrreversibilityPolicyEngine()
        self._lock = asyncio.Lock()
    
    def add_step(
        self,
        step_id: str,
        action: Callable,
        rollback: Callable,
        side_effect_type: Optional[SideEffectType] = None,
        *args,
        **kwargs,
    ) -> "EnhancedSagaCompensation":
        """Add a saga step with optional side effect classification."""
        if side_effect_type is None:
            # Auto-classify
            side_effect_type = self._classifier.classify(step_id, kwargs)
        
        self._steps.append({
            "step_id": step_id,
            "action": action,
            "rollback": rollback,
            "side_effect_type": side_effect_type,
            "args": args,
            "kwargs": kwargs,
        })
        return self
    
    async def execute(self) -> Dict[str, Any]:
        """
        Execute saga with side effect tracking.
        
        Returns detailed result including:
        - success: bool
        - completed_steps: list
        - failed_step: str
        - side_effects: list of side effects
        - irreversibility_results: handling of irreversible effects
        - manual_interventions: items needing human review
        """
        completed = []
        failed_step = None
        
        try:
            for step_info in self._steps:
                result = step_info["action"](
                    *step_info["args"],
                    **step_info["kwargs"]
                )
                if asyncio.iscoroutine(result):
                    result = await result
                
                completed.append(step_info["step_id"])
                
                # Track side effect
                side_effect = SideEffect(
                    step_id=step_info["step_id"],
                    effect_type=step_info["side_effect_type"],
                    resource_id=str(result) if result else step_info["step_id"],
                    description=f"Action {step_info['step_id']} completed",
                    occurred_at=datetime.now(),
                    compensation_possible=step_info["rollback"] is not None,
                )
                self._side_effects.append(side_effect)
            
            return {
                "success": True,
                "saga_id": self.saga_id,
                "completed_steps": completed,
                "failed_step": None,
                "side_effects": self._side_effects,
                "irreversibility_results": [],
                "manual_interventions": [],
            }
        
        except Exception as e:
            logger.error(f"Saga {self.saga_id} failed at {completed[-1] if completed else 'init'}: {e}")
            failed_step = completed[-1] if completed else None
            
            # Compensate with irreversibility handling
            compensation_results = await self._compensate_with_policy(completed)
            
            # Collect manual interventions
            manual_interventions = await self._policy_engine.get_pending_escalations()
            
            return {
                "success": False,
                "saga_id": self.saga_id,
                "completed_steps": completed,
                "failed_step": failed_step,
                "side_effects": self._side_effects,
                "irreversibility_results": compensation_results,
                "manual_interventions": manual_interventions,
                "error": str(e),
            }
    
    async def _compensate_with_policy(
        self,
        completed_steps: List[str],
    ) -> List[CompensationResult]:
        """Compensate steps with irreversibility policy handling."""
        results = []
        
        for step_info in reversed(self._steps):
            if step_info["step_id"] not in completed_steps:
                continue
            
            # Find corresponding side effect
            side_effect = next(
                (se for se in self._side_effects if se.step_id == step_info["step_id"]),
                None
            )
            
            if not side_effect:
                continue
            
            # Try rollback
            rollback_success = False
            try:
                rollback = step_info["rollback"](
                    *step_info["args"],
                    **step_info["kwargs"]
                )
                if asyncio.iscoroutine(rollback):
                    await rollback
                rollback_success = True
            except Exception as e:
                logger.warning(f"Rollback failed for {step_info['step_id']}: {e}")
            
            # Update side effect status
            side_effect.compensation_possible = rollback_success
            
            # Handle based on policy
            if side_effect.effect_type == SideEffectType.IRREVERSIBLE:
                # Irreversible - apply policy
                result = await self._policy_engine.handle_irreversibility(side_effect)
                results.append(result)
            else:
                # Reversible - just record success
                results.append(CompensationResult(
                    step_id=step_info["step_id"],
                    success=rollback_success,
                    side_effect_classified=side_effect,
                    strategy_used=CompensationStrategy.COMPENSATE,
                    compensation_completed=rollback_success,
                    remaining_risk=[],
                    manual_intervention_required=False,
                ))
        
        return results
    
    def get_side_effect_summary(self) -> Dict[str, Any]:
        """Get summary of all side effects."""
        summary = {
            "total": len(self._side_effects),
            "by_type": {},
            "risks": [],
            "manual_intervention_count": 0,
        }
        
        for se in self._side_effects:
            # Count by type
            type_key = se.effect_type.value
            summary["by_type"][type_key] = summary["by_type"].get(type_key, 0) + 1
            
            # Track risks
            if se.effect_type == SideEffectType.IRREVERSIBLE:
                summary["risks"].append({
                    "step_id": se.step_id,
                    "risk_level": se.risk_level,
                    "estimated_undo_cost": se.estimated_undo_cost,
                })
                summary["manual_intervention_count"] += 1
        
        return summary
