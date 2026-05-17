"""Execution engine for handler dispatch."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Coroutine, Optional

from src.infrastructure.router.types import (
    ExecutionResult,
    RequestContext,
    RouteResult,
)

if TYPE_CHECKING:
    from src.infrastructure.router.observation.health_monitor import HealthMonitor

logger = logging.getLogger(__name__)


@dataclass
class HandlerConfig:
    """Configuration for handler."""

    timeout_seconds: float = 30.0
    retry_on_failure: bool = True
    max_retries: int = 3


HandlerFunc = Callable[["RequestContext"], Coroutine[Any, Any, Any]]


class ExecutionEngine:
    """
    Executes routing decisions.
    
    Handles:
    - Handler dispatch
    - Timeout management
    - Health tracking
    - Error handling
    """

    def __init__(
        self,
        health_monitor: Optional[HealthMonitor] = None,
    ):
        self._handlers: dict[str, tuple[HandlerFunc, HandlerConfig]] = {}
        self._health_monitor = health_monitor
        self._default_config = HandlerConfig()

    def register_handler(
        self,
        intent: str,
        handler: HandlerFunc,
        config: Optional[HandlerConfig] = None,
    ) -> None:
        """
        Register handler for intent.
        
        Args:
            intent: Intent path
            handler: Async handler function
            config: Optional handler configuration
        """
        self._handlers[intent] = (handler, config or self._default_config)
        logger.debug(f"Registered handler for intent: {intent}")

    def unregister_handler(self, intent: str) -> None:
        """Unregister handler for intent."""
        self._handlers.pop(intent, None)

    async def execute(
        self,
        context: RequestContext,
        route_result: RouteResult,
    ) -> ExecutionResult:
        """
        Execute routing decision.
        
        Args:
            context: Request context
            route_result: Routing decision
            
        Returns:
            ExecutionResult with execution status
        """
        handler_data = self._handlers.get(route_result.intent)

        if not handler_data:
            return ExecutionResult(
                success=False,
                intent=route_result.intent,
                error=f"No handler registered for intent: {route_result.intent}",
            )

        handler, config = handler_data
        start_time = time.time()

        try:
            result = await asyncio.wait_for(
                handler(context),
                timeout=config.timeout_seconds,
            )

            latency_ms = (time.time() - start_time) * 1000

            if self._health_monitor:
                await self._health_monitor.record(
                    intent=route_result.intent,
                    success=True,
                    latency_ms=latency_ms,
                )

            return ExecutionResult(
                success=True,
                intent=route_result.intent,
                result=result,
                latency_ms=latency_ms,
            )

        except asyncio.TimeoutError:
            latency_ms = (time.time() - start_time) * 1000
            logger.error(f"Handler timeout for intent {route_result.intent}")

            if self._health_monitor:
                await self._health_monitor.record(
                    intent=route_result.intent,
                    success=False,
                    latency_ms=latency_ms,
                )

            return ExecutionResult(
                success=False,
                intent=route_result.intent,
                error=f"Handler timeout after {config.timeout_seconds}s",
                latency_ms=latency_ms,
            )

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            logger.exception(f"Handler error for intent {route_result.intent}")

            if self._health_monitor:
                await self._health_monitor.record(
                    intent=route_result.intent,
                    success=False,
                    latency_ms=latency_ms,
                )

            return ExecutionResult(
                success=False,
                intent=route_result.intent,
                error=str(e),
                latency_ms=latency_ms,
            )

    def get_registered_intents(self) -> list[str]:
        """Get list of registered intents."""
        return list(self._handlers.keys())

    def has_handler(self, intent: str) -> bool:
        """Check if handler exists for intent."""
        return intent in self._handlers


class LambdaHandler:
    """Wrapper for lambda/function handlers."""

    def __init__(self, func: Callable[..., Coroutine[Any, Any, Any]]):
        self._func = func

    async def __call__(self, context: RequestContext) -> Any:
        return await self._func(context)


def create_handler(func: Callable[..., Coroutine[Any, Any, Any]]) -> LambdaHandler:
    """Create handler from async function."""
    return LambdaHandler(func)
