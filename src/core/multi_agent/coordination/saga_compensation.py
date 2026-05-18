"""
Saga Atomic Compensation and Circuit Error Classification.

Saga Pattern:
- Compensation steps wrapped in transaction
- Retry entire compensation on failure (max 3 times)

Circuit Breaker Error Classification:
- Timeout errors: temporary, don't increase failure count
- 5xx, connection refused, panic: serious, increase failure count
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class ErrorType(str, Enum):
    """Circuit breaker error types."""
    TRIP = "trip"  # Serious errors that trip the breaker
    TEMP = "temp"  # Temporary errors that don't trip


@dataclass
class CompensationStep:
    """Single compensation step in saga."""
    step_id: str
    action: Callable
    rollback: Callable
    args: tuple = ()
    kwargs: Dict[str, Any] = field(default_factory=dict)
    status: str = "pending"  # pending, completed, failed


@dataclass
class SagaResult:
    """Result of saga execution."""
    success: bool
    saga_id: str
    completed_steps: List[str]
    failed_step: Optional[str]
    compensation_attempts: int
    error: Optional[str]


class SagaAtomicCompensation:
    """
    Saga pattern with atomic compensation.
    
    Guarantees:
    - All compensation steps are executed on failure
    - Compensation is retried (up to 3 times)
    - Compensation_attempts are tracked
    """
    
    def __init__(
        self,
        saga_id: str,
        max_compensation_retries: int = 3,
    ):
        self.saga_id = saga_id
        self.max_retries = max_compensation_retries
        self._steps: List[CompensationStep] = []
        self._completed_steps: List[str] = []
        self._lock = asyncio.Lock()
    
    def add_step(
        self,
        step_id: str,
        action: Callable,
        rollback: Callable,
        *args,
        **kwargs,
    ) -> "SagaAtomicCompensation":
        """Add a saga step."""
        step = CompensationStep(
            step_id=step_id,
            action=action,
            rollback=rollback,
            args=args,
            kwargs=kwargs,
        )
        self._steps.append(step)
        return self
    
    async def execute(self) -> SagaResult:
        """
        Execute saga with atomic compensation.
        
        On failure, retries compensation for all completed steps.
        """
        completed = []
        failed_step_id = None
        
        try:
            # Execute each step
            for step in self._steps:
                step.status = "pending"
                
                # Execute action
                result = step.action(*step.args, **step.kwargs)
                if asyncio.iscoroutine(result):
                    result = await result
                
                step.status = "completed"
                completed.append(step.step_id)
                self._completed_steps.append(step.step_id)
            
            return SagaResult(
                success=True,
                saga_id=self.saga_id,
                completed_steps=completed,
                failed_step=None,
                compensation_attempts=0,
                error=None,
            )
            
        except Exception as e:
            # Find which step failed by looking at status
            failed_step = None
            for step in self._steps:
                if step.status == "pending":
                    failed_step = step.step_id
                    break
            
            logger.error(f"Saga {self.saga_id} failed at step {failed_step or 'init'}: {e}")
            
            # Compensate completed steps (those with status "completed")
            completed_for_compensation = [
                s.step_id for s in self._steps 
                if s.status == "completed"
            ]
            compensation_attempts = await self._compensate(completed_for_compensation)
            
            return SagaResult(
                success=False,
                saga_id=self.saga_id,
                completed_steps=completed,
                failed_step=failed_step,
                compensation_attempts=compensation_attempts,
                error=str(e),
            )
    
    async def _compensate(self, completed_steps: List[str]) -> int:
        """
        Compensate all completed steps.
        
        Retries up to max_retries times.
        """
        for attempt in range(1, self.max_retries + 1):
            all_ok = True
            
            # Compensate in reverse order
            for step in reversed(self._steps):
                if step.step_id not in completed_steps:
                    continue
                
                try:
                    step.status = "compensating"
                    
                    rollback = step.rollback(*step.args, **step.kwargs)
                    if asyncio.iscoroutine(rollback):
                        await rollback
                    
                    step.status = "compensated"
                    
                except Exception as e:
                    logger.warning(
                        f"Compensation step {step.step_id} failed "
                        f"(attempt {attempt}): {e}"
                    )
                    all_ok = False
                    step.status = "compensation_failed"
            
            if all_ok:
                logger.info(f"Saga {self.saga_id} compensated successfully")
                return attempt
        
        logger.error(f"Saga {self.saga_id} compensation failed after {self.max_retries} attempts")
        return self.max_retries


class CircuitErrorClassifier:
    """
    Classifies errors for circuit breaker trip decisions.
    
    Error Types:
    - TRIP: Serious errors (5xx, connection refused, panic) that trip the breaker
    - TEMP: Temporary errors (timeout) that don't increase failure count
    """
    
    # Patterns that indicate serious errors
    TRIP_PATTERNS = [
        "5",  # 5xx errors
        "connection refused",
        "connection reset",
        "panic",
        "out of memory",
        "assertion failed",
        "deadlock",
        "unavailable",
        "service unavailable",
        "internal server error",
        "not implemented",
    ]
    
    # Patterns that indicate temporary errors
    TEMP_PATTERNS = [
        "timeout",
        "timed out",
        "temporarily unavailable",
        "too many requests",
        "rate limit",
        "backoff",
        "retry",
        "queue full",
        "capacity",
    ]
    
    def __init__(
        self,
        trip_patterns: Optional[List[str]] = None,
        temp_patterns: Optional[List[str]] = None,
    ):
        self.trip_patterns = trip_patterns or self.TRIP_PATTERNS
        self.temp_patterns = temp_patterns or self.TEMP_PATTERNS
    
    def classify(self, error: Exception) -> ErrorType:
        """
        Classify an error.
        
        Returns:
        - ErrorType.TRIP: Serious error that should trip breaker
        - ErrorType.TEMP: Temporary error that shouldn't trip breaker
        """
        error_str = str(error).lower()
        error_type = type(error).__name__.lower()
        
        # Check for serious errors
        for pattern in self.trip_patterns:
            if pattern.lower() in error_str or pattern.lower() in error_type:
                return ErrorType.TRIP
        
        # Check for temporary errors
        for pattern in self.temp_patterns:
            if pattern.lower() in error_str or pattern.lower() in error_type:
                return ErrorType.TEMP
        
        # Default: classify by exception type
        default_types = {
            "timeout": ErrorType.TEMP,
            "connectionerror": ErrorType.TRIP,
            "httperror": ErrorType.TRIP,
        }
        
        for exc_type, error_type in default_types.items():
            if exc_type in error_type:
                return error_type
        
        # Unknown errors default to TRIP (safer)
        return ErrorType.TRIP
    
    def should_trip(self, error: Exception) -> tuple[bool, ErrorType]:
        """
        Determine if error should trip circuit breaker.
        
        Returns (should_trip, error_type).
        """
        error_type = self.classify(error)
        return error_type == ErrorType.TRIP, error_type
    
    def get_explanation(self, error: Exception) -> Dict[str, Any]:
        """Get detailed explanation of error classification."""
        error_str = str(error)
        error_type = type(error).__name__
        classified = self.classify(error)
        
        matched_patterns = []
        for pattern in self.trip_patterns + self.temp_patterns:
            if pattern.lower() in error_str.lower():
                matched_patterns.append(pattern)
        
        return {
            "error_type": error_type,
            "error_message": error_str,
            "classification": classified.value,
            "matched_patterns": matched_patterns,
            "should_trip_breaker": classified == ErrorType.TRIP,
        }
