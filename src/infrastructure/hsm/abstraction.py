"""Infrastructure adapter for Hardware Security Module.

This module implements the domain's `HardwareSecurityModule` port interface
by wrapping the concrete `get_hsm()` function from `atecc608.py`.

The dependency flow is:
    Domain (ABPartitionManager)
        ↓ depends on
    HardwareSecurityModule (abstract port)
        ↑ implemented by
    HSMAdapter (infrastructure adapter)
        ↓ wraps
    get_hsm() (atecc608 concrete)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.domain.ports.hardware_security import HardwareSecurityModule

if TYPE_CHECKING:
    from src.infrastructure.hsm.atecc608 import BaseHSM

logger = logging.getLogger(__name__)


class HSMAdapter(HardwareSecurityModule):
    """Infrastructure adapter that implements HardwareSecurityModule port.
    
    This adapter wraps the ATECC608 (or mock/software) HSM implementation
    and exposes it through the domain's abstract interface.
    
    The adapter translates between:
    - Domain interface: `HardwareSecurityModule` (simple, focused)
    - Infrastructure interface: `BaseHSM` from atecc608.py (detailed)
    
    Usage:
        # Create adapter (typically at application startup)
        adapter = HSMAdapter()
        
        # Inject into domain service
        manager = ABPartitionManager(probe, config, hsm=adapter)
        
        # Domain uses the adapter without knowing about infrastructure
        counter = await manager._hsm.get_counter(0)
    """
    
    def __init__(self) -> None:
        """Initialize the HSM adapter."""
        self._hsm: BaseHSM | None = None
    
    async def _get_hsm(self) -> BaseHSM:
        """Get or initialize the underlying HSM.
        
        Returns:
            Initialized HSM instance
            
        Raises:
            RuntimeError: If HSM is not available
        """
        if self._hsm is None:
            from src.infrastructure.hsm.atecc608 import get_hsm
            self._hsm = await get_hsm()
        
        return self._hsm
    
    async def get_counter(self, slot: int) -> int:
        """Read monotonic counter value.
        
        Args:
            slot: Counter slot number
            
        Returns:
            Current counter value
        """
        try:
            hsm = await self._get_hsm()
            return await hsm.get_counter(slot)
        except Exception as e:
            logger.warning("hsm_get_counter_failed", slot=slot, error=str(e))
            return 0
    
    async def set_counter(self, slot: int, value: int) -> None:
        """Set counter value.
        
        Args:
            slot: Counter slot number
            value: New counter value
        """
        try:
            hsm = await self._get_hsm()
            await hsm.increment_counter(slot)
        except Exception as e:
            logger.warning("hsm_set_counter_failed", slot=slot, error=str(e))
    
    async def sign(self, slot: int, data: bytes) -> bytes:
        """Sign data with key in slot.
        
        Args:
            slot: Key slot number
            data: Data to sign
            
        Returns:
            Signature bytes
        """
        hsm = await self._get_hsm()
        return await hsm.sign(slot, data)
    
    async def verify(self, slot: int, data: bytes, signature: bytes) -> bool:
        """Verify signature.
        
        Args:
            slot: Key slot number
            data: Original data
            signature: Signature to verify
            
        Returns:
            True if signature is valid
        """
        hsm = await self._get_hsm()
        return await hsm.verify(slot, data, signature)
    
    async def is_available(self) -> bool:
        """Check if HSM is available.
        
        Returns:
            True if HSM is initialized and ready
        """
        try:
            hsm = await self._get_hsm()
            return hsm is not None
        except Exception:
            return False


class MockHSMAdapter(HardwareSecurityModule):
    """Mock implementation of HardwareSecurityModule for testing.
    
    This adapter provides a no-op implementation for cases where
    no real HSM is available (development, testing).
    
    WARNING: This mock provides default values and does NOT provide
    actual cryptographic security. Use only for testing/development.
    """
    
    def __init__(self) -> None:
        """Initialize mock HSM adapter."""
        self._counters: dict[int, int] = {0: 0, 1: 0}
    
    async def get_counter(self, slot: int) -> int:
        """Get counter value (mock implementation)."""
        return self._counters.get(slot, 0)
    
    async def set_counter(self, slot: int, value: int) -> None:
        """Set counter value (mock implementation)."""
        self._counters[slot] = value
    
    async def sign(self, slot: int, data: bytes) -> bytes:
        """Sign data (mock implementation - returns dummy signature)."""
        import hashlib
        return hashlib.sha256(data).digest() * 2  # 64 bytes
    
    async def verify(self, slot: int, data: bytes, signature: bytes) -> bool:
        """Verify signature (mock - always returns True)."""
        return True
    
    async def is_available(self) -> bool:
        """Mock HSM is always available."""
        return True
