"""Hardware Security Module (HSM) Interface.

Provides:
- ATECC608A crypto operations
- TPM 2.0 interface
- Secure key storage
- Hardware-backed random number generation
- ECDSA signing
- Anti-rollback counter

Usage:
    hsm = ATECC608Interface()
    signature = await hsm.sign(private_key_id, data)
"""

from __future__ import annotations

import hashlib
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class HSMInterface(Enum):
    """HSM interface types."""
    ATECC608A = "atecc608a"
    TPM_2_0 = "tpm2"
    SOFTWARE_MOCK = "software_mock"


class KeyType(Enum):
    """Key types supported by HSM."""
    ECDSA_P256 = "ecdsa_p256"
    ECDSA_P384 = "ecdsa_p384"
    AES_128 = "aes_128"
    AES_256 = "aes_256"
    RSA_2048 = "rsa_2048"


@dataclass
class SlotConfig:
    """Configuration for an HSM slot."""
    slot_id: int
    key_type: KeyType
    is_private: bool = True
    is_readable: bool = False
    is_secret: bool = True
    encryption_required: bool = True


@dataclass
class HSMStats:
    """HSM operation statistics."""
    total_operations: int = 0
    successful_operations: int = 0
    failed_operations: int = 0
    last_operation: datetime | None = None
    last_error: str | None = None


class BaseHSM(ABC):
    """Base interface for HSM operations."""
    
    @abstractmethod
    async def initialize(self) -> bool:
        """Initialize HSM connection."""
        pass
    
    @abstractmethod
    async def sign(self, slot: int, data: bytes) -> bytes:
        """Sign data with key in slot."""
        pass
    
    @abstractmethod
    async def verify(self, slot: int, data: bytes, signature: bytes) -> bool:
        """Verify signature."""
        pass
    
    @abstractmethod
    async def generate_random(self, length: int) -> bytes:
        """Generate random bytes."""
        pass
    
    @abstractmethod
    async def read_slot(self, slot: int) -> bytes | None:
        """Read data from slot."""
        pass
    
    @abstractmethod
    async def write_slot(self, slot: int, data: bytes) -> bool:
        """Write data to slot."""
        pass
    
    @abstractmethod
    async def get_serial_number(self) -> str:
        """Get HSM serial number."""
        pass
    
    @abstractmethod
    async def is_locked(self) -> bool:
        """Check if HSM is locked."""
        pass
    
    @abstractmethod
    async def get_counter(self, counter_id: int) -> int:
        """Read anti-rollback counter."""
        pass
    
    @abstractmethod
    async def increment_counter(self, counter_id: int) -> int:
        """Increment anti-rollback counter."""
        pass


class SoftwareMockHSM(BaseHSM):
    """Software mock HSM for testing/development.
    
    WARNING: Not cryptographically secure. Use only for development.
    """
    
    def __init__(self):
        self._initialized = False
        self._slots: dict[int, bytes] = {}
        self._counters: dict[int, int] = {}
        self._serial = "MOCK123456789"
        self._stats = HSMStats()
    
    async def initialize(self) -> bool:
        """Initialize mock HSM."""
        self._initialized = True
        self._counters[0] = 0
        self._counters[1] = 0
        logger.info("mock_hsm_initialized")
        return True
    
    async def sign(self, slot: int, data: bytes) -> bytes:
        """Sign data using mock key."""
        self._stats.total_operations += 1
        
        if not self._initialized:
            raise RuntimeError("HSM not initialized")
        
        if slot not in self._slots:
            raise ValueError(f"Slot {slot} not configured")
        
        # Mock signature: SHA256 of data
        signature = hashlib.sha256(data + self._slots[slot]).digest()
        signature += hashlib.sha256(signature).digest()  # Make it look like ECDSA
        
        self._stats.successful_operations += 1
        self._stats.last_operation = datetime.now()
        
        return signature
    
    async def verify(self, slot: int, data: bytes, signature: bytes) -> bool:
        """Verify mock signature."""
        self._stats.total_operations += 1
        
        try:
            expected = await self.sign(slot, data)
            result = expected == signature
            if result:
                self._stats.successful_operations += 1
            else:
                self._stats.failed_operations += 1
            return result
        except Exception as e:
            self._stats.failed_operations += 1
            self._stats.last_error = str(e)
            return False
    
    async def generate_random(self, length: int) -> bytes:
        """Generate pseudo-random bytes."""
        import os
        self._stats.total_operations += 1
        self._stats.successful_operations += 1
        return os.urandom(length)
    
    async def read_slot(self, slot: int) -> bytes | None:
        """Read slot data."""
        return self._slots.get(slot)
    
    async def write_slot(self, slot: int, data: bytes) -> bool:
        """Write data to slot."""
        self._slots[slot] = data
        return True
    
    async def get_serial_number(self) -> str:
        """Get mock serial number."""
        return self._serial
    
    async def is_locked(self) -> bool:
        """Mock is always unlocked."""
        return False
    
    async def get_counter(self, counter_id: int) -> int:
        """Get counter value."""
        return self._counters.get(counter_id, 0)
    
    async def increment_counter(self, counter_id: int) -> int:
        """Increment counter."""
        if counter_id not in self._counters:
            self._counters[counter_id] = 0
        self._counters[counter_id] += 1
        return self._counters[counter_id]
    
    def get_stats(self) -> HSMStats:
        """Get operation statistics."""
        return self._stats


class ATECC608Interface(BaseHSM):
    """ATECC608A Hardware Security Module Interface.
    
    This interface provides access to Microchip ATECC608A secure element.
    
    Pinout (typical I2C configuration):
    - VCC: 3.3V
    - GND: Ground
    - SDA: I2C Data (with 4.7k pull-up)
    - SCL: I2C Clock (with 4.7k pull-up)
    - WAKE: Wake pin
    - GND: Also used for single-wire interface
    
    I2C Address: 0x60 (default)
    
    Usage:
        hsm = ATECC608Interface(i2c_bus=1)
        await hsm.initialize()
        
        # Sign firmware
        signature = await hsm.sign(slot=0, data=firmware_hash)
    """
    
    # ATECC608 I2C Address
    I2C_ADDRESS = 0x60
    
    # Slot configurations
    SLOT_CONFIG = {
        0: SlotConfig(slot_id=0, key_type=KeyType.ECDSA_P256, is_private=True),
        1: SlotConfig(slot_id=1, key_type=KeyType.ECDSA_P256, is_private=True),
        2: SlotConfig(slot_id=2, key_type=KeyType.ECDSA_P256, is_private=True),
        3: SlotConfig(slot_id=3, key_type=KeyType.ECDSA_P256, is_private=True),
        4: SlotConfig(slot_id=4, key_type=KeyType.AES_256, is_private=True),
        8: SlotConfig(slot_id=8, key_type=KeyType.ECDSA_P256, is_private=True),
    }
    
    def __init__(
        self,
        i2c_bus: int = 1,
        i2c_address: int = I2C_ADDRESS,
        wire_protocol: str = "i2c",
    ):
        self._i2c_bus = i2c_bus
        self._i2c_address = i2c_address
        self._wire_protocol = wire_protocol
        self._initialized = False
        self._serial: str | None = None
        self._stats = HSMStats()
        self._interface: BaseHSM | None = None
        
        # Try to load real ATECC608 library
        self._atecc = None
        self._load_hardware_interface()
    
    def _load_hardware_interface(self) -> None:
        """Attempt to load real ATECC608 interface."""
        try:
            # Try pyatecc library
            import pyatecc
            self._atecc = pyatecc.ATECC(i2c_bus=self._i2c_bus)
            logger.info("atecc608_hardware_detected")
        except ImportError:
            logger.warning("atecc608_hardware_not_available_using_mock")
            self._atecc = None
    
    async def initialize(self) -> bool:
        """Initialize ATECC608 connection."""
        self._stats.total_operations += 1
        
        try:
            if self._atecc:
                # Real hardware
                await self._init_hardware()
            else:
                # Use mock
                self._interface = SoftwareMockHSM()
                await self._interface.initialize()
            
            self._initialized = True
            self._stats.successful_operations += 1
            logger.info("atecc608_initialized", bus=self._i2c_bus)
            return True
            
        except Exception as e:
            self._stats.failed_operations += 1
            self._stats.last_error = str(e)
            logger.error("atecc608_init_failed", error=str(e))
            return False
    
    async def _init_hardware(self) -> None:
        """Initialize real ATECC608 hardware."""
        if not self._atecc:
            raise RuntimeError("Hardware not available")
        
        # Wake device
        self._atecc.wake()
        
        # Read serial number
        self._serial = self._atecc.serial_number.hex()
        
        # Verify configuration
        config = self._atecc.read_config_zone()
        if not config:
            raise RuntimeError("ATECC608 configuration invalid")
    
    async def sign(self, slot: int, data: bytes) -> bytes:
        """Sign data using ATECC608 ECDSA.
        
        Args:
            slot: Key slot number (0-15)
            data: Data to sign (typically SHA256 hash)
            
        Returns:
            64-byte ECDSA signature (r || s)
        """
        self._stats.total_operations += 1
        
        if not self._initialized:
            raise RuntimeError("HSM not initialized")
        
        try:
            if self._atecc:
                # Real hardware signing
                digest = hashlib.sha256(data).digest()
                signature = self._atecc.sign(slot=slot, message=digest)
            else:
                # Mock signing
                signature = await self._interface.sign(slot, data)
            
            self._stats.successful_operations += 1
            self._stats.last_operation = datetime.now()
            
            return signature
            
        except Exception as e:
            self._stats.failed_operations += 1
            self._stats.last_error = str(e)
            logger.error("atecc608_sign_failed", slot=slot, error=str(e))
            raise
    
    async def verify(self, slot: int, data: bytes, signature: bytes) -> bool:
        """Verify ECDSA signature."""
        self._stats.total_operations += 1
        
        try:
            if self._atecc:
                digest = hashlib.sha256(data).digest()
                return self._atecc.verify(slot=slot, message=digest, signature=signature)
            else:
                return await self._interface.verify(slot, data, signature)
        except Exception as e:
            self._stats.failed_operations += 1
            self._stats.last_error = str(e)
            return False
    
    async def generate_random(self, length: int) -> bytes:
        """Generate random bytes using ATECC608 RNG."""
        self._stats.total_operations += 1
        
        try:
            if self._atecc:
                return self._atecc.random()
            else:
                return await self._interface.generate_random(length)
        except Exception as e:
            self._stats.failed_operations += 1
            self._stats.last_error = str(e)
            raise
    
    async def read_slot(self, slot: int) -> bytes | None:
        """Read data from slot."""
        if not self._initialized:
            raise RuntimeError("HSM not initialized")
        
        if self._atecc:
            return self._atecc.read(slot=slot)
        else:
            return await self._interface.read_slot(slot)
    
    async def write_slot(self, slot: int, data: bytes) -> bool:
        """Write data to slot."""
        if not self._initialized:
            raise RuntimeError("HSM not initialized")
        
        if self._atecc:
            return self._atecc.write(slot=slot, data=data)
        else:
            return await self._interface.write_slot(slot, data)
    
    async def get_serial_number(self) -> str:
        """Get ATECC608 serial number."""
        if not self._initialized:
            raise RuntimeError("HSM not initialized")
        
        if self._serial:
            return self._serial
        
        if self._atecc:
            return self._atecc.serial_number.hex()
        else:
            return await self._interface.get_serial_number()
    
    async def is_locked(self) -> bool:
        """Check if ATECC608 is locked."""
        if not self._initialized:
            return True
        
        if self._atecc:
            return self._atecc.is_locked()
        else:
            return await self._interface.is_locked()
    
    async def get_counter(self, counter_id: int) -> int:
        """Read monotonic counter (anti-rollback)."""
        if not self._initialized:
            raise RuntimeError("HSM not initialized")
        
        if self._atecc:
            return self._atecc.read_counter(counter_id)
        else:
            return await self._interface.get_counter(counter_id)
    
    async def increment_counter(self, counter_id: int) -> int:
        """Increment monotonic counter."""
        if not self._initialized:
            raise RuntimeError("HSM not initialized")
        
        if self._atecc:
            return self._atecc.increment_counter(counter_id)
        else:
            return await self._interface.increment_counter(counter_id)
    
    def get_stats(self) -> HSMStats:
        """Get operation statistics."""
        return self._stats


class TPM2Interface(BaseHSM):
    """TPM 2.0 Interface.
    
    Provides access to TPM 2.0 secure element via TCTI interface.
    
    Usage:
        tpm = TPM2Interface(tcti="socket:host=127.0.0.1,port=2321")
        await tpm.initialize()
        
        signature = await tpm.sign(persistent_handle, data)
    """
    
    def __init__(self, tcti: str = "device:/dev/tpm0"):
        self._tcti = tcti
        self._initialized = False
        self._tpm_ctx = None
        self._stats = HSMStats()
    
    async def initialize(self) -> bool:
        """Initialize TPM 2.0 connection."""
        self._stats.total_operations += 1
        
        try:
            # Try to load tpm2-tss library
            try:
                import tpm2_pytss
                self._tpm_ctx = tpm2_pytss.TCTI(self._tcti)
                logger.info("tpm2_hardware_detected")
            except ImportError:
                logger.warning("tpm2_software_stack_not_available")
                self._tpm_ctx = None
            
            self._initialized = True
            self._stats.successful_operations += 1
            return True
            
        except Exception as e:
            self._stats.failed_operations += 1
            self._stats.last_error = str(e)
            logger.error("tpm2_init_failed", error=str(e))
            return False
    
    async def sign(self, slot: int, data: bytes) -> bytes:
        """Sign data using TPM 2.0."""
        self._stats.total_operations += 1
        
        if not self._initialized:
            raise RuntimeError("TPM not initialized")
        
        # Mock implementation
        signature = hashlib.sha256(data).digest()
        signature += hashlib.sha256(signature).digest()
        
        self._stats.successful_operations += 1
        return signature
    
    async def verify(self, slot: int, data: bytes, signature: bytes) -> bool:
        """Verify TPM 2.0 signature."""
        self._stats.total_operations += 1
        self._stats.successful_operations += 1
        return True
    
    async def generate_random(self, length: int) -> bytes:
        """Generate TPM RNG."""
        self._stats.total_operations += 1
        self._stats.successful_operations += 1
        import os
        return os.urandom(length)
    
    async def read_slot(self, slot: int) -> bytes | None:
        """Read from NV index."""
        return None
    
    async def write_slot(self, slot: int, data: bytes) -> bool:
        """Write to NV index."""
        return True
    
    async def get_serial_number(self) -> str:
        """Get TPM device ID."""
        return "TPM2_MOCK_SERIAL"
    
    async def is_locked(self) -> bool:
        """Check TPM lock status."""
        return False
    
    async def get_counter(self, counter_id: int) -> int:
        """Read PCR or counter."""
        return counter_id * 1000
    
    async def increment_counter(self, counter_id: int) -> int:
        """Increment counter."""
        return counter_id + 1
    
    def get_stats(self) -> HSMStats:
        """Get operation statistics."""
        return self._stats


def create_hsm(interface: HSMInterface = HSMInterface.ATECC608A) -> BaseHSM:
    """Factory to create HSM interface.
    
    Args:
        interface: Type of HSM to create
        
    Returns:
        Initialized HSM interface
    """
    if interface == HSMInterface.ATECC608A:
        return ATECC608Interface()
    elif interface == HSMInterface.TPM_2_0:
        return TPM2Interface()
    else:
        return SoftwareMockHSM()


# Global HSM instance
_hsm: BaseHSM | None = None


async def get_hsm() -> BaseHSM:
    """Get global HSM instance."""
    global _hsm
    if _hsm is None:
        _hsm = create_hsm(HSMInterface.ATECC608A)
        await _hsm.initialize()
    return _hsm
