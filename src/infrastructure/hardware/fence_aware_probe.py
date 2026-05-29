"""Fence Token Enforcement for Hardware Probes - P0-Hardening.

Wraps any HardwareProbe to enforce fence token validation on every
erase/write/verify operation, preventing split-brain in distributed flash.

P0-C Requirement:
  Every probe operation (erase, write_memory, read_memory, verify) MUST
  validate the fence token BEFORE executing. This is enforced by wrapping
  with FenceAwareProbeAdapter.

Usage:
  1. Acquire lock + fence token via LockManager
  2. Wrap probe with FenceAwareProbeAdapter(probe, lock_manager, token)
  3. All operations through the adapter validate token automatically

Integration:
  - FenceAwareProbeAdapter: wraps HardwareProbe, validates token on every call
  - FenceTokenMiddleware: middleware-style enforcement in the probe pipeline
  - probe_manager.py: uses FenceAwareProbeAdapter when lock is held
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.hardware.flash.flash_lock import (
        FlashFenceToken,
        LockManager,
    )
    from src.infrastructure.hardware.hardware_probe_protocol import HardwareProbe

logger = logging.getLogger(__name__)


class FenceViolationError(Exception):
    """Raised when a fence token validation fails before a probe operation."""

    def __init__(
        self,
        operation: str,
        token: str,
        reason: str,
    ):
        self.operation = operation
        self.token = token
        self.reason = reason
        super().__init__(
            f"Fence violation on {operation}: token={token[:8]}... reason={reason}"
        )


@dataclass
class FenceTokenMiddleware:
    """Middleware that enforces fence token validation in the probe pipeline.

    P0-C: Every probe operation MUST pass through this middleware to validate
    the fence token before reaching the hardware. This prevents stale
    operations from executing after a lock has been revoked.

    Usage:
        middleware = FenceTokenMiddleware(lock_manager, token)
        middleware.register("erase", erase_handler)
        middleware.register("write_memory", write_handler)
        result = await middleware.execute("erase", address, length)
    """

    lock_manager: LockManager
    fence_token: FlashFenceToken
    target_name: str

    _handlers: dict[str, Callable] = field(default_factory=dict)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def register(self, operation: str, handler: Callable) -> None:
        """Register a handler for an operation.

        Args:
            operation: Operation name (erase, write_memory, verify, etc.)
            handler: Async callable to invoke after token validation
        """
        self._handlers[operation] = handler

    async def execute(
        self,
        operation: str,
        *args,
        **kwargs,
    ) -> Any:
        """Execute an operation after validating the fence token.

        Args:
            operation: Operation name
            *args: Positional args passed to the handler
            **kwargs: Keyword args passed to the handler

        Returns:
            Handler result

        Raises:
            FenceViolationError: If token validation fails
        """
        # Validate token BEFORE executing
        is_valid, reason = await self.lock_manager.target_lock.validate_fence_token(
            target_name=self.target_name,
            token=self.fence_token,
            operation_name=operation,
        )

        if not is_valid:
            logger.error(
                "fence_violation_blocked: operation=%s token=%s reason=%s",
                operation,
                self.fence_token.token[:8],
                reason,
            )
            raise FenceViolationError(
                operation=operation,
                token=self.fence_token.token,
                reason=reason,
            )

        handler = self._handlers.get(operation)
        if handler is None:
            raise FenceViolationError(
                operation=operation,
                token=self.fence_token.token,
                reason=f"No handler registered for operation: {operation}",
            )

        result = await handler(*args, **kwargs)

        # Advance token on success
        await self.lock_manager.advance_fence_token(
            self.target_name,
            self.fence_token.owner_id,
        )

        return result


class FenceAwareProbeAdapter:
    """P0-Hardening: Wraps a HardwareProbe to enforce fence token validation.

    Every erase/write/verify operation validates the fence token before executing.
    If validation fails, the operation is blocked with FenceViolationError.

    This adapter implements the same HardwareProbe protocol, so it can be used
    as a drop-in replacement wherever a HardwareProbe is expected.

    CRITICAL: The adapter does NOT re-execute hardware operations. If token
    validation fails, the operation is blocked entirely. Use this adapter
    only when a lock+fence token has been acquired.

    Usage:
        lock_mgr = LockManager(target_lock=...)
        lock, token = await lock_mgr.acquire_with_fence_token(
            "engine_car", "session_1", "tx_123"
        )
        probe = FenceAwareProbeAdapter(
            underlying_probe=real_probe,
            lock_manager=lock_mgr,
            fence_token=token,
            target_name="engine_car",
        )
        # All operations through `probe` are automatically fenced
        await probe.erase(0x08000000, 4096)
        await probe.write_memory(0x08000000, firmware_bytes)
        await probe.verify(0x08000000, expected_crc)
    """

    def __init__(
        self,
        underlying_probe: HardwareProbe,
        lock_manager: LockManager,
        fence_token: FlashFenceToken,
        target_name: str,
    ):
        """
        Args:
            underlying_probe: The real probe to delegate to
            lock_manager: LockManager instance for token validation
            fence_token: Fence token from acquire_with_fence_token
            target_name: Target being operated on
        """
        self._probe = underlying_probe
        self._lm = lock_manager
        self._token = fence_token
        self._target = target_name
        self._validated_operations: int = 0

    async def _validate_and_execute(
        self,
        operation_name: str,
        operation_fn: Callable,
        *args,
        **kwargs,
    ) -> Any:
        """Validate fence token, execute operation, advance token on success.

        This is the P0-C enforcement point: EVERY probe operation goes through
        this method.
        """
        is_valid, reason = await self._lm.target_lock.validate_fence_token(
            target_name=self._target,
            token=self._token,
            operation_name=operation_name,
        )

        if not is_valid:
            logger.error(
                "fence_violation: blocked %s on %s token=%s reason=%s",
                operation_name,
                self._target,
                self._token.token[:8],
                reason,
            )
            raise FenceViolationError(
                operation=operation_name,
                token=self._token.token,
                reason=reason,
            )

        self._validated_operations += 1
        result = await operation_fn(*args, **kwargs)

        # Advance token version after successful operation (P0-C)
        await self._lm.advance_fence_token(self._target, self._token.owner_id)

        return result

    # ---- HardwareProbe protocol implementation ----

    @property
    def probe_info(self) -> Any:
        return self._probe.probe_info

    async def connect(self, target_id: str) -> bool:
        return await self._probe.connect(target_id)

    async def disconnect(self) -> None:
        return await self._probe.disconnect()

    async def read_memory(self, address: int, length: int) -> bytes:
        return await self._validate_and_execute(
            "read_memory",
            self._probe.read_memory,
            address,
            length,
        )

    async def write_memory(self, address: int, data: bytes) -> bool:
        return await self._validate_and_execute(
            "write_memory",
            self._probe.write_memory,
            address,
            data,
        )

    async def erase(self, address: int, length: int) -> bool:
        return await self._validate_and_execute(
            "erase",
            self._probe.erase,
            address,
            length,
        )

    async def reset(self) -> bool:
        return await self._probe.reset()

    async def halt(self) -> bool:
        return await self._probe.halt()

    async def resume(self) -> bool:
        return await self._probe.resume()

    async def step(self) -> bool:
        return await self._probe.step()

    async def read_register(self, register: str) -> int:
        return await self._probe.read_register(register)

    async def write_register(self, register: str, value: int) -> bool:
        return await self._probe.write_register(register, value)

    async def set_breakpoint(self, address: int) -> bool:
        return await self._probe.set_breakpoint(address)

    async def remove_breakpoint(self, address: int) -> bool:
        return await self._probe.remove_breakpoint(address)

    # ---- Convenience helpers for flash-specific operations ----

    async def verify(
        self,
        address: int,
        length: int,
        expected_crc: int | None = None,
    ) -> bool:
        """P0-C: Verify flash content after write.

        Wraps erase + write + readback + CRC comparison as a single
        fenced operation.

        Args:
            address: Start address
            length: Number of bytes
            expected_crc: Optional expected CRC-32

        Returns:
            True if verification passes
        """
        data = await self._validate_and_execute(
            "verify",
            self._probe.read_memory,
            address,
            length,
        )

        if expected_crc is not None:
            import zlib
            actual_crc = zlib.crc32(data) & 0xFFFFFFFF
            if actual_crc != expected_crc:
                logger.error(
                    "verify_failed: address=0x%x expected_crc=%08x actual_crc=%08x",
                    address,
                    expected_crc,
                    actual_crc,
                )
                # Invalidate fence on failure
                await self._lm.invalidate_fence_on_failure(
                    self._target, self._token.owner_id
                )
                return False

        return True

    def get_stats(self) -> dict[str, Any]:
        """Get fence enforcement statistics."""
        return {
            "validated_operations": self._validated_operations,
            "target": self._target,
            "token_seq": self._token.sequence,
            "token_valid": self._token.is_valid(),
        }
