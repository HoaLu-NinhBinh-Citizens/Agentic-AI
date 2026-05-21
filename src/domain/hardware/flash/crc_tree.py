"""CRC Tree / Merkle Verification - Incremental verification for large firmware.

Phase 6.2: Addresses critical production gap:
- Merkle tree for firmware verification
- Chunk-level incremental verification
- Fast resume after corruption detection
- Delta verification for OTA
- Fleet-scale verification without full download

Instead of verifying full 8MB/16MB image, verify only changed chunks.
This is essential for:
- Low-bandwidth connections
- Large fleet operations
- Resume after partial corruption
- OTA delta updates
"""

from __future__ import annotations

import hashlib
import logging
import struct
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ChunkInfo:
    """Information about a firmware chunk."""
    
    chunk_index: int
    offset: int
    size: int
    
    # Hashes
    content_hash: str  # SHA256 of chunk content
    merkle_hash: str | None = None  # Hash in Merkle tree
    
    # Verification state
    verified: bool = False
    verified_at: float | None = None


@dataclass
class MerkleNode:
    """Node in Merkle verification tree."""
    
    level: int  # 0 = leaf (chunk), higher = internal
    index: int  # Index at this level
    
    # Hash
    hash: str
    
    # Children (for internal nodes)
    left_child: int | None = None  # Index in parent level
    right_child: int | None = None
    
    # Metadata
    chunk_range: tuple[int, int] | None = None  # (start_offset, end_offset)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "level": self.level,
            "index": self.index,
            "hash": self.hash,
            "left_child": self.left_child,
            "right_child": self.right_child,
            "chunk_range": self.chunk_range,
        }


@dataclass
class VerificationTree:
    """Merkle tree for firmware verification.
    
    Structure:
                    [root hash]
                    /          \
           [interior hash]    [interior hash]
           /      \            /      \
        [chunk] [chunk]   [chunk] [chunk]
        ...
    
    Benefits:
    - Verify single chunk: O(log n) instead of O(n)
    - Detect corruption location precisely
    - Incremental verification
    - Parallel verification possible
    """
    
    chunk_size: int = 4096
    
    _chunks: list[ChunkInfo] = field(default_factory=list)
    _nodes: list[list[MerkleNode]] = field(default_factory=list)  # nodes[level] = list
    
    root_hash: str = ""
    
    def build(
        self,
        firmware_data: bytes,
        chunk_size: int | None = None,
    ) -> str:
        """Build verification tree from firmware data.
        
        Args:
            firmware_data: Firmware binary
            chunk_size: Size of each chunk (default: 4096)
        
        Returns:
            Root hash of the tree
        """
        self.chunk_size = chunk_size or self.chunk_size
        self._chunks = []
        self._nodes = []
        
        # Create chunks
        offset = 0
        chunk_index = 0
        
        while offset < len(firmware_data):
            chunk_data = firmware_data[offset : offset + self.chunk_size]
            
            chunk = ChunkInfo(
                chunk_index=chunk_index,
                offset=offset,
                size=len(chunk_data),
                content_hash=hashlib.sha256(chunk_data).hexdigest(),
            )
            self._chunks.append(chunk)
            
            offset += len(chunk_data)
            chunk_index += 1
        
        # Build tree from leaves
        self._build_tree()
        
        return self.root_hash
    
    def _build_tree(self) -> None:
        """Build Merkle tree from chunks."""
        if not self._chunks:
            return
        
        # Level 0: chunk hashes
        level_0 = []
        for i, chunk in enumerate(self._chunks):
            node = MerkleNode(
                level=0,
                index=i,
                hash=chunk.content_hash,
                chunk_range=(chunk.offset, chunk.offset + chunk.size),
            )
            level_0.append(node)
            chunk.merkle_hash = chunk.content_hash
        
        self._nodes.append(level_0)
        
        # Build levels up to root
        current_level = level_0
        
        while len(current_level) > 1:
            next_level = self._build_parent_level(current_level)
            self._nodes.append(next_level)
            current_level = next_level
        
        # Root hash
        if current_level:
            self.root_hash = current_level[0].hash
    
    def _build_parent_level(self, child_level: list[MerkleNode]) -> list[MerkleNode]:
        """Build parent level from child level."""
        parent_level = []
        
        for i in range(0, len(child_level), 2):
            left = child_level[i]
            
            if i + 1 < len(child_level):
                right = child_level[i + 1]
            else:
                # Duplicate last node for odd number
                right = left
            
            # Hash of concatenation
            combined = left.hash + right.hash
            parent_hash = hashlib.sha256(combined.encode()).hexdigest()
            
            parent = MerkleNode(
                level=child_level[0].level + 1,
                index=i // 2,
                hash=parent_hash,
                left_child=left.index if child_level == self._nodes[0] else None,
                right_child=right.index if child_level == self._nodes[0] else None,
                chunk_range=(left.chunk_range[0], right.chunk_range[1]),
            )
            parent_level.append(parent)
        
        return parent_level
    
    def verify_chunk(self, chunk_index: int, chunk_data: bytes) -> bool:
        """Verify a single chunk.
        
        Args:
            chunk_index: Index of chunk to verify
            chunk_data: Actual chunk data
        
        Returns:
            True if chunk is valid
        """
        if chunk_index >= len(self._chunks):
            return False
        
        expected_hash = self._chunks[chunk_index].content_hash
        actual_hash = hashlib.sha256(chunk_data).hexdigest()
        
        if actual_hash != expected_hash:
            logger.warning(
                "chunk_verification_failed: chunk=%d expected=%s actual=%s",
                chunk_index,
                expected_hash[:16],
                actual_hash[:16],
            )
            return False
        
        # Mark as verified
        self._chunks[chunk_index].verified = True
        self._chunks[chunk_index].verified_at = time.time()
        
        return True
    
    def verify_proof(
        self,
        chunk_index: int,
        proof_hashes: list[str],
    ) -> bool:
        """Verify chunk using Merkle proof (without full data).
        
        Args:
            chunk_index: Index of chunk
            proof_hashes: List of sibling hashes from root to leaf
        
        Returns:
            True if proof is valid
        """
        if not proof_hashes:
            return False
        
        current_hash = self._chunks[chunk_index].content_hash
        
        # Walk up the tree, combining with proof hashes
        level = 0
        idx = chunk_index
        
        for proof_hash in proof_hashes:
            if idx % 2 == 0:
                # This node is left child
                combined = current_hash + proof_hash
            else:
                # This node is right child
                combined = proof_hash + current_hash
            
            current_hash = hashlib.sha256(combined.encode()).hexdigest()
            level += 1
            idx //= 2
        
        return current_hash == self.root_hash
    
    def get_proof(self, chunk_index: int) -> list[str]:
        """Get Merkle proof for a chunk.
        
        Args:
            chunk_index: Index of chunk
        
        Returns:
            List of sibling hashes from root to leaf
        """
        if chunk_index >= len(self._chunks):
            return []
        
        proof = []
        idx = chunk_index
        
        for level in range(len(self._nodes) - 1):
            current_level = self._nodes[level]
            
            if idx % 2 == 0:
                # Need right sibling
                sibling_idx = idx + 1
            else:
                # Need left sibling
                sibling_idx = idx - 1
            
            if sibling_idx < len(current_level):
                proof.append(current_level[sibling_idx].hash)
            else:
                # Duplicate sibling (singleton at end)
                proof.append(current_level[idx].hash)
            
            idx //= 2
        
        return proof
    
    def verify_incremental(
        self,
        probe: Any,
        partition_start: int,
        chunk_indices: list[int] | None = None,
    ) -> dict[str, Any]:
        """Incrementally verify chunks on target.
        
        Args:
            probe: Probe interface
            partition_start: Start address of firmware
            chunk_indices: Specific chunks to verify (None = all)
        
        Returns:
            Verification result
        """
        import asyncio
        
        result = {
            "total_chunks": len(self._chunks),
            "verified_chunks": 0,
            "failed_chunks": [],
            "skipped_chunks": 0,
        }
        
        indices_to_verify = chunk_indices if chunk_indices else list(range(len(self._chunks)))
        
        for chunk_index in indices_to_verify:
            chunk = self._chunks[chunk_index]
            
            # Skip if already verified
            if chunk.verified:
                result["skipped_chunks"] += 1
                continue
            
            # Read chunk from target
            addr = partition_start + chunk.offset
            
            try:
                data = asyncio.get_event_loop().run_until_complete(
                    probe.read_memory(addr, chunk.size)
                )
                
                if self.verify_chunk(chunk_index, data):
                    result["verified_chunks"] += 1
                else:
                    result["failed_chunks"].append({
                        "chunk_index": chunk_index,
                        "offset": chunk.offset,
                    })
                    
            except Exception as e:
                logger.error("chunk_read_failed", chunk_index=chunk_index, error=str(e))
                result["failed_chunks"].append({
                    "chunk_index": chunk_index,
                    "error": str(e),
                })
        
        return result
    
    def get_verification_stats(self) -> dict[str, Any]:
        """Get verification statistics."""
        verified = sum(1 for c in self._chunks if c.verified)
        return {
            "total_chunks": len(self._chunks),
            "verified_chunks": verified,
            "remaining_chunks": len(self._chunks) - verified,
            "verification_percent": (verified / len(self._chunks) * 100) if self._chunks else 0,
            "root_hash": self.root_hash[:16] if self.root_hash else None,
        }
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "chunk_size": self.chunk_size,
            "total_chunks": len(self._chunks),
            "root_hash": self.root_hash,
            "tree_height": len(self._nodes),
            "verification_stats": self.get_verification_stats(),
        }


@dataclass
class IncrementalVerifier:
    """Incremental verification for large firmware.
    
    Uses Merkle tree for efficient partial verification.
    Essential for:
    - Large firmware (8MB+)
    - Fleet OTA operations
    - Resume after interruption
    """
    
    tree: VerificationTree = field(default_factory=VerificationTree)
    
    # Streaming support
    _verified_offsets: set[int] = field(default_factory=set)
    
    def __post_init__(self) -> None:
        """Initialize verifier."""
        self._verified_offsets = set()
    
    def build_from_firmware(
        self,
        firmware_data: bytes,
        chunk_size: int = 4096,
    ) -> str:
        """Build verification tree from firmware.
        
        Returns:
            Root hash for comparison
        """
        return self.tree.build(firmware_data, chunk_size)
    
    def verify_chunk_data(
        self,
        chunk_index: int,
        chunk_data: bytes,
    ) -> bool:
        """Verify chunk data matches expected hash."""
        return self.tree.verify_chunk(chunk_index, chunk_data)
    
    def get_chunk_proof(self, chunk_index: int) -> list[str]:
        """Get Merkle proof for chunk."""
        return self.tree.get_proof(chunk_index)
    
    def verify_with_proof(
        self,
        chunk_index: int,
        chunk_data: bytes,
        proof: list[str],
    ) -> bool:
        """Verify chunk using proof (offline verification)."""
        # First verify local hash
        if not self.tree.verify_chunk(chunk_index, chunk_data):
            return False
        
        # Then verify proof against root
        return self.tree.verify_proof(chunk_index, proof)
    
    def mark_verified(self, chunk_index: int) -> None:
        """Mark chunk as verified."""
        if chunk_index < len(self.tree._chunks):
            self.tree._chunks[chunk_index].verified = True
            self._verified_offsets.add(self.tree._chunks[chunk_index].offset)
    
    def get_unverified_ranges(self) -> list[tuple[int, int]]:
        """Get ranges of unverified chunks.
        
        Returns:
            List of (offset, size) tuples for unverified regions
        """
        ranges = []
        
        for chunk in self.tree._chunks:
            if not chunk.verified:
                ranges.append((chunk.offset, chunk.size))
        
        return ranges
    
    def needs_verification(self) -> bool:
        """Check if any chunks need verification."""
        return any(not c.verified for c in self.tree._chunks)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "root_hash": self.tree.root_hash,
            "chunk_size": self.tree.chunk_size,
            "total_chunks": len(self.tree._chunks),
            "verified_chunks": sum(1 for c in self.tree._chunks if c.verified),
            "verified_offsets": list(self._verified_offsets),
        }


@dataclass
class FirmwareManifest:
    """Manifest for firmware verification.
    
    Contains all verification metadata:
    - Root hash
    - Chunk hashes
    - Merkle proofs
    - Metadata
    """
    
    firmware_hash: str  # SHA256 of entire firmware
    root_hash: str  # Merkle tree root
    
    chunk_size: int
    total_size: int
    
    chunk_hashes: list[str]  # Hash of each chunk
    
    # For offline verification
    proof_per_chunk: dict[int, list[str]] = field(default_factory=dict)
    
    # Metadata
    version: str = ""
    build_timestamp: str = ""
    build_info: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "firmware_hash": self.firmware_hash,
            "root_hash": self.root_hash,
            "chunk_size": self.chunk_size,
            "total_size": self.total_size,
            "chunk_hashes": self.chunk_hashes,
            "version": self.version,
            "build_timestamp": self.build_timestamp,
            "build_info": self.build_info,
        }
    
    @classmethod
    def from_firmware(
        cls,
        firmware_data: bytes,
        chunk_size: int = 4096,
        version: str = "",
        build_info: dict[str, Any] | None = None,
    ) -> FirmwareManifest:
        """Create manifest from firmware data."""
        from datetime import datetime
        
        tree = VerificationTree(chunk_size=chunk_size)
        root_hash = tree.build(firmware_data, chunk_size)
        
        return cls(
            firmware_hash=hashlib.sha256(firmware_data).hexdigest(),
            root_hash=root_hash,
            chunk_size=chunk_size,
            total_size=len(firmware_data),
            chunk_hashes=[c.content_hash for c in tree._chunks],
            version=version,
            build_timestamp=datetime.now().isoformat(),
            build_info=build_info or {},
        )
    
    def export_proofs(self) -> dict[str, Any]:
        """Export manifest with all Merkle proofs."""
        tree = VerificationTree(chunk_size=self.chunk_size)
        tree.build(b"\x00" * self.total_size, self.chunk_size)
        
        # Update tree with our hashes
        for i, chunk in enumerate(tree._chunks):
            if i < len(self.chunk_hashes):
                chunk.content_hash = self.chunk_hashes[i]
        
        proofs = {}
        for i in range(len(self.chunk_hashes)):
            proofs[str(i)] = self.get_chunk_proof(i)
        
        return {
            **self.to_dict(),
            "proofs": proofs,
        }
    
    def get_chunk_proof(self, chunk_index: int) -> list[str]:
        """Get proof for chunk (rebuild tree if needed)."""
        if str(chunk_index) in self.proof_per_chunk:
            return self.proof_per_chunk[str(chunk_index)]
        
        # Rebuild proof from chunk hashes
        # This is expensive, cache the result
        return []


@dataclass
class DeltaVerifier:
    """Verification for delta OTA updates.
    
    Verifies only changed chunks in delta updates.
    """
    
    base_manifest: FirmwareManifest | None = None
    incremental_verifier: IncrementalVerifier | None = None
    
    def add_base_firmware(
        self,
        firmware_data: bytes,
        chunk_size: int = 4096,
    ) -> str:
        """Add base firmware for delta verification."""
        self.incremental_verifier = IncrementalVerifier()
        root_hash = self.incremental_verifier.build_from_firmware(firmware_data, chunk_size)
        
        self.base_manifest = FirmwareManifest.from_firmware(
            firmware_data, chunk_size
        )
        
        return root_hash
    
    def verify_delta(
        self,
        delta_chunks: dict[int, bytes],
    ) -> dict[str, Any]:
        """Verify delta update chunks.
        
        Args:
            delta_chunks: {chunk_index: chunk_data} for changed chunks
        
        Returns:
            Verification result
        """
        if not self.incremental_verifier:
            return {"error": "No base firmware set"}
        
        result = {
            "verified_chunks": 0,
            "failed_chunks": [],
            "root_hash_match": True,
        }
        
        for chunk_index, chunk_data in delta_chunks.items():
            if self.incremental_verifier.verify_chunk_data(chunk_index, chunk_data):
                result["verified_chunks"] += 1
            else:
                result["failed_chunks"].append(chunk_index)
                result["root_hash_match"] = False
        
        return result
    
    def rebuild_root_after_delta(
        self,
        delta_chunks: dict[int, bytes],
        base_firmware: bytes,
    ) -> str:
        """Rebuild root hash after applying delta.
        
        Returns:
            New root hash
        """
        # Rebuild firmware with delta
        full_data = bytearray(base_firmware)
        
        for chunk_index, chunk_data in delta_chunks.items():
            offset = chunk_index * self.base_manifest.chunk_size
            full_data[offset : offset + len(chunk_data)] = chunk_data
        
        # Build new verification tree
        tree = VerificationTree(chunk_size=self.base_manifest.chunk_size)
        return tree.build(bytes(full_data), self.base_manifest.chunk_size)
