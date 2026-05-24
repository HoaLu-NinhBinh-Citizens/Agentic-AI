"""Hardware Trust Anchor - Anti-rollback protection with hardware-backed monotonic counter.

Phase 6.2 P1: Hardware-backed anti-rollback trust anchor.

CRITICAL: Anti-rollback must be anchored in hardware (OTP/eFuse/secure element/bootloader),
NOT in debug probe writes. This module models the hardware trust boundary.

Trust hierarchy:
1. OTP/eFuse (immutable) - highest trust
2. Secure Element (tamper-evident) - high trust  
3. Bootloader-managed (software trust anchor) - medium trust
4. Debug probe writes (software only) - NOT trusted for anti-rollback

For production:
- Use OTP/eFuse when available (STM32 Option Bytes, NXP OTFAD, etc.)
- Use Secure Element (TPM, SE) when available
- Fallback to bootloader-managed with caveats
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class TrustAnchorType(Enum):
    """Types of hardware trust anchors for anti-rollback."""
    
    # Hardware immutable storage
    OTP_EPROM = "otp_eprom"           # One-time programmable EPROM
    OTP_EFUSE = "otp_efuse"           # eFuse (STM32, ESP32, etc.)
    SECURE_ELEMENT = "secure_element"  # TPM, Secure Enclave, etc.
    
    # Software trust anchors (with caveats)
    BOOTLOADER = "bootloader"         # Bootloader-managed counter
    FLASH_PAGE = "flash_page"          # Dedicated flash page (MCUboot style)
    
    # Debug/testing only (NOT for production)
    DEBUG_PROBE = "debug_probe"       # Written via debug interface - NOT TRUSTED
    RAM = "ram"                       # RAM-based - lost on reset


class AntiRollbackError(Exception):
    """Raised when anti-rollback validation fails."""
    pass


class TrustAnchorUnavailableError(AntiRollbackError):
    """Raised when required trust anchor is not available."""
    pass


@dataclass
class AntiRollbackVersion:
    """Version information for anti-rollback checking."""
    
    version: int
    min_version: int
    timestamp: datetime = field(default_factory=datetime.now)
    
    # Hardware attestation
    anchor_type: TrustAnchorType = TrustAnchorType.BOOTLOADER
    anchor_id: str = ""
    attestation: Optional[bytes] = None
    
    def is_valid(self) -> bool:
        """Check if version meets minimum requirement."""
        return self.version >= self.min_version


@dataclass
class TrustAnchorConfig:
    """Configuration for hardware trust anchor."""
    
    # Trust anchor type
    anchor_type: TrustAnchorType = TrustAnchorType.BOOTLOADER
    
    # For OTP/eFuse
    otp_base_address: int = 0x1FFF7800  # STM32 Option Bytes example
    otp_version_offset: int = 0
    
    # For Secure Element
    se_slot_id: int = 0
    se_key_id: int = 0
    
    # For Bootloader/Flash page
    bootloader_magic: int = 0x8BADF00D
    flash_page_base: int = 0x0801F000  # Last page example
    
    # Minimum acceptable trust level
    # Set to OTP or SECURE_ELEMENT for production
    minimum_trust_level: TrustAnchorType = TrustAnchorType.BOOTLOADER
    
    # Version floor
    min_anti_rollback_version: int = 0
    
    def get_trust_level(self) -> int:
        """Get numeric trust level (higher = more trusted)."""
        levels = {
            TrustAnchorType.RAM: 0,
            TrustAnchorType.DEBUG_PROBE: 1,
            TrustAnchorType.FLASH_PAGE: 2,
            TrustAnchorType.BOOTLOADER: 3,
            TrustAnchorType.SECURE_ELEMENT: 4,
            TrustAnchorType.OTP_EFUSE: 5,
            TrustAnchorType.OTP_EPROM: 5,
        }
        return levels.get(self.anchor_type, 0)
    
    def meets_minimum_trust(self) -> bool:
        """Check if current trust level meets minimum requirement."""
        return self.get_trust_level() >= self.get_minimum_trust_level()
    
    def get_minimum_trust_level(self) -> int:
        """Get numeric level for minimum trust requirement."""
        levels = {
            TrustAnchorType.RAM: 0,
            TrustAnchorType.DEBUG_PROBE: 1,
            TrustAnchorType.FLASH_PAGE: 2,
            TrustAnchorType.BOOTLOADER: 3,
            TrustAnchorType.SECURE_ELEMENT: 4,
            TrustAnchorType.OTP_EFUSE: 5,
            TrustAnchorType.OTP_EPROM: 5,
        }
        return levels.get(self.minimum_trust_level, 0)


@dataclass
class TrustAnchorState:
    """Current state of the trust anchor."""
    
    anchor_type: TrustAnchorType
    current_version: int = 0
    is_locked: bool = False
    last_updated: datetime = field(default_factory=datetime.now)
    
    # Attestation data
    attestation_hash: str = ""
    attestation_signature: Optional[bytes] = None
    
    # Errors
    read_errors: int = 0
    write_errors: int = 0
    verification_errors: int = 0


class HardwareTrustAnchor:
    """Hardware-backed anti-rollback trust anchor.
    
    This is the CRITICAL piece for secure OTA:
    - Anti-rollback version MUST be stored in hardware
    - Bootloader/secure boot MUST read and enforce this version
    - Debug probe writes are NOT acceptable for production
    
    Usage:
    ```python
    # Production: Use OTP/eFuse or Secure Element
    anchor = HardwareTrustAnchor(
        config=TrustAnchorConfig(
            anchor_type=TrustAnchorType.OTP_EFUSE,
            minimum_trust_level=TrustAnchorType.OTP_EFUSE,
            min_anti_rollback_version=10,
        )
    )
    
    # Check version before accepting firmware
    if not await anchor.validate_version(firmware_version):
        raise AntiRollbackError("Firmware version too old")
    ```
    """
    
    def __init__(
        self,
        config: TrustAnchorConfig,
        probe: Any = None,  # Hardware probe interface
    ):
        self.config = config
        self.probe = probe
        self._state = TrustAnchorState(anchor_type=config.anchor_type)
        
        # Validate trust level at init
        if not config.meets_minimum_trust():
            logger.warning(
                "trust_anchor_trust_level_warning",
                current=config.anchor_type.value,
                minimum=config.minimum_trust_level.value,
            )
    
    async def read_version(self) -> AntiRollbackVersion:
        """Read current anti-rollback version from hardware.
        
        Returns:
            AntiRollbackVersion with current version and metadata.
            
        Raises:
            TrustAnchorUnavailableError: If trust anchor cannot be read.
        """
        try:
            version = await self._read_from_hardware()
            
            self._state.current_version = version
            self._state.last_updated = datetime.now()
            
            return AntiRollbackVersion(
                version=version,
                min_version=self.config.min_anti_rollback_version,
                anchor_type=self.config.anchor_type,
                anchor_id=self._get_anchor_id(),
                attestation=self._state.attestation_signature,
            )
            
        except Exception as e:
            self._state.read_errors += 1
            raise TrustAnchorUnavailableError(
                f"Failed to read trust anchor: {e}"
            ) from e
    
    async def write_version(self, version: int) -> bool:
        """Write new anti-rollback version to hardware.
        
        WARNING: This should only be called by:
        1. Bootloader during secure boot
        2. Secure element key ceremony
        3. OTA update acceptance (after signature validation)
        
        NOT by debug probe in production!
        
        Args:
            version: New version number (must be higher than current).
            
        Returns:
            True if written successfully.
            
        Raises:
            AntiRollbackError: If version is not higher or write fails.
        """
        # Read current version first
        current = await self.read_version()
        
        if version <= current.version:
            raise AntiRollbackError(
                f"Anti-rollback version must increase: "
                f"current={current.version}, new={version}"
            )
        
        # Verify trust level allows write
        if self.config.anchor_type in (
            TrustAnchorType.DEBUG_PROBE,
            TrustAnchorType.RAM,
        ):
            logger.error(
                "anti_rollback_write_rejected",
                reason="untrusted_anchor_type",
                type=self.config.anchor_type.value,
            )
            raise AntiRollbackError(
                f"Cannot write to {self.config.anchor_type.value} in production"
            )
        
        try:
            success = await self._write_to_hardware(version)
            
            if success:
                self._state.current_version = version
                self._state.last_updated = datetime.now()
                logger.info(
                    "anti_rollback_version_updated",
                    version=version,
                    anchor=self.config.anchor_type.value,
                )
            
            return success
            
        except Exception as e:
            self._state.write_errors += 1
            raise AntiRollbackError(f"Failed to write trust anchor: {e}") from e
    
    async def validate_version(self, firmware_version: int) -> bool:
        """Validate firmware version against anti-rollback counter.
        
        Args:
            firmware_version: Version of firmware being loaded.
            
        Returns:
            True if version is acceptable.
        """
        try:
            current = await self.read_version()
            
            if firmware_version < current.min_version:
                logger.warning(
                    "anti_rollback_validation_failed",
                    firmware_version=firmware_version,
                    minimum=self.config.min_anti_rollback_version,
                    current_version=current.version,
                )
                return False
            
            return True
            
        except TrustAnchorUnavailableError:
            # If we can't read anchor, reject by default
            logger.error("anti_rollback_validation_rejected", reason="anchor_unavailable")
            return False
    
    async def get_attestation(self) -> dict[str, Any]:
        """Get attestation data for verification.
        
        Returns:
            Attestation dictionary with version and signature.
        """
        version = await self.read_version()
        
        return {
            "anchor_type": self.config.anchor_type.value,
            "current_version": version.version,
            "min_version": version.min_version,
            "timestamp": version.timestamp.isoformat(),
            "attestation_hash": self._state.attestation_hash,
            "is_trusted": self.config.meets_minimum_trust(),
        }
    
    async def verify_attestation(self, attestation: dict[str, Any]) -> bool:
        """Verify attestation data integrity.
        
        Args:
            attestation: Attestation from get_attestation().
            
        Returns:
            True if attestation is valid.
        """
        # Check anchor type matches
        if attestation.get("anchor_type") != self.config.anchor_type.value:
            return False
        
        # Check version hasn't been tampered
        try:
            current = await self.read_version()
            if current.version != attestation.get("current_version"):
                logger.warning(
                    "attestation_version_mismatch",
                    attestation=attestation.get("current_version"),
                    actual=current.version,
                )
                return False
        except TrustAnchorUnavailableError:
            return False
        
        # Verify hash chain
        expected_hash = hashlib.sha256(
            f"{current.version}:{current.timestamp.isoformat()}".encode()
        ).hexdigest()
        
        if attestation.get("attestation_hash") != expected_hash:
            self._state.verification_errors += 1
            return False
        
        return True
    
    def get_state(self) -> dict[str, Any]:
        """Get current trust anchor state."""
        return {
            "anchor_type": self._state.anchor_type.value,
            "current_version": self._state.current_version,
            "is_locked": self._state.is_locked,
            "last_updated": self._state.last_updated.isoformat(),
            "errors": {
                "read": self._state.read_errors,
                "write": self._state.write_errors,
                "verification": self._state.verification_errors,
            },
        }
    
    # =================================================================
    # Hardware-specific implementations
    # =================================================================
    
    async def _read_from_hardware(self) -> int:
        """Read version from hardware (implementation-specific)."""
        if self.probe is None:
            raise TrustAnchorUnavailableError("No probe interface")
        
        if self.config.anchor_type == TrustAnchorType.OTP_EFUSE:
            return await self._read_otp_efuse()
        elif self.config.anchor_type == TrustAnchorType.SECURE_ELEMENT:
            return await self._read_secure_element()
        elif self.config.anchor_type in (
            TrustAnchorType.BOOTLOADER,
            TrustAnchorType.FLASH_PAGE,
        ):
            return await self._read_flash_page()
        else:
            raise TrustAnchorUnavailableError(
                f"Unsupported anchor type: {self.config.anchor_type}"
            )
    
    async def _write_to_hardware(self, version: int) -> bool:
        """Write version to hardware (implementation-specific)."""
        if self.probe is None:
            raise TrustAnchorUnavailableError("No probe interface")
        
        if self.config.anchor_type == TrustAnchorType.OTP_EFUSE:
            return await self._write_otp_efuse(version)
        elif self.config.anchor_type == TrustAnchorType.SECURE_ELEMENT:
            return await self._write_secure_element(version)
        elif self.config.anchor_type in (
            TrustAnchorType.BOOTLOADER,
            TrustAnchorType.FLASH_PAGE,
        ):
            return await self._write_flash_page(version)
        else:
            raise AntiRollbackError(
                f"Cannot write to {self.config.anchor_type.value}"
            )
    
    async def _read_otp_efuse(self) -> int:
        """Read from OTP/eFuse."""
        # Implementation depends on specific MCU
        # Example for STM32:
        # addr = self.config.otp_base_address + self.config.otp_version_offset
        # data = await self.probe.read_memory(addr, 4)
        # return int.from_bytes(data, 'little')
        raise NotImplementedError("MCU-specific implementation required")
    
    async def _write_otp_efuse(self, version: int) -> bool:
        """Write to OTP/eFuse (one-time!)."""
        # WARNING: OTP can only be written once!
        # Use with extreme caution
        raise NotImplementedError("MCU-specific implementation required")
    
    async def _read_secure_element(self) -> int:
        """Read from Secure Element."""
        raise NotImplementedError("Secure element implementation required")
    
    async def _write_secure_element(self, version: int) -> bool:
        """Write to Secure Element."""
        raise NotImplementedError("Secure element implementation required")
    
    async def _read_flash_page(self) -> int:
        """Read from bootloader-managed flash page."""
        addr = self.config.flash_page_base
        data = await self.probe.read_memory(addr, 4)
        magic = int.from_bytes(data[:4], 'little')
        
        if magic != self.config.bootloader_magic:
            # Return minimum version if magic invalid
            return 0
        
        version_bytes = await self.probe.read_memory(addr + 4, 4)
        return int.from_bytes(version_bytes, 'little')
    
    async def _write_flash_page(self, version: int) -> bool:
        """Write to bootloader flash page (MCUboot-style)."""
        addr = self.config.flash_page_base
        
        # MCUboot-style trailer
        magic = self.config.bootloader_magic.to_bytes(4, 'little')
        version_bytes = version.to_bytes(4, 'little')
        
        # Calculate checksum
        data = magic + version_bytes
        checksum = hashlib.sha256(data).digest()[:4]
        
        # Write all fields
        await self.probe.write_memory(addr, magic + version_bytes + checksum)
        
        # Verify
        read_back = await self._read_flash_page()
        return read_back == version
    
    def _get_anchor_id(self) -> str:
        """Get unique identifier for this anchor."""
        if self.config.anchor_type == TrustAnchorType.OTP_EFUSE:
            return f"otp@0x{self.config.otp_base_address:x}"
        elif self.config.anchor_type == TrustAnchorType.SECURE_ELEMENT:
            return f"se@slot{self.config.se_slot_id}"
        elif self.config.anchor_type == TrustAnchorType.BOOTLOADER:
            return f"bl@0x{self.config.flash_page_base:x}"
        return "unknown"


class AntiRollbackValidator:
    """Validates firmware against anti-rollback requirements.
    
    Use this to validate firmware before accepting OTA update.
    """
    
    def __init__(
        self,
        trust_anchor: HardwareTrustAnchor,
        signing_policy: Any = None,  # FirmwareSigningPolicy
    ):
        self.trust_anchor = trust_anchor
        self.signing_policy = signing_policy
    
    async def validate_firmware(
        self,
        firmware_version: int,
        signature_valid: bool,
        target_name: str,
    ) -> tuple[bool, str]:
        """Validate firmware for OTA acceptance.
        
        Args:
            firmware_version: Version of incoming firmware.
            signature_valid: Whether signature verification passed.
            target_name: Target device name.
            
        Returns:
            (is_valid, reason)
        """
        # Step 1: Check signature (if policy configured)
        if self.signing_policy and not signature_valid:
            return False, "Signature verification failed"
        
        # Step 2: Check anti-rollback version
        try:
            current_version = await self.trust_anchor.read_version()
            
            if firmware_version < current_version.min_version:
                return False, (
                    f"Version {firmware_version} below minimum "
                    f"{current_version.min_version}"
                )
            
            if firmware_version < current_version.version:
                return False, (
                    f"Anti-rollback: firmware version {firmware_version} "
                    f"is older than installed version {current_version.version}"
                )
            
        except TrustAnchorUnavailableError as e:
            # If anchor unavailable, reject by default
            return False, f"Trust anchor unavailable: {e}"
        
        return True, "Valid"
    
    async def update_after_successful_boot(
        self,
        firmware_version: int,
    ) -> bool:
        """Update anti-rollback counter after successful boot.
        
        Call this from bootloader after firmware boots successfully.
        
        Args:
            firmware_version: Version that booted.
            
        Returns:
            True if updated successfully.
        """
        try:
            await self.trust_anchor.write_version(firmware_version)
            logger.info(
                "anti_rollback_updated",
                version=firmware_version,
            )
            return True
        except AntiRollbackError as e:
            logger.error(
                "anti_rollback_update_failed",
                version=firmware_version,
                error=str(e),
            )
            return False
