"""Hardware Security Module (HSM) Port Interface.

This module defines the domain port for hardware security operations.
The domain layer depends on this abstract interface, not on concrete
infrastructure implementations.

Anti-Pattern (before refactor):
    from src.infrastructure.hsm.atecc608 import get_hsm  # VIOLATION!
    hsm = await get_hsm()

Correct Pattern (after refactor):
    # HSM is injected via constructor or factory
    manager = ABPartitionManager(probe, config, hsm=injected_hsm)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class HardwareSecurityModule(ABC):
    """Abstract interface for hardware security module operations.
    
    This interface defines the contract for HSM operations used by the
    domain layer. Concrete implementations are provided by infrastructure.
    
    Methods:
        get_counter(): Read monotonic counter for anti-rollback
        set_counter(): Set counter value (for anti-rollback)
        sign(): Sign data with key in slot
        verify(): Verify signature
        is_available(): Check if HSM is available
    
    Example:
        class MyHSM(HardwareSecurityModule):
            async def get_counter(self, slot: int) -> int:
                # Implementation
                pass
    """
    
    @abstractmethod
    async def get_counter(self, slot: int) -> int:
        """Read monotonic counter value.
        
        Used for anti-rollback protection.
        
        Args:
            slot: Counter slot number (typically 0 for primary)
            
        Returns:
            Current counter value
        """
        pass
    
    @abstractmethod
    async def set_counter(self, slot: int, value: int) -> None:
        """Set counter value.
        
        Used for anti-rollback protection when advancing counter.
        
        Args:
            slot: Counter slot number
            value: New counter value
        """
        pass
    
    @abstractmethod
    async def sign(self, slot: int, data: bytes) -> bytes:
        """Sign data with key in slot.
        
        Args:
            slot: Key slot number
            data: Data to sign (typically SHA256 hash)
            
        Returns:
            Signature bytes (typically 64 bytes for ECDSA P-256)
        """
        pass
    
    @abstractmethod
    async def verify(self, slot: int, data: bytes, signature: bytes) -> bool:
        """Verify signature.
        
        Args:
            slot: Key slot number
            data: Original data
            signature: Signature to verify
            
        Returns:
            True if signature is valid
        """
        pass
    
    @abstractmethod
    async def is_available(self) -> bool:
        """Check if HSM is available.
        
        Returns:
            True if HSM is initialized and ready
        """
        pass
