"""Resume idempotency with token-based atomic updates - Phase 5B."""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime
from typing import Optional

from .types import InterruptStatus, PlanInterrupt, ResumeResult


class PlanInterruptStore:
    """Store interface for plan interrupts."""
    
    async def save(self, interrupt: PlanInterrupt) -> None:
        """Save an interrupt."""
        raise NotImplementedError
    
    async def get(self, interrupt_id: str) -> Optional[PlanInterrupt]:
        """Get an interrupt by ID."""
        raise NotImplementedError
    
    async def update_status(
        self,
        interrupt_id: str,
        status: InterruptStatus,
        **kwargs,
    ) -> bool:
        """Update interrupt status atomically."""
        raise NotImplementedError
    
    async def atomic_resume(
        self,
        interrupt_id: str,
        token: str,
        user_input: dict,
    ) -> tuple[bool, bool]:
        """Atomic resume with token validation.
        
        Returns:
            Tuple of (success, already_resumed)
        """
        raise NotImplementedError
    
    async def get_expired(self) -> list[PlanInterrupt]:
        """Get all expired interrupts."""
        raise NotImplementedError


class InMemoryPlanInterruptStore(PlanInterruptStore):
    """In-memory implementation of interrupt store."""
    
    def __init__(self):
        self._interrupts: dict[str, PlanInterrupt] = {}
        self._token_map: dict[str, str] = {}
    
    async def save(self, interrupt: PlanInterrupt) -> None:
        """Save an interrupt."""
        self._interrupts[interrupt.interrupt_id] = interrupt
        self._token_map[interrupt.interrupt_id] = interrupt.resume_token
    
    async def get(self, interrupt_id: str) -> Optional[PlanInterrupt]:
        """Get an interrupt by ID."""
        return self._interrupts.get(interrupt_id)
    
    async def update_status(
        self,
        interrupt_id: str,
        status: InterruptStatus,
        **kwargs,
    ) -> bool:
        """Update interrupt status."""
        interrupt = self._interrupts.get(interrupt_id)
        if not interrupt:
            return False
        
        interrupt.status = status
        for key, value in kwargs.items():
            if hasattr(interrupt, key):
                setattr(interrupt, key, value)
        
        return True
    
    async def atomic_resume(
        self,
        interrupt_id: str,
        token: str,
        user_input: dict,
    ) -> tuple[bool, bool]:
        """Atomic resume with token validation."""
        interrupt = self._interrupts.get(interrupt_id)
        
        if not interrupt:
            return False, False
        
        if interrupt.status != InterruptStatus.PENDING:
            return False, True
        
        if interrupt.resume_token != token:
            return False, False
        
        interrupt.status = InterruptStatus.RESUMED
        interrupt.resumed_at = int(datetime.utcnow().timestamp())
        interrupt.user_input = user_input
        
        return True, False
    
    async def get_expired(self) -> list[PlanInterrupt]:
        """Get all expired interrupts."""
        now = int(datetime.utcnow().timestamp())
        return [
            i for i in self._interrupts.values()
            if i.status == InterruptStatus.PENDING
            and i.expires_at is not None
            and i.expires_at <= now
        ]


class ResumeIdempotency:
    """Token-based idempotent resume for plan interrupts.
    
    Ensures exactly-once resume semantics through token validation
    and atomic updates.
    """
    
    def __init__(
        self,
        store: PlanInterruptStore,
        default_timeout_seconds: int = 300,
    ):
        self._store = store
        self._default_timeout = default_timeout_seconds
    
    async def create_interrupt(
        self,
        plan_id: str,
        task_id: str,
        timeout_seconds: Optional[int] = None,
    ) -> PlanInterrupt:
        """Create a new interrupt.
        
        Args:
            plan_id: Plan identifier
            task_id: Task identifier that was interrupted
            timeout_seconds: Resume timeout (default from config)
            
        Returns:
            The created PlanInterrupt with unique resume_token
        """
        timeout = timeout_seconds or self._default_timeout
        
        interrupt = PlanInterrupt(
            interrupt_id=str(uuid.uuid4()),
            plan_id=plan_id,
            task_id=task_id,
            status=InterruptStatus.PENDING,
            resume_token=secrets.token_urlsafe(32),
            expires_at=int(datetime.utcnow().timestamp()) + timeout,
        )
        
        await self._store.save(interrupt)
        
        return interrupt
    
    async def get_interrupt(
        self,
        interrupt_id: str,
    ) -> Optional[PlanInterrupt]:
        """Get an interrupt by ID."""
        return await self._store.get(interrupt_id)
    
    async def resume(
        self,
        interrupt_id: str,
        user_input: dict,
        token: str,
    ) -> ResumeResult:
        """Resume a plan with user input.
        
        This operation is idempotent - multiple calls with the same
        token will only succeed once.
        
        Args:
            interrupt_id: The interrupt to resume
            user_input: User input to continue the plan
            token: The resume token
            
        Returns:
            ResumeResult indicating success or failure reason
        """
        interrupt = await self._store.get(interrupt_id)
        
        if not interrupt:
            return ResumeResult(
                success=False,
                error=f"Interrupt not found: {interrupt_id}",
            )
        
        if interrupt.status == InterruptStatus.RESUMED:
            return ResumeResult(
                success=False,
                already_resumed=True,
                error="Interrupt already resumed",
            )
        
        if interrupt.status == InterruptStatus.CANCELLED:
            return ResumeResult(
                success=False,
                error="Interrupt was cancelled",
            )
        
        if interrupt.status == InterruptStatus.EXPIRED:
            return ResumeResult(
                success=False,
                error="Interrupt has expired",
            )
        
        if interrupt.resume_token != token:
            return ResumeResult(
                success=False,
                invalid_token=True,
                error="Invalid resume token",
            )
        
        success, already_resumed = await self._store.atomic_resume(
            interrupt_id, token, user_input
        )
        
        if not success:
            return ResumeResult(
                success=False,
                error="Failed to resume interrupt",
            )
        
        return ResumeResult(success=True)
    
    async def cancel(
        self,
        interrupt_id: str,
        token: str,
    ) -> ResumeResult:
        """Cancel an interrupt.
        
        Args:
            interrupt_id: The interrupt to cancel
            token: The resume token (must match)
            
        Returns:
            ResumeResult indicating success or failure
        """
        interrupt = await self._store.get(interrupt_id)
        
        if not interrupt:
            return ResumeResult(
                success=False,
                error=f"Interrupt not found: {interrupt_id}",
            )
        
        if interrupt.resume_token != token:
            return ResumeResult(
                success=False,
                invalid_token=True,
                error="Invalid resume token",
            )
        
        if interrupt.status != InterruptStatus.PENDING:
            return ResumeResult(
                success=False,
                error=f"Cannot cancel interrupt with status: {interrupt.status}",
            )
        
        await self._store.update_status(
            interrupt_id,
            InterruptStatus.CANCELLED,
        )
        
        return ResumeResult(success=True)
    
    async def expire(self, interrupt_id: str) -> bool:
        """Mark an interrupt as expired.
        
        Args:
            interrupt_id: The interrupt to expire
            
        Returns:
            True if successfully expired
        """
        return await self._store.update_status(
            interrupt_id,
            InterruptStatus.EXPIRED,
            expired_at=int(datetime.utcnow().timestamp()),
        )
    
    async def get_expired_interrupts(self) -> list[PlanInterrupt]:
        """Get all expired pending interrupts.
        
        Useful for background cleanup.
        """
        return await self._store.get_expired()
    
    async def validate_token(
        self,
        interrupt_id: str,
        token: str,
    ) -> bool:
        """Validate a resume token without resuming.
        
        Args:
            interrupt_id: The interrupt ID
            token: The token to validate
            
        Returns:
            True if token is valid and matches
        """
        interrupt = await self._store.get(interrupt_id)
        if not interrupt:
            return False
        return interrupt.resume_token == token


class ResumeTokenGenerator:
    """Generates secure resume tokens."""
    
    @staticmethod
    def generate(length: int = 32) -> str:
        """Generate a secure random token.
        
        Args:
            length: Token length in bytes (default 32)
            
        Returns:
            URL-safe base64 encoded token
        """
        return secrets.token_urlsafe(length)
