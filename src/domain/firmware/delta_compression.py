"""Delta Compression - Binary diff for firmware updates.

Provides:
- Binary diff using bsdiff
- Incremental firmware updates
- Delta verification
- Apply on embedded device

Usage:
    delta = DeltaCompressor()
    patch = await delta.create_delta(old_firmware, new_firmware)
    applied = await delta.apply_delta(old_firmware, patch)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import struct
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import BinaryIO

logger = logging.getLogger(__name__)

# Try to import bsdiff
try:
    import bsdiff4
    HAS_BSDIFF = True
except ImportError:
    HAS_BSDIFF = False
    logger.warning("bsdiff4 not installed, using fallback delta")


class DeltaAlgorithm(Enum):
    """Delta compression algorithms."""
    BSDIFF = "bsdiff"
    BSDIFF4 = "bsdiff4"
    CURCMD = "curcmd"
    RAW = "raw"


@dataclass
class DeltaMetadata:
    """Metadata for delta patch."""
    algorithm: str
    old_size: int
    new_size: int
    patch_size: int
    compression_ratio: float
    old_hash: str
    new_hash: str
    created_at: str
    version: str = "1.0"
    
    def to_dict(self) -> dict:
        return {
            "algorithm": self.algorithm,
            "old_size": self.old_size,
            "new_size": self.new_size,
            "patch_size": self.patch_size,
            "compression_ratio": self.compression_ratio,
            "old_hash": self.old_hash,
            "new_hash": self.new_hash,
            "created_at": self.created_at,
            "version": self.version,
        }
    
    def to_bytes(self) -> bytes:
        return json.dumps(self.to_dict()).encode()
    
    @classmethod
    def from_bytes(cls, data: bytes) -> "DeltaMetadata":
        d = json.loads(data.decode())
        return cls(**d)


@dataclass
class DeltaPatch:
    """Delta patch with metadata and data."""
    metadata: DeltaMetadata
    patch_data: bytes
    
    def to_bytes(self) -> bytes:
        """Serialize patch to bytes.
        
        Format:
        - 4 bytes: metadata length (little-endian)
        - metadata JSON
        - patch data
        """
        meta_bytes = self.metadata.to_bytes()
        meta_len = struct.pack("<I", len(meta_bytes))
        return meta_len + meta_bytes + self.patch_data
    
    @classmethod
    def from_bytes(cls, data: bytes) -> "DeltaPatch":
        """Deserialize patch from bytes."""
        meta_len = struct.unpack("<I", data[:4])[0]
        meta_bytes = data[4 : 4 + meta_len]
        patch_data = data[4 + meta_len :]
        
        metadata = DeltaMetadata.from_bytes(meta_bytes)
        return cls(metadata=metadata, patch_data=patch_data)
    
    @property
    def total_size(self) -> int:
        return len(self.to_bytes())


@dataclass 
class DeltaStats:
    """Delta compression statistics."""
    old_size: int = 0
    new_size: int = 0
    patch_size: int = 0
    compression_ratio: float = 0.0
    processing_time_ms: float = 0.0
    algorithm: str = "unknown"


class FallbackBinaryDiff:
    """Fallback diff when bsdiff not available.
    
    Uses simple byte-level diff with RLE compression.
    Not as efficient as bsdiff but works without dependencies.
    """
    
    def diff(self, old: bytes, new: bytes) -> bytes:
        """Create binary diff."""
        import io
        
        operations = []
        old_pos = 0
        new_pos = 0
        
        while new_pos < len(new):
            # Find longest match
            match_len = 0
            best_old_pos = -1
            
            # Limit search window for performance
            search_start = max(0, old_pos - 4096)
            search_end = min(len(old), old_pos + 4096)
            
            for i in range(search_start, search_end):
                if old[i] == new[new_pos]:
                    # Count consecutive matches
                    j = i
                    k = new_pos
                    while j < len(old) and k < len(new) and old[j] == new[k]:
                        j += 1
                        k += 1
                        if k - new_pos > match_len:
                            match_len = k - new_pos
                            best_old_pos = i
            
            if match_len >= 4:
                # Emit COPY operation
                operations.append(("COPY", best_old_pos, match_len))
                old_pos = best_old_pos + match_len
                new_pos += match_len
            else:
                # Emit ADD for new bytes
                add_start = new_pos
                add_len = 1
                new_pos += 1
                
                # Extend ADD if not matching anything in old
                while new_pos < len(new):
                    is_match = False
                    for i in range(search_start, search_end):
                        if new_pos < len(new) and old[i] == new[new_pos]:
                            is_match = True
                            break
                    if not is_match:
                        add_len += 1
                        new_pos += 1
                    else:
                        break
                
                if add_len > 0:
                    operations.append(("ADD", add_start, add_len))
        
        # Serialize operations
        result = io.BytesIO()
        
        for op, pos, length in operations:
            if op == "COPY":
                result.write(struct.pack("<BII", 0, pos, length))
            else:  # ADD
                result.write(struct.pack("<BI", 1, length))
                result.write(new[pos : pos + length])
        
        return result.getvalue()
    
    def patch(self, old: bytes, diff: bytes) -> bytes:
        """Apply binary diff to old data."""
        import io
        
        result = io.BytesIO(old)
        pos = 0
        
        while pos < len(diff):
            op = diff[pos]
            pos += 1
            
            if op == 0:
                # COPY
                old_pos, length = struct.unpack("<II", diff[pos : pos + 8])
                pos += 8
                result.write(old[old_pos : old_pos + length])
            else:
                # ADD
                length = struct.unpack("<I", diff[pos : pos + 4])[0]
                pos += 4
                result.write(diff[pos : pos + length])
                pos += length
        
        return result.getvalue()


class DeltaCompressor:
    """Delta compression for firmware updates.
    
    Creates and applies binary patches to minimize OTA update size.
    """
    
    def __init__(
        self,
        algorithm: DeltaAlgorithm = DeltaAlgorithm.BSDIFF4,
        max_patch_size_ratio: float = 1.0,
    ):
        """
        Args:
            algorithm: Delta algorithm to use
            max_patch_size_ratio: Max patch size relative to new firmware
        """
        self._algorithm = algorithm
        self._max_patch_size_ratio = max_patch_size_ratio
        self._stats = DeltaStats()
        
        if not HAS_BSDIFF and algorithm == DeltaAlgorithm.BSDIFF4:
            logger.warning("bsdiff4 not available, using fallback")
            self._fallback = FallbackBinaryDiff()
        else:
            self._fallback = None
    
    async def create_delta(
        self,
        old_firmware: bytes,
        new_firmware: bytes,
    ) -> DeltaPatch:
        """Create delta patch from old to new firmware.
        
        Args:
            old_firmware: Original firmware bytes
            new_firmware: Updated firmware bytes
            
        Returns:
            DeltaPatch containing metadata and binary diff
        """
        import time
        start_time = time.time()
        
        old_hash = hashlib.sha256(old_firmware).hexdigest()
        new_hash = hashlib.sha256(new_firmware).hexdigest()
        
        # Check if diff is beneficial
        if len(new_firmware) <= len(old_firmware):
            # Same size or smaller, might not need delta
            if hashlib.sha256(old_firmware).digest() == hashlib.sha256(new_firmware).digest():
                logger.info("firmware_identical_no_patch_needed")
                # Return empty patch with raw data marker
                patch_data = new_firmware
            else:
                # Use forward delta
                patch_data = await self._create_diff(old_firmware, new_firmware)
        else:
            patch_data = await self._create_diff(old_firmware, new_firmware)
        
        # Check patch size
        if len(patch_data) > len(new_firmware) * self._max_patch_size_ratio:
            logger.warning(
                "delta_not_beneficial_using_raw",
                patch_size=len(patch_data),
                new_size=len(new_firmware),
            )
            patch_data = new_firmware
        
        elapsed_ms = (time.time() - start_time) * 1000
        
        metadata = DeltaMetadata(
            algorithm=self._algorithm.value,
            old_size=len(old_firmware),
            new_size=len(new_firmware),
            patch_size=len(patch_data),
            compression_ratio=len(patch_data) / max(1, len(new_firmware)),
            old_hash=old_hash,
            new_hash=new_hash,
            created_at=datetime.now().isoformat(),
        )
        
        self._stats = DeltaStats(
            old_size=len(old_firmware),
            new_size=len(new_firmware),
            patch_size=len(patch_data),
            compression_ratio=metadata.compression_ratio,
            processing_time_ms=elapsed_ms,
            algorithm=self._algorithm.value,
        )
        
        logger.info(
            "delta_created",
            old_size=len(old_firmware),
            new_size=len(new_firmware),
            patch_size=len(patch_data),
            compression_ratio=f"{metadata.compression_ratio:.2%}",
            time_ms=f"{elapsed_ms:.1f}",
        )
        
        return DeltaPatch(metadata=metadata, patch_data=patch_data)
    
    async def _create_diff(self, old: bytes, new: bytes) -> bytes:
        """Create binary diff."""
        if HAS_BSDIFF:
            return bsdiff4.diff(old, new)
        else:
            return self._fallback.diff(old, new)
    
    async def apply_delta(
        self,
        old_firmware: bytes,
        patch: DeltaPatch,
    ) -> tuple[bytes, bool]:
        """Apply delta patch to old firmware.
        
        Args:
            old_firmware: Original firmware bytes
            patch: Delta patch to apply
            
        Returns:
            (reconstructed_firmware, is_valid)
        """
        # Verify hashes
        old_hash = hashlib.sha256(old_firmware).hexdigest()
        if old_hash != patch.metadata.old_hash:
            logger.error("old_hash_mismatch", expected=patch.metadata.old_hash, actual=old_hash)
            return b"", False
        
        # Apply patch
        try:
            if patch.metadata.algorithm == "raw" or patch.patch_data == patch.metadata.new_firmware if hasattr(patch.metadata, 'new_firmware') else len(patch.patch_data) == patch.metadata.new_size:
                # Raw data (same size or larger)
                new_firmware = patch.patch_data
            else:
                # Apply binary diff
                if HAS_BSDIFF:
                    new_firmware = bsdiff4.patch(old_firmware, patch.patch_data)
                else:
                    new_firmware = self._fallback.patch(old_firmware, patch.patch_data)
            
            # Verify new hash
            new_hash = hashlib.sha256(new_firmware).hexdigest()
            is_valid = new_hash == patch.metadata.new_hash
            
            if not is_valid:
                logger.error(
                    "patch_apply_hash_mismatch",
                    expected=patch.metadata.new_hash,
                    actual=new_hash,
                )
                return b"", False
            
            logger.info("patch_applied_successfully", size=len(new_firmware))
            return new_firmware, True
            
        except Exception as e:
            logger.error("patch_apply_failed", error=str(e))
            return b"", False
    
    def verify_delta(self, old_firmware: bytes, patch: DeltaPatch) -> bool:
        """Verify delta without applying.
        
        Args:
            old_firmware: Original firmware
            patch: Delta patch
            
        Returns:
            True if delta is valid
        """
        old_hash = hashlib.sha256(old_firmware).hexdigest()
        return old_hash == patch.metadata.old_hash
    
    def estimate_patch_size(self, old_size: int, new_size: int) -> int:
        """Estimate patch size without creating it.
        
        Uses empirical ratio based on typical firmware changes.
        """
        # Typical compression ratio for embedded firmware
        if abs(old_size - new_size) < 1024:
            # Small changes - high compression
            return int(min(old_size, new_size) * 0.1)
        else:
            # Significant changes
            return int((old_size + new_size) * 0.3)


class DeltaBuilder:
    """Build delta patches for multiple firmware versions.
    
    Useful for fleet management with different firmware versions.
    """
    
    def __init__(self, compressor: DeltaCompressor | None = None):
        self._compressor = compressor or DeltaCompressor()
        self._firmware_index: dict[str, bytes] = {}
        self._patch_cache: dict[str, DeltaPatch] = {}
    
    def add_firmware(self, version: str, firmware: bytes) -> None:
        """Add firmware version to index."""
        self._firmware_index[version] = firmware
        logger.info("firmware_added", version=version, size=len(firmware))
    
    async def build_patches_for_version(
        self,
        target_version: str,
        target_firmware: bytes,
    ) -> dict[str, DeltaPatch]:
        """Build delta patches from all known versions to target.
        
        Returns:
            Dict mapping source version to delta patch
        """
        patches = {}
        target_hash = hashlib.sha256(target_firmware).hexdigest()
        
        for source_version, source_firmware in self._firmware_index.items():
            if source_version == target_version:
                continue
            
            patch = await self._compressor.create_delta(source_firmware, target_firmware)
            patches[source_version] = patch
            
            logger.info(
                "patch_built",
                from_version=source_version,
                to_version=target_version,
                patch_size=patch.metadata.patch_size,
            )
        
        return patches
    
    def get_optimal_patch_path(
        self,
        current_version: str,
        target_version: str,
        available_patches: dict[str, DeltaPatch],
    ) -> list[str]:
        """Find optimal path of patches to reach target version.
        
        Uses BFS to find shortest upgrade path.
        """
        if current_version == target_version:
            return []
        
        # Build graph
        versions = list(self._firmware_index.keys()) + [target_version]
        edges: dict[str, list[str]] = {v: [] for v in versions}
        
        for source, patch in available_patches.items():
            if patch.metadata.new_hash == hashlib.sha256(self._firmware_index.get(target_version, b"")).hexdigest():
                edges[source].append(target_version)
        
        # BFS
        from collections import deque
        queue = deque([(current_version, [current_version])])
        visited = {current_version}
        
        while queue:
            current, path = queue.popleft()
            
            if current == target_version:
                return path[1:]
            
            for next_ver in edges.get(current, []):
                if next_ver not in visited:
                    visited.add(next_ver)
                    queue.append((next_ver, path + [next_ver]))
        
        return []


# Utility functions

def extract_delta_from_file(path: Path) -> DeltaPatch:
    """Extract delta patch from file."""
    with open(path, "rb") as f:
        data = f.read()
    return DeltaPatch.from_bytes(data)


def save_delta_to_file(patch: DeltaPatch, path: Path) -> None:
    """Save delta patch to file."""
    with open(path, "wb") as f:
        f.write(patch.to_bytes())
    logger.info("delta_saved", path=str(path), size=patch.total_size)


if __name__ == "__main__":
    print("Delta Compression for Firmware")
    print("=" * 40)
    print("Binary diff for efficient OTA updates")
    print()
    
    # Example usage
    import asyncio
    
    async def demo():
        compressor = DeltaCompressor()
        
        # Simulate firmware versions
        old = b"A" * 10000 + b"OLD_FIRMWARE" + b"B" * 10000
        new = b"A" * 10000 + b"NEW_FIRMWARE" + b"B" * 10000
        
        # Create delta
        patch = await compressor.create_delta(old, new)
        print(f"Old size: {patch.metadata.old_size}")
        print(f"New size: {patch.metadata.new_size}")
        print(f"Patch size: {patch.metadata.patch_size}")
        print(f"Compression: {patch.metadata.compression_ratio:.1%}")
        
        # Apply patch
        reconstructed, valid = await compressor.apply_delta(old, patch)
        print(f"Apply valid: {valid}")
        print(f"Match: {reconstructed == new}")
    
    asyncio.run(demo())
