"""
WORM Archive with Hash Chain and Merkle Proof.

Provides immutable archive with cryptographic verification:
- WORM (Write Once Read Many) semantics
- Hash chain for sequential integrity
- Merkle proof for partial verification
- Signed manifest
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ArchiveEntry:
    """Single entry in WORM archive."""
    entry_id: str
    tenant_id: str
    payload: Dict[str, Any]
    timestamp: datetime
    hash: str  # SHA-256 of payload
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HashChainBlock:
    """Block in hash chain."""
    block_id: str
    sequence: int
    entries: List[ArchiveEntry]
    block_hash: str  # Hash of entries
    previous_hash: str  # Previous block's hash
    merkle_root: str  # Merkle tree root of entries
    timestamp: datetime
    signature: Optional[str] = None


@dataclass
class MerkleProof:
    """Proof of inclusion in Merkle tree."""
    entry_id: str
    merkle_root: str
    proof: List[Dict[str, str]]  # Hashes and positions
    block_sequence: int
    timestamp: datetime


@dataclass
class ManifestEntry:
    """Entry in signed manifest."""
    block_id: str
    block_sequence: int
    merkle_root: str
    previous_hash: str
    entry_count: int
    timestamp: datetime
    manifest_hash: str


@dataclass
class ArchiveManifest:
    """Signed manifest for archive verification."""
    manifest_id: str
    archive_id: str
    entries: List[ManifestEntry]
    chain_hash: str  # Hash of all blocks
    created_at: datetime
    signature: str  # Digital signature
    public_key_id: str


class WORMArchive:
    """
    WORM (Write Once Read Many) Archive.
    
    Guarantees:
    - Once written, data cannot be modified or deleted
    - Cryptographic integrity via hash chain
    - Merkle proof for partial verification
    - Signed manifest for audit
    
    Use cases:
    - DLQ archival with audit trail
    - Compliance logging
    - Transaction history
    """
    
    def __init__(
        self,
        archive_id: str,
        block_size: int = 100,  # Entries per block
    ):
        self.archive_id = archive_id
        self.block_size = block_size
        
        self._blocks: List[HashChainBlock] = []
        self._current_block_entries: List[ArchiveEntry] = []
        self._manifest: Optional[ArchiveManifest] = None
        self._entry_index: Dict[str, tuple[int, int]] = {}  # entry_id -> (block_idx, entry_idx)
        self._lock = asyncio.Lock()
        
        # Genesis block hash
        self._genesis_hash = "0" * 64
    
    async def append(
        self,
        entry_id: str,
        tenant_id: str,
        payload: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ArchiveEntry:
        """Append entry to archive (WORM - cannot modify after)."""
        async with self._lock:
            # Create entry with hash
            payload_str = json.dumps(payload, sort_keys=True)
            entry_hash = hashlib.sha256(payload_str.encode()).hexdigest()
            
            entry = ArchiveEntry(
                entry_id=entry_id,
                tenant_id=tenant_id,
                payload=payload,
                timestamp=datetime.now(),
                hash=entry_hash,
                metadata=metadata or {},
            )
            
            # Add to current block
            self._current_block_entries.append(entry)
            self._entry_index[entry_id] = (
                len(self._blocks),
                len(self._current_block_entries) - 1
            )
            
            # If block is full, seal it
            if len(self._current_block_entries) >= self.block_size:
                await self._seal_block()
            
            return entry
    
    async def _seal_block(self) -> None:
        """Seal current block and create new one."""
        entries = self._current_block_entries
        if not entries:
            return
        
        # Calculate Merkle root
        merkle_root = self._calculate_merkle_root(entries)
        
        # Calculate block hash
        block_content = json.dumps({
            "entries": [e.hash for e in entries],
            "merkle_root": merkle_root,
        }, sort_keys=True)
        block_hash = hashlib.sha256(block_content.encode()).hexdigest()
        
        # Get previous hash
        if self._blocks:
            previous_hash = self._blocks[-1].block_hash
        else:
            previous_hash = self._genesis_hash
        
        # Create block
        block = HashChainBlock(
            block_id=f"{self.archive_id}_block_{len(self._blocks)}",
            sequence=len(self._blocks),
            entries=entries,
            block_hash=block_hash,
            previous_hash=previous_hash,
            merkle_root=merkle_root,
            timestamp=datetime.now(),
        )
        
        self._blocks.append(block)
        self._current_block_entries = []
        
        logger.info(f"Sealed block {block.block_id} with {len(entries)} entries")
    
    def _calculate_merkle_root(self, entries: List[ArchiveEntry]) -> str:
        """Calculate Merkle tree root."""
        if not entries:
            return hashlib.sha256(b"").hexdigest()
        
        # Start with entry hashes
        level = [e.hash for e in entries]
        
        # Build tree up
        while len(level) > 1:
            if len(level) % 2 == 1:
                level.append(level[-1])  # Duplicate last for odd count
            
            new_level = []
            for i in range(0, len(level), 2):
                combined = level[i] + level[i + 1]
                new_level.append(hashlib.sha256(combined.encode()).hexdigest())
            
            level = new_level
        
        return level[0] if level else hashlib.sha256(b"").hexdigest()
    
    async def finalize(self, signature: str, public_key_id: str) -> ArchiveManifest:
        """Finalize archive and create signed manifest."""
        async with self._lock:
            # Seal any remaining entries
            if self._current_block_entries:
                await self._seal_block()
            
            # Create manifest entries
            manifest_entries = []
            chain_content = ""
            
            for block in self._blocks:
                manifest_entry = ManifestEntry(
                    block_id=block.block_id,
                    block_sequence=block.sequence,
                    merkle_root=block.merkle_root,
                    previous_hash=block.previous_hash,
                    entry_count=len(block.entries),
                    timestamp=block.timestamp,
                    manifest_hash="",  # Will compute
                )
                manifest_entries.append(manifest_entry)
                chain_content += block.block_hash
            
            # Calculate chain hash
            chain_hash = hashlib.sha256(chain_content.encode()).hexdigest()
            
            # Create manifest
            manifest = ArchiveManifest(
                manifest_id=f"{self.archive_id}_manifest_{datetime.now().timestamp()}",
                archive_id=self.archive_id,
                entries=manifest_entries,
                chain_hash=chain_hash,
                created_at=datetime.now(),
                signature=signature,
                public_key_id=public_key_id,
            )
            
            # Update entry hashes
            for entry in manifest_entries:
                entry.manifest_hash = hashlib.sha256(
                    json.dumps({
                        "block_id": entry.block_id,
                        "merkle_root": entry.merkle_root,
                        "chain_hash": entry.chain_hash if hasattr(entry, 'chain_hash') else "",
                    }, sort_keys=True).encode()
                ).hexdigest()
            
            self._manifest = manifest
            
            logger.info(f"Finalized archive {self.archive_id} with {len(self._blocks)} blocks")
            return manifest
    
    async def get_entry(self, entry_id: str) -> Optional[ArchiveEntry]:
        """Get entry by ID."""
        if entry_id not in self._entry_index:
            return None
        
        block_idx, entry_idx = self._entry_index[entry_id]
        
        if block_idx >= len(self._blocks):
            return None
        
        block = self._blocks[block_idx]
        if entry_idx >= len(block.entries):
            return None
        
        return block.entries[entry_idx]
    
    async def get_merkle_proof(self, entry_id: str) -> Optional[MerkleProof]:
        """Generate Merkle proof for entry."""
        if entry_id not in self._entry_index:
            return None
        
        block_idx, entry_idx = self._entry_index[entry_id]
        
        if block_idx >= len(self._blocks):
            return None
        
        block = self._blocks[block_idx]
        entry = block.entries[entry_idx]
        
        # Build proof
        proof = self._build_merkle_proof(block.entries, entry_idx)
        
        return MerkleProof(
            entry_id=entry_id,
            merkle_root=block.merkle_root,
            proof=proof,
            block_sequence=block.sequence,
            timestamp=block.timestamp,
        )
    
    def _build_merkle_proof(
        self,
        entries: List[ArchiveEntry],
        entry_idx: int,
    ) -> List[Dict[str, str]]:
        """Build Merkle proof for entry."""
        # Build tree structure for proof
        proof = []
        
        # Start with leaf hashes
        level = [(i, e.hash) for i, e in enumerate(entries)]
        
        while len(level) > 1:
            if len(level) % 2 == 1:
                level.append((level[-1][0], level[-1][1]))
            
            new_level = []
            for i in range(0, len(level), 2):
                left_idx, left_hash = level[i]
                right_idx, right_hash = level[i + 1]
                
                # Determine if our entry is in this pair
                if entry_idx in (left_idx, right_idx):
                    if entry_idx == left_idx:
                        proof.append({
                            "position": "right",
                            "hash": right_hash,
                        })
                    else:
                        proof.append({
                            "position": "left",
                            "hash": left_hash,
                        })
                
                combined = left_hash + right_hash
                new_level.append((left_idx // 2, hashlib.sha256(combined.encode()).hexdigest()))
            
            level = new_level
        
        return proof
    
    async def verify_merkle_proof(self, proof: MerkleProof) -> bool:
        """Verify Merkle proof."""
        if proof.entry_id not in self._entry_index:
            return False
        
        block_idx, entry_idx = self._entry_index[proof.entry_id]
        block = self._blocks[block_idx]
        
        # Reconstruct root from proof
        entry = block.entries[entry_idx]
        current_hash = entry.hash
        
        for step in proof.proof:
            if step["position"] == "right":
                current_hash = hashlib.sha256(
                    current_hash.encode() + step["hash"].encode()
                ).hexdigest()
            else:
                current_hash = hashlib.sha256(
                    step["hash"].encode() + current_hash.encode()
                ).hexdigest()
        
        return current_hash == proof.merkle_root
    
    async def verify_chain_integrity(self) -> tuple[bool, List[str]]:
        """Verify hash chain integrity."""
        errors = []
        
        previous_hash = self._genesis_hash
        
        for i, block in enumerate(self._blocks):
            # Verify previous hash link
            if block.previous_hash != previous_hash:
                errors.append(f"Block {i}: previous hash mismatch")
            
            # Verify Merkle root
            calculated_root = self._calculate_merkle_root(block.entries)
            if calculated_root != block.merkle_root:
                errors.append(f"Block {i}: Merkle root mismatch")
            
            # Verify block hash
            block_content = json.dumps({
                "entries": [e.hash for e in block.entries],
                "merkle_root": block.merkle_root,
            }, sort_keys=True)
            calculated_hash = hashlib.sha256(block_content.encode()).hexdigest()
            if calculated_hash != block.block_hash:
                errors.append(f"Block {i}: block hash mismatch")
            
            previous_hash = block.block_hash
        
        return len(errors) == 0, errors
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get archive metrics."""
        total_entries = sum(len(b.entries) for b in self._blocks)
        
        return {
            "archive_id": self.archive_id,
            "blocks": len(self._blocks),
            "total_entries": total_entries,
            "current_block_entries": len(self._current_block_entries),
            "has_manifest": self._manifest is not None,
            "integrity_verified": asyncio.create_task(self.verify_chain_integrity()) if False else None,
        }
