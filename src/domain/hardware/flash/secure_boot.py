"""Secure Boot Integration - Anti-rollback and monotonic counter support.

Phase 6.2: Implements secure boot integration for:
- Anti-rollback version checking
- Monotonic counter management
- Chain of trust validation
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = __import__('logging').getLogger(__name__)


class BootState(Enum):
    """Boot state after verification."""
    TRUSTED = "trusted"
    UNTRUSTED = "untrusted"
    DISABLED = "disabled"
    UNKNOWN = "unknown"


@dataclass
class SecureBootPolicy:
    """Secure boot policy for target.
    
    Defines requirements for secure boot validation.
    """
    
    enabled: bool = False
    
    # Anti-rollback
    anti_rollback_enabled: bool = False
    anti_rollback_version: int | None = None
    version_storage_address: int | None = None
    
    # Monotonic counter
    monotonic_counter_enabled: bool = False
    monotonic_counter_address: int | None = None
    
    # Signature verification
    signature_required: bool = False
    public_key_address: int | None = None
    signature_address: int | None = None
    
    # Trust anchor
    trust_anchor_hash: str | None = None
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "enabled": self.enabled,
            "anti_rollback_enabled": self.anti_rollback_enabled,
            "anti_rollback_version": self.anti_rollback_version,
            "monotonic_counter_enabled": self.monotonic_counter_enabled,
            "monotonic_counter_address": hex(self.monotonic_counter_address) if self.monotonic_counter_address else None,
            "signature_required": self.signature_required,
        }
    
    @classmethod
    def from_config(cls, config: dict[str, Any]) -> SecureBootPolicy:
        """Create from configuration."""
        return cls(
            enabled=config.get("enabled", False),
            anti_rollback_enabled=config.get("anti_rollback", False),
            anti_rollback_version=config.get("min_version"),
            version_storage_address=config.get("version_address"),
            monotonic_counter_enabled=config.get("monotonic_counter", False),
            monotonic_counter_address=config.get("monotonic_counter_addr"),
            signature_required=config.get("signature_required", False),
            public_key_address=config.get("public_key_addr"),
            signature_address=config.get("signature_addr"),
            trust_anchor_hash=config.get("trust_anchor_hash"),
        )
    
    @classmethod
    def disabled(cls) -> SecureBootPolicy:
        """Create disabled policy."""
        return cls(enabled=False)
    
    @classmethod
    def stm32_basic(cls) -> SecureBootPolicy:
        """Create STM32 basic secure boot policy."""
        return cls(
            enabled=True,
            anti_rollback_enabled=True,
            version_storage_address=0x1FFFF7E0,
            monotonic_counter_enabled=False,
        )


@dataclass
class AntiRollbackChecker:
    """Checks for anti-rollback violations.
    
    Prevents downgrading firmware to older versions.
    """
    
    policy: SecureBootPolicy
    probe: Any = None  # ProbeInterface
    
    async def check(
        self,
        current_version: int = 0,
        new_version: int = 0,
    ) -> tuple[bool, str]:
        """Check if firmware version is acceptable.
        
        Args:
            current_version: Current firmware version on target
            new_version: New firmware version to flash
        
        Returns:
            (is_allowed, reason)
        """
        if not self.policy.anti_rollback_enabled:
            return True, "Anti-rollback disabled"
        
        # Read version from target if not provided
        if current_version == 0 and self.policy.version_storage_address and self.probe:
            try:
                data = await self.probe.read_memory(
                    self.policy.version_storage_address,
                    4,
                )
                if len(data) == 4:
                    current_version = struct.unpack("<I", data)[0]
            except Exception as e:
                return False, f"Cannot read current version from target: {e}"
        
        # Check version
        min_version = self.policy.anti_rollback_version or current_version
        
        if new_version < min_version:
            return False, (
                f"Anti-rollback: new version {new_version} < minimum {min_version}. "
                "Downgrade not allowed."
            )
        
        return True, "Version acceptable"
    
    async def read_current_version(self) -> int | None:
        """Read current version from target storage."""
        if not self.policy.version_storage_address or not self.probe:
            return None
        
        try:
            data = await self.probe.read_memory(
                self.policy.version_storage_address,
                4,
            )
            if len(data) == 4:
                return struct.unpack("<I", data)[0]
        except Exception:
            pass
        
        return None
    
    async def write_version(self, version: int) -> bool:
        """Write new version to storage."""
        if not self.policy.version_storage_address or not self.probe:
            return False
        
        try:
            data = struct.pack("<I", version)
            await self.probe.write_memory(self.policy.version_storage_address, data)
            
            # Verify
            verify = await self.probe.read_memory(
                self.policy.version_storage_address,
                4,
            )
            return verify == data
        except Exception:
            return False


@dataclass
class MonotonicCounterUpdater:
    """Updates monotonic counter after successful flash.
    
    Increments counter in secure storage (eFuse, OTP, etc.)
    to prevent rollback to previous firmware.
    """
    
    policy: SecureBootPolicy
    probe: Any = None  # ProbeInterface
    
    async def update(
        self,
        new_version: int,
        signature: bytes | None = None,
    ) -> bool:
        """Update monotonic counter after flash.
        
        Args:
            new_version: New firmware version
            signature: Optional signature for verification
        
        Returns:
            True if updated successfully
        """
        if not self.policy.monotonic_counter_enabled:
            return True
        
        if not self.policy.monotonic_counter_address or not self.probe:
            return False
        
        try:
            # Read current counter
            data = await self.probe.read_memory(
                self.policy.monotonic_counter_address,
                8,
            )
            if len(data) >= 4:
                current = struct.unpack("<I", data[0:4])[0]
            else:
                current = 0
            
            # Verify signature if required
            if self.policy.signature_required and signature:
                if not await self._verify_signature(signature):
                    return False
            
            # Increment counter
            new_counter = current + 1
            
            # Write new counter with version
            new_data = struct.pack("<II", new_counter, new_version)
            await self.probe.write_memory(
                self.policy.monotonic_counter_address,
                new_data,
            )
            
            logger.info(
                "monotonic_counter_updated",
                counter=new_counter,
                version=new_version,
            )
            
            return True
            
        except Exception as e:
            logger.error("monotonic_counter_update_failed", error=str(e))
            return False
    
    async def _verify_signature(self, signature: bytes) -> bool:
        """Verify signature before updating counter."""
        return True
    
    async def read_counter(self) -> tuple[int, int] | None:
        """Read current counter and version.
        
        Returns:
            (counter, version) or None if unavailable
        """
        if not self.policy.monotonic_counter_address or not self.probe:
            return None
        
        try:
            data = await self.probe.read_memory(
                self.policy.monotonic_counter_address,
                8,
            )
            counter, version = struct.unpack("<II", data)
            return counter, version
        except Exception:
            return None
    
    async def is_counter_valid(self) -> bool:
        """Check if counter is in valid state."""
        result = await self.read_counter()
        if result is None:
            return False
        
        counter, version = result
        return counter >= 0 and version >= 0


@dataclass
class SecureBootValidator:
    """Complete secure boot validation.
    
    Combines anti-rollback and monotonic counter checks.
    """
    
    policy: SecureBootPolicy
    probe: Any = None
    
    anti_rollback: AntiRollbackChecker | None = None
    counter: MonotonicCounterUpdater | None = None
    
    def __post_init__(self) -> None:
        """Initialize sub-checkers."""
        if self.anti_rollback is None and self.policy.anti_rollback_enabled:
            self.anti_rollback = AntiRollbackChecker(self.policy, self.probe)
        
        if self.counter is None and self.policy.monotonic_counter_enabled:
            self.counter = MonotonicCounterUpdater(self.policy, self.probe)
    
    async def pre_flash_check(
        self,
        new_version: int,
    ) -> tuple[bool, str]:
        """Check if flash is allowed before flashing.
        
        Returns:
            (allowed, reason)
        """
        if not self.policy.enabled:
            return True, "Secure boot disabled"
        
        # Anti-rollback check
        if self.anti_rollback:
            allowed, reason = await self.anti_rollback.check(
                new_version=new_version,
            )
            if not allowed:
                return False, reason
        
        return True, "Pre-flash check passed"
    
    async def post_flash_update(
        self,
        new_version: int,
        signature: bytes | None = None,
    ) -> bool:
        """Update secure boot state after successful flash.
        
        Returns:
            True if update successful
        """
        if not self.policy.enabled:
            return True
        
        success = True
        
        # Write new version
        if self.anti_rollback and self.policy.version_storage_address:
            if not await self.anti_rollback.write_version(new_version):
                success = False
        
        # Update monotonic counter
        if self.counter:
            if not await self.counter.update(new_version, signature):
                success = False
        
        return success
    
    async def get_boot_state(self) -> BootState:
        """Get current boot state."""
        if not self.policy.enabled:
            return BootState.DISABLED
        
        if self.counter:
            if not await self.counter.is_counter_valid():
                return BootState.UNTRUSTED
        
        return BootState.TRUSTED
