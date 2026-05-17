"""Interrupt handler with expiration and escalation - Phase 5B."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Optional

from .types import ExpirationPolicy, ExpirationResult, InterruptStatus, PlanInterrupt


class InterruptHandler:
    """Handles interrupt expiration with configurable policies.
    
    Supports three expiration policies:
    - AUTO_CANCEL: Automatically cancel the workflow
    - ESCALATE: Notify supervisor via event bus
    - FALLBACK_BRANCH: Execute fallback branch if defined
    """
    
    def __init__(
        self,
        expiration_policy: ExpirationPolicy = ExpirationPolicy.AUTO_CANCEL,
        escalation_channel: Optional[str] = None,
        on_cancel: Optional[Callable[[str], None]] = None,
        on_escalate: Optional[Callable[[str, PlanInterrupt], None]] = None,
        on_fallback: Optional[Callable[[str], None]] = None,
    ):
        self._policy = expiration_policy
        self._escalation_channel = escalation_channel
        self._on_cancel = on_cancel
        self._on_escalate = on_escalate
        self._on_fallback = on_fallback
    
    @property
    def policy(self) -> ExpirationPolicy:
        """Get current expiration policy."""
        return self._policy
    
    async def check_expiration(
        self,
        interrupt: PlanInterrupt,
    ) -> ExpirationResult:
        """Check if an interrupt has expired.
        
        Args:
            interrupt: The interrupt to check
            
        Returns:
            ExpirationResult with expiration status
        """
        if interrupt.status != InterruptStatus.PENDING:
            return ExpirationResult(
                is_expired=False,
                should_escalate=False,
                fallback_available=False,
            )
        
        if interrupt.expires_at is None:
            return ExpirationResult(
                is_expired=False,
                should_escalate=False,
                fallback_available=False,
            )
        
        now = int(datetime.utcnow().timestamp())
        is_expired = now >= interrupt.expires_at
        
        return ExpirationResult(
            is_expired=is_expired,
            expired_at=interrupt.expires_at if is_expired else None,
            should_escalate=is_expired and self._policy == ExpirationPolicy.ESCALATE,
            fallback_available=is_expired and self._policy == ExpirationPolicy.FALLBACK_BRANCH,
        )
    
    async def execute_policy(
        self,
        interrupt: PlanInterrupt,
        policy: Optional[ExpirationPolicy] = None,
    ) -> str:
        """Execute the expiration policy.
        
        Args:
            interrupt: The expired interrupt
            policy: Override policy (uses default if None)
            
        Returns:
            Action taken: 'cancelled', 'escalated', 'fallback', or 'none'
        """
        policy = policy or self._policy
        
        result = await self.check_expiration(interrupt)
        
        if not result.is_expired:
            return "none"
        
        if policy == ExpirationPolicy.AUTO_CANCEL:
            if self._on_cancel:
                self._on_cancel(interrupt.plan_id)
            return "cancelled"
        
        if policy == ExpirationPolicy.ESCALATE:
            if self._on_escalate:
                self._on_escalate(interrupt.plan_id, interrupt)
            return "escalated"
        
        if policy == ExpirationPolicy.FALLBACK_BRANCH:
            if self._on_fallback:
                self._on_fallback(interrupt.plan_id)
            return "fallback"
        
        return "none"
    
    async def process_expired_interrupts(
        self,
        expired_interrupts: list[PlanInterrupt],
    ) -> dict[str, str]:
        """Process a list of expired interrupts.
        
        Args:
            expired_interrupts: List of expired interrupts
            
        Returns:
            Dictionary mapping interrupt_id to action taken
        """
        results = {}
        
        for interrupt in expired_interrupts:
            action = await self.execute_policy(interrupt)
            results[interrupt.interrupt_id] = action
        
        return results


class InterruptExpirationMonitor:
    """Background monitor for interrupt expiration.
    
    Periodically checks for expired interrupts and
    executes the configured policy.
    """
    
    def __init__(
        self,
        handler: InterruptHandler,
        store,  # PlanInterruptStore
        check_interval_seconds: float = 60.0,
    ):
        self._handler = handler
        self._store = store
        self._interval = check_interval_seconds
        self._running = False
    
    async def start(self) -> None:
        """Start the expiration monitor."""
        self._running = True
    
    async def stop(self) -> None:
        """Stop the expiration monitor."""
        self._running = False
    
    async def check_once(self) -> dict[str, str]:
        """Check for expired interrupts once.
        
        Returns:
            Dictionary of interrupt_id to action taken
        """
        expired = await self._store.get_expired()
        return await self._handler.process_expired_interrupts(expired)
    
    @property
    def is_running(self) -> bool:
        """Check if monitor is running."""
        return self._running


class EscalationManager:
    """Manages escalation of expired interrupts.
    
    Sends notifications to supervisors via configured channel.
    """
    
    def __init__(
        self,
        channel: str,
        event_emitter: Optional[Callable[[str, dict], None]] = None,
    ):
        self._channel = channel
        self._event_emitter = event_emitter
        self._escalation_history: list[dict] = []
    
    async def escalate(
        self,
        plan_id: str,
        interrupt: PlanInterrupt,
        reason: str = "expired",
    ) -> str:
        """Escalate an interrupt to supervisor.
        
        Args:
            plan_id: Plan identifier
            interrupt: The expired interrupt
            reason: Escalation reason
            
        Returns:
            Escalation ticket ID
        """
        escalation_id = f"esc_{plan_id}_{interrupt.interrupt_id}"
        
        escalation_event = {
            "escalation_id": escalation_id,
            "plan_id": plan_id,
            "interrupt_id": interrupt.interrupt_id,
            "task_id": interrupt.task_id,
            "reason": reason,
            "created_at": int(datetime.utcnow().timestamp()),
            "status": "pending",
        }
        
        self._escalation_history.append(escalation_event)
        
        if self._event_emitter:
            self._event_emitter(
                self._channel,
                escalation_event,
            )
        
        return escalation_id
    
    def get_pending_escalations(self) -> list[dict]:
        """Get all pending escalations."""
        return [
            e for e in self._escalation_history
            if e.get("status") == "pending"
        ]
    
    def resolve_escalation(
        self,
        escalation_id: str,
        resolution: str,
    ) -> bool:
        """Resolve an escalation.
        
        Args:
            escalation_id: Escalation identifier
            resolution: Resolution action
            
        Returns:
            True if escalation was found and resolved
        """
        for event in self._escalation_history:
            if event.get("escalation_id") == escalation_id:
                event["status"] = "resolved"
                event["resolution"] = resolution
                event["resolved_at"] = int(datetime.utcnow().timestamp())
                return True
        return False


class FallbackBranchHandler:
    """Handles fallback branch execution for expired interrupts.
    
    Manages fallback branch definitions and execution.
    """
    
    def __init__(self):
        self._fallback_map: dict[str, str] = {}
        self._fallback_handlers: dict[str, Callable] = {}
    
    def register_fallback(
        self,
        task_id: str,
        fallback_branch: str,
        handler: Optional[Callable] = None,
    ) -> None:
        """Register a fallback branch for a task.
        
        Args:
            task_id: Task identifier
            fallback_branch: Branch name to execute on fallback
            handler: Optional custom handler
        """
        self._fallback_map[task_id] = fallback_branch
        if handler:
            self._fallback_handlers[task_id] = handler
    
    def get_fallback_branch(self, task_id: str) -> Optional[str]:
        """Get the fallback branch for a task.
        
        Args:
            task_id: Task identifier
            
        Returns:
            Fallback branch name or None
        """
        return self._fallback_map.get(task_id)
    
    def has_fallback(self, task_id: str) -> bool:
        """Check if a task has a fallback defined.
        
        Args:
            task_id: Task identifier
            
        Returns:
            True if fallback is defined
        """
        return task_id in self._fallback_map
    
    async def execute_fallback(
        self,
        plan_id: str,
        task_id: str,
        context: dict,
    ) -> tuple[bool, Any]:
        """Execute fallback branch for a task.
        
        Args:
            plan_id: Plan identifier
            task_id: Task identifier
            context: Execution context
            
        Returns:
            Tuple of (success, result)
        """
        if task_id not in self._fallback_handlers:
            return True, {"fallback_branch": self._fallback_map.get(task_id)}
        
        handler = self._fallback_handlers[task_id]
        try:
            result = await handler(context)
            return True, result
        except Exception as e:
            return False, {"error": str(e)}
