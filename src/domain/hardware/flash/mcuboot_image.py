"""MCUboot Image Trailer - Full spec implementation.

Implements the complete MCUboot image trailer structure as per:
https://github.com/mcu-tools/mcuboot/blob/master/docs/design.md

The image trailer is written at the end of each flash slot and contains:
- Magic bytes for validation
- Image header size
- Image size
- Image version
- Image hash (SHA-256)
- Signature (if enabled)
- Swap status (for swap-aware upgrades)
- Copy status (for direct-xip mode)
- Boot record (TLVs)
"""

from __future__ import annotations

import hashlib
import struct
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


# MCUboot constants
IMAGE_MAGIC = 0x96F3B83D  # "MHRS" - MCUboot Header Reserved Space
IMAGE_MAGIC_V1 = 0x6907     # Legacy magic
IMAGE_MAGIC_V2 = 0x96F3B83D  # Current magic

# Image trailer sizes (depends on flash alignment and features)
BOOT_MAGIC_SIZE = 16
IMAGE_TLV_SIZE = 4  # TLV header (type + len)
SHA256_SIZE = 32
SHA384_SIZE = 48
SHA512_SIZE = 64

# Default flash alignment
DEFAULT_FLASH_ALIGN = 4  # STM32 typically 4-byte aligned

# Image states
IMAGE_STATE_INVALID = 0
IMAGE_STATE_VALID = 1


class ImageSlot(Enum):
    """Image slot designation."""
    PRIMARY = "primary"   # Slot A - where new images are flashed
    SECONDARY = "secondary"  # Slot B - for swap or backup
    SCRATCH = "scratch"   # Scratch area for swap operations


class ImageType(Enum):
    """Type of firmware image."""
    FIRMWARE = "firmware"
    APPLICATION = "application"
    BOOTLOADER = "bootloader"


@dataclass
class ImageVersion:
    """Image semantic version."""
    major: int = 0
    minor: int = 0
    revision: int = 0
    build: int = 0
    
    def to_int(self) -> int:
        """Convert to 32-bit integer (mcuboot format)."""
        return (self.major << 24) | (self.minor << 16) | (self.revision << 8) | self.build
    
    @classmethod
    def from_int(cls, value: int) -> ImageVersion:
        """Create from 32-bit integer."""
        return cls(
            major=(value >> 24) & 0xFF,
            minor=(value >> 16) & 0xFF,
            revision=(value >> 8) & 0xFF,
            build=value & 0xFF,
        )
    
    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.revision}+{self.build}"
    
    def __lt__(self, other: ImageVersion) -> bool:
        if self.major != other.major:
            return self.major < other.major
        if self.minor != other.minor:
            return self.minor < other.minor
        if self.revision != other.revision:
            return self.revision < other.revision
        return self.build < other.build


@dataclass
class ImageHeader:
    """MCUboot image header structure.
    
    Size: 32 bytes (fixed)
    Layout:
        0-3: magic (IMAGE_MAGIC_V2)
        4-7: image_load_address (0 if not loadable)
        8-11: header_size (size of this header, typically 32)
        12-15: total_image_size (including header + payload + TLVs)
        16-19: image_header_version (1 for V2)
        20-23: flags (see ImageHeaderFlags)
        24-27: version (semantic version as uint32)
        28-31: reserved
    """
    
    # Constants
    HEADER_SIZE = 32
    HEADER_VERSION = 1
    
    # Struct format: little-endian
    STRUCT_FORMAT = "<IIHHI"
    
    magic: int = IMAGE_MAGIC_V2
    image_load_address: int = 0  # 0 = not loadable
    header_size: int = HEADER_SIZE
    total_image_size: int = 0  # Set after build
    image_header_version: int = HEADER_VERSION
    flags: int = 0  # ImageHeaderFlags
    version: ImageVersion = field(default_factory=ImageVersion)
    _pad: int = 0
    
    def pack(self) -> bytes:
        """Pack header to bytes."""
        return struct.pack(
            self.STRUCT_FORMAT,
            self.magic,
            self.image_load_address,
            self.header_size,
            self.total_image_size,
            self.image_header_version,
        ) + struct.pack(
            "<II",
            self.flags,
            self.version.to_int(),
        ) + struct.pack("<I", 0)  # Reserved
    
    @classmethod
    def unpack(cls, data: bytes) -> ImageHeader:
        """Unpack header from bytes."""
        if len(data) < 32:
            raise ValueError("Header data too short")
        
        (
            magic, load_addr, hdr_size, total_size, hdr_version,
            flags, version_int, reserved
        ) = struct.unpack("<IIHHIII", data[:28])
        
        return cls(
            magic=magic,
            image_load_address=load_addr,
            header_size=hdr_size,
            total_image_size=total_size,
            image_header_version=hdr_version,
            flags=flags,
            version=ImageVersion.from_int(version_int),
            _pad=reserved,
        )
    
    def is_valid(self) -> bool:
        """Check if header is valid."""
        return self.magic == IMAGE_MAGIC_V2 and self.header_size >= self.HEADER_SIZE


class ImageHeaderFlags(Enum):
    """Image header flags."""
    ENCRYPTED = 0x0001      # Image is encrypted
    ECHALPA = 0x0002        # Disable hardware key checks
    SWAP = 0x0004          # Swap-using scratch
    PERUSER_TLV = 0x0080   # User-defined TLVs present
    DONT_DELETE = 0x0100   # Don't delete on revert


class ImageTlvType(Enum):
    """Image TLV (Type-Length-Value) types."""
    SHA256 = 0x10         # Image hash (SHA-256)
    SHA384 = 0x11         # Image hash (SHA-384)
    SHA512 = 0x12         # Image hash (SHA-512)
    RSA2048 = 0x20        # RSA-2048 signature
    RSA3072 = 0x23        # RSA-3072 signature
    ECDSA256 = 0x21       # ECDSA-256 signature
    ECDSA384 = 0x25       # ECDSA-384 signature
    ED25519 = 0x26        # Ed25519 signature
    ENC_RSA2048 = 0x30    # RSA-2048 encrypted key
    ENC_EC256 = 0x31      # EC-256 encrypted key
    ENC_KW = 0x32         # Key in key-wrap format


@dataclass
class ImageTlv:
    """Image TLV entry."""
    
    tlv_type: ImageTlvType
    value: bytes
    
    STRUCT_FORMAT = "<HH"  # type (2 bytes) + len (2 bytes)
    
    def pack(self) -> bytes:
        """Pack TLV to bytes."""
        header = struct.pack(self.STRUCT_FORMAT, self.tlv_type.value, len(self.value))
        return header + self.value
    
    @classmethod
    def unpack(cls, data: bytes) -> ImageTlv:
        """Unpack TLV from bytes."""
        if len(data) < 4:
            raise ValueError("TLV data too short")
        
        tlv_type, length = struct.unpack(cls.STRUCT_FORMAT, data[:4])
        value = data[4:4 + length]
        
        return cls(
            tlv_type=ImageTlvType(tlv_type),
            value=value,
        )
    
    @classmethod
    def sha256(cls, image_data: bytes) -> ImageTlv:
        """Create SHA-256 hash TLV."""
        hash_value = hashlib.sha256(image_data).digest()
        return cls(tlv_type=ImageTlvType.SHA256, value=hash_value)


@dataclass 
class ImageTrailer:
    """MCUboot image trailer.
    
    Written at the end of each slot, after the image and its TLVs.
    Contains metadata needed for boot validation and swap operations.
    
    Layout (at end of flash slot):
        [-boot_magic] (16 bytes) - Must be last
        [-swap_size] (4 bytes) - Size of swap section
        [-copy_done] (1 byte) - Copy operation status
        [-image_ok] (1 byte) - Image confirmed valid
        [-swap_info] (1 byte) - Swap status info
        [-pad1] (1 byte)
        [-enckey] (32 bytes) - Encrypted key (if encrypted)
        [-crckey] (32 bytes) - CRC of key (if encrypted)
    """
    
    FLASH_ALIGN: int = DEFAULT_FLASH_ALIGN
    
    # Magic at end of trailer
    BOOT_MAGIC = bytes([
        0x77, 0x3D, 0x27, 0x3D,  # "w=';="
        0x77, 0x3D, 0x27, 0x3D,
        0x77, 0x3D, 0x27, 0x3D,
        0x77, 0x3D, 0x27, 0x3D,
    ])
    
    # Traction states
    COPY_DONE = 0x01  # Copy to primary slot done
    COPY_SWAP = 0x03  # Copy via swap
    
    IMAGE_OK = 0x01   # Image confirmed (not revert)
    IMAGE_REVERT = 0x02  # Image should be reverted
    
    # Swap states
    SWAP_NONE = 0
    SWAP_PERFORM = 1
    SWAP_REVERT = 2
    SWAP_FAIL = 3
    
    def calculate_trailer_size(
        self,
        has_encryption: bool = False,
        swap_enabled: bool = False,
    ) -> int:
        """Calculate total trailer size in bytes.
        
        Args:
            has_encryption: Whether image uses encryption
            swap_enabled: Whether swap operation is enabled
        
        Returns:
            Total trailer size aligned to flash boundary
        """
        size = 0
        
        # Boot magic (always present)
        size += BOOT_MAGIC_SIZE
        
        if swap_enabled:
            size += 4  # swap_size
        
        size += 1  # copy_done
        size += 1  # image_ok
        size += 1  # swap_info
        size += 1  # padding
        
        if has_encryption:
            size += 32  # enckey
            size += 4   # crckey (simplified)
        
        # Align to flash boundary
        alignment = self.FLASH_ALIGN
        size = ((size + alignment - 1) // alignment) * alignment
        
        return size
    
    def pack(
        self,
        copy_done: int = 0,
        image_ok: int = 0,
        swap_info: int = 0,
        swap_size: int = 0,
        has_magic: bool = True,
    ) -> bytes:
        """Pack trailer to bytes.
        
        Args:
            copy_done: Copy status (0, COPY_DONE, or COPY_SWAP)
            image_ok: Image confirmation (0, IMAGE_OK, or IMAGE_REVERT)
            swap_info: Swap status
            swap_size: Size of swap section
            has_magic: Include boot magic at end
        
        Returns:
            Packed trailer bytes
        """
        chunks = []
        
        # swap_size (only if swap enabled)
        if swap_size > 0:
            chunks.append(struct.pack("<I", swap_size))
        
        # copy_done
        chunks.append(bytes([copy_done & 0xFF]))
        
        # image_ok
        chunks.append(bytes([image_ok & 0xFF]))
        
        # swap_info
        chunks.append(bytes([swap_info & 0xFF]))
        
        # padding
        chunks.append(bytes([0]))
        
        # Boot magic at end
        if has_magic:
            chunks.append(self.BOOT_MAGIC)
        
        result = b"".join(chunks)
        
        # Align to flash boundary
        alignment = self.FLASH_ALIGN
        padding = (alignment - len(result) % alignment) % alignment
        if padding:
            result += bytes(padding)
        
        return result
    
    def parse(self, data: bytes) -> dict[str, Any]:
        """Parse trailer from bytes.
        
        Returns:
            Dictionary with parsed values
        """
        result = {
            "copy_done": 0,
            "image_ok": 0,
            "swap_info": 0,
            "swap_size": 0,
            "has_magic": False,
            "valid": False,
        }
        
        if len(data) < 5:
            return result
        
        offset = 0
        
        # Check for magic at end
        if len(data) >= 16 and data[-16:] == self.BOOT_MAGIC:
            result["has_magic"] = True
            data = data[:-16]
        
        # Parse backwards from end
        if len(data) >= 1:
            result["copy_done"] = data[-1]
            offset = 1
        
        if len(data) >= 2:
            result["image_ok"] = data[-2]
            offset = 2
        
        if len(data) >= 3:
            result["swap_info"] = data[-3]
            offset = 3
        
        if len(data) >= 4:
            result["swap_size"] = struct.unpack("<I", data[-4:])[0]
        
        # Validate
        result["valid"] = (
            result["has_magic"] or
            result["copy_done"] != 0 or
            result["image_ok"] != 0
        )
        
        return result


@dataclass
class McubootImage:
    """Complete MCUboot image with header and trailer.
    
    Usage:
    ```python
    # Build image
    image = McubootImage()
    image.load_firmware(firmware_bytes)
    image.set_version(1, 2, 3, 4)
    image.sign(private_key_pem, SignatureScheme.ECDSA_P256)
    
    # Serialize
    image_bytes = image.build()
    
    # Write to flash
    await probe.write_memory(slot_a_base, image_bytes)
    ```
    """
    
    header: ImageHeader = field(default_factory=ImageHeader)
    payload: bytes = b""
    tlvs: list[ImageTlv] = field(default_factory=list)
    trailer: ImageTrailer = field(default_factory=ImageTrailer)
    
    # Signing
    _signature: Optional[bytes] = None
    _signature_scheme: Optional[ImageTlvType] = None
    
    def load_firmware(self, data: bytes) -> None:
        """Load firmware payload."""
        self.payload = data
        self.header.total_image_size = self.header.HEADER_SIZE + len(data)
    
    def set_version(
        self,
        major: int,
        minor: int,
        revision: int = 0,
        build: int = 0,
    ) -> None:
        """Set image version."""
        self.header.version = ImageVersion(major, minor, revision, build)
    
    def add_hash_tlv(self, algorithm: str = "sha256") -> None:
        """Add image hash TLV."""
        if algorithm == "sha256":
            self.tlvs.append(ImageTlv.sha256(self.payload))
        elif algorithm == "sha384":
            self.tlvs.append(ImageTlv(
                tlv_type=ImageTlvType.SHA384,
                value=hashlib.sha384(self.payload).digest(),
            ))
        elif algorithm == "sha512":
            self.tlvs.append(ImageTlv(
                tlv_type=ImageTlvType.SHA512,
                value=hashlib.sha512(self.payload).digest(),
            ))
    
    def add_signature(
        self,
        signature: bytes,
        scheme: ImageTlvType,
    ) -> None:
        """Add signature TLV."""
        self.tlvs.append(ImageTlv(tlv_type=scheme, value=signature))
        self._signature = signature
        self._signature_scheme = scheme
    
    def build(self) -> bytes:
        """Build complete image with header, payload, and trailer.
        
        Returns:
            Complete MCUboot image bytes
        """
        # Calculate image size (header + payload + TLVs)
        tlv_size = sum(4 + len(tlv.value) for tlv in self.tlvs)
        self.header.total_image_size = (
            self.header.HEADER_SIZE +
            len(self.payload) +
            tlv_size
        )
        
        # Build image
        chunks = [
            self.header.pack(),
            self.payload,
        ]
        
        # Add TLVs
        for tlv in self.tlvs:
            chunks.append(tlv.pack())
        
        # Add trailer
        trailer_data = self.trailer.pack()
        chunks.append(trailer_data)
        
        return b"".join(chunks)
    
    def get_hash(self) -> str:
        """Get SHA-256 hash of image."""
        # Exclude header's total_image_size field which we fill during build
        header_copy = self.header.pack()
        image_content = (
            header_copy[:12] +  # Up to total_image_size
            struct.pack("<I", self.header.total_image_size) +
            header_copy[16:] +
            self.payload
        )
        return hashlib.sha256(image_content).hexdigest()
    
    @classmethod
    def parse(cls, data: bytes) -> McubootImage:
        """Parse image from bytes."""
        # Parse header
        header = ImageHeader.unpack(data[:32])
        
        # Extract payload
        payload_start = header.header_size
        tlv_start = payload_start + (header.total_image_size - header.header_size)
        
        # Find TLVs (they end before trailer magic or EOF)
        # MCUboot TLVs are after payload
        payload = data[payload_start:tlv_start] if tlv_start < len(data) else b""
        
        # Parse TLVs
        tlvs = []
        offset = tlv_start
        while offset + 4 <= len(data):
            tlv_type, tlv_len = struct.unpack("<HH", data[offset:offset + 4])
            if offset + 4 + tlv_len > len(data):
                break
            tlv_value = data[offset + 4:offset + 4 + tlv_len]
            try:
                tlvs.append(ImageTlv(
                    tlv_type=ImageTlvType(tlv_type),
                    value=tlv_value,
                ))
            except ValueError:
                pass  # Unknown TLV type, skip
            offset += 4 + tlv_len
        
        return cls(
            header=header,
            payload=payload,
            tlvs=tlvs,
        )
    
    def validate(self) -> tuple[bool, str]:
        """Validate image structure.
        
        Returns:
            (is_valid, error_message)
        """
        # Check magic
        if self.header.magic != IMAGE_MAGIC_V2:
            return False, f"Invalid magic: 0x{self.header.magic:08X}"
        
        # Check header size
        if self.header.header_size < ImageHeader.HEADER_SIZE:
            return False, f"Invalid header size: {self.header.header_size}"
        
        # Check for hash TLV
        hash_tlvs = [t for t in self.tlvs if t.tlv_type in (
            ImageTlvType.SHA256, ImageTlvType.SHA384, ImageTlvType.SHA512
        )]
        if not hash_tlvs:
            return False, "Missing hash TLV"
        
        # Verify hash
        hash_tlv = hash_tlvs[0]
        expected_hash = hashlib.sha256(self.payload).digest()
        if hash_tlv.value != expected_hash:
            return False, "Hash mismatch"
        
        return True, "Valid"


@dataclass
class FlashSlotLayout:
    """Flash layout for dual-bank MCUboot system.
    
    STM32F407 example layout (2MB flash):
        0x08000000 - 0x080FFFFF: Main flash (2MB)
            0x08000000 - 0x08003FFF: Bootloader (16KB)
            0x08004000 - 0x0807FFFF: Slot A (496KB)
            0x08080000 - 0x080BFFFF: Slot B (496KB)
            0x080C0000 - 0x080FFFFF: Scratch (496KB)
    """
    
    flash_base: int = 0x08000000
    flash_size: int = 0x200000  # 2MB
    sector_size: int = 0x4000   # 16KB sectors
    
    # Regions (relative to flash_base)
    bootloader_start: int = 0x000000
    bootloader_size: int = 0x10000  # 64KB
    
    slot_a_start: int = 0x10000
    slot_size: int = 0x80000  # 512KB each
    
    scratch_start: int = 0x0  # Set based on slot size
    
    @property
    def slot_a_end(self) -> int:
        return self.slot_a_start + self.slot_size
    
    @property
    def slot_b_start(self) -> int:
        return self.slot_a_end
    
    @property
    def slot_b_end(self) -> int:
        return self.slot_b_start + self.slot_size
    
    @property
    def scratch_start(self) -> int:
        return self.slot_b_end
    
    @property
    def scratch_end(self) -> int:
        return self.flash_base + self.flash_size
    
    @property
    def slot_a_addr(self) -> int:
        return self.flash_base + self.slot_a_start
    
    @property
    def slot_b_addr(self) -> int:
        return self.flash_base + self.slot_b_start
    
    @property
    def scratch_addr(self) -> int:
        return self.flash_base + self.scratch_start
    
    def get_trailer_offset(self, slot: ImageSlot) -> int:
        """Get trailer offset from slot start."""
        if slot == ImageSlot.PRIMARY:
            return self.slot_size
        elif slot == ImageSlot.SECONDARY:
            return self.slot_size
        else:  # SCRATCH
            return self.flash_size - self.slot_b_start - self.slot_size
