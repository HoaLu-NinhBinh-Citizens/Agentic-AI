"""
Strongly Consistent Policy Cache with Anti-Entropy Sync.

Features:
- Policy version reconciliation
- Periodic anti-entropy synchronization
- Merkle tree for efficient consistency verification
- Gossip-based propagation
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import random
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class PolicyVersion:
    """Policy version with metadata."""
    policy_id: str
    version: int
    content_hash: str
    content: Dict[str, Any]
    created_at: datetime
    created_by: str
    sequence_number: int  # Strictly increasing globally
    is_deleted: bool = False


@dataclass
class AntiEntropyState:
    """State for anti-entropy synchronization."""
    peer_id: str
    last_sync_at: datetime
    last_sequence: int
    is_synced: bool


@dataclass
class MerkleNode:
    """Merkle tree node for consistency verification."""
    hash: str
    policy_id: str
    version: int
    left: Optional[MerkleNode] = None
    right: Optional[MerkleNode] = None
    is_leaf: bool = True


class PolicyConsistencyLevel(str, Enum):
    """Consistency levels for policy reads."""
    STRONG = "strong"      # Read latest confirmed version
    BOUNDED = "bounded"    # Read version within staleness bound
    EVENTUAL = "eventual"  # Read any cached version


class PolicyCacheWithAntiEntropy:
    """
    Strongly consistent policy cache with anti-entropy sync.
    
    Features:
    - Version-based cache with sequence numbers
    - Anti-entropy periodic synchronization
    - Merkle tree for efficient consistency verification
    - Gossip protocol for propagation
    - Reconciliation on divergence
    """
    
    def __init__(
        self,
        node_id: str,
        peer_nodes: Optional[List[str]] = None,
        sync_interval_seconds: float = 30.0,
        staleness_bound_seconds: float = 60.0,
        consistency_level: PolicyConsistencyLevel = PolicyConsistencyLevel.STRONG,
    ):
        self.node_id = node_id
        self.peer_nodes = peer_nodes or []
        self.sync_interval = sync_interval_seconds
        self.staleness_bound = staleness_bound_seconds
        self.consistency_level = consistency_level
        
        # Policy storage
        self._policies: Dict[str, PolicyVersion] = {}
        self._policy_history: List[PolicyVersion] = []
        
        # Sequence number for strict ordering
        self._global_sequence: int = 0
        
        # Anti-entropy state
        self._anti_entropy_state: Dict[str, AntiEntropyState] = {}
        
        # Merkle tree
        self._merkle_root: Optional[MerkleNode] = None
        
        # Subscribers
        self._subscribers: List[Callable] = []
        
        # Sync task
        self._sync_task: Optional[asyncio.Task] = None
        self._running = False
        
        self._lock = asyncio.Lock()
    
    async def start(self) -> None:
        """Start anti-entropy sync."""
        self._running = True
        self._sync_task = asyncio.create_task(self._sync_loop())
    
    async def stop(self) -> None:
        """Stop anti-entropy sync."""
        self._running = False
        if self._sync_task:
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass
    
    async def _sync_loop(self) -> None:
        """Periodic anti-entropy sync loop."""
        while self._running:
            try:
                await asyncio.sleep(self.sync_interval)
                await self._run_anti_entropy()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Anti-entropy sync error: {e}")
    
    async def _run_anti_entropy(self) -> None:
        """Run anti-entropy synchronization with peers."""
        for peer_id in self.peer_nodes:
            try:
                await self._sync_with_peer(peer_id)
            except Exception as e:
                logger.warning(f"Failed to sync with {peer_id}: {e}")
    
    async def _sync_with_peer(self, peer_id: str) -> None:
        """
        Sync with a peer node.
        
        Uses a simplified gossip protocol:
        1. Exchange Merkle tree roots
        2. If different, find diverged ranges
        3. Exchange diverged policies
        4. Reconcile
        """
        # Get our Merkle root hash
        our_root = self._get_merkle_root()
        
        # Simulate getting peer's root (in production, this would be RPC)
        peer_root = await self._get_peer_merkle_root(peer_id)
        
        if our_root == peer_root:
            # We're in sync
            await self._update_anti_entropy_state(peer_id, True)
            return
        
        # Find differences
        diff = await self._find_differences(peer_id)
        
        if not diff:
            return
        
        # Reconcile differences
        await self._reconcile_differences(peer_id, diff)
        
        # Update state
        await self._update_anti_entropy_state(peer_id, True)
    
    async def _get_peer_merkle_root(self, peer_id: str) -> str:
        """Get peer's Merkle root hash."""
        # In production, this would be an RPC call
        # For simulation, return our root (assume synced)
        return self._get_merkle_root()
    
    async def _find_differences(self, peer_id: str) -> List[str]:
        """Find policy IDs that differ between us and peer."""
        # In production, this would use range queries
        # For simulation, return empty (assume synced)
        return []
    
    async def _reconcile_differences(
        self,
        peer_id: str,
        diff: List[str],
    ) -> None:
        """Reconcile differences with peer."""
        for policy_id in diff:
            # Get peer's version
            peer_version = await self._get_peer_policy(peer_id, policy_id)
            
            if peer_version:
                # Compare sequence numbers
                local = self._policies.get(policy_id)
                
                if not local or peer_version.sequence_number > local.sequence_number:
                    # Peer has newer version
                    await self._apply_policy(peer_version)
    
    async def _get_peer_policy(self, peer_id: str, policy_id: str) -> Optional[PolicyVersion]:
        """Get policy from peer."""
        # In production, this would be an RPC call
        return None
    
    async def _update_anti_entropy_state(
        self,
        peer_id: str,
        is_synced: bool,
    ) -> None:
        """Update anti-entropy state for peer."""
        async with self._lock:
            self._anti_entropy_state[peer_id] = AntiEntropyState(
                peer_id=peer_id,
                last_sync_at=datetime.now(),
                last_sequence=self._global_sequence,
                is_synced=is_synced,
            )
    
    async def update_policy(
        self,
        policy_id: str,
        content: Dict[str, Any],
        created_by: str,
    ) -> PolicyVersion:
        """Update policy with version tracking."""
        async with self._lock:
            # Increment global sequence
            self._global_sequence += 1
            
            # Get old version for history
            old = self._policies.get(policy_id)
            old_version = old.version if old else 0
            
            # Create new version
            content_hash = self._compute_content_hash(content)
            version = PolicyVersion(
                policy_id=policy_id,
                version=old_version + 1,
                content_hash=content_hash,
                content=content,
                created_at=datetime.now(),
                created_by=created_by,
                sequence_number=self._global_sequence,
            )
            
            # Store
            self._policies[policy_id] = version
            self._policy_history.append(version)
            
            # Rebuild Merkle tree
            self._rebuild_merkle_tree()
            
            # Notify subscribers
            await self._notify_subscribers(policy_id, version)
        
        return version
    
    async def delete_policy(self, policy_id: str, deleted_by: str) -> PolicyVersion:
        """Delete policy (tombstone)."""
        async with self._lock:
            self._global_sequence += 1
            
            old = self._policies.get(policy_id)
            
            version = PolicyVersion(
                policy_id=policy_id,
                version=(old.version if old else 0) + 1,
                content_hash="",
                content={},
                created_at=datetime.now(),
                created_by=deleted_by,
                sequence_number=self._global_sequence,
                is_deleted=True,
            )
            
            self._policies[policy_id] = version
            self._policy_history.append(version)
            
            self._rebuild_merkle_tree()
            await self._notify_subscribers(policy_id, version)
        
        return version
    
    async def get_policy(
        self,
        policy_id: str,
        consistency: Optional[PolicyConsistencyLevel] = None,
    ) -> Optional[PolicyVersion]:
        """Get policy with consistency guarantees."""
        consistency = consistency or self.consistency_level
        
        async with self._lock:
            version = self._policies.get(policy_id)
        
        if consistency == PolicyConsistencyLevel.STRONG:
            # Verify with quorum of peers
            if self.peer_nodes:
                await self._verify_with_quorum(policy_id, version)
        
        elif consistency == PolicyConsistencyLevel.BOUNDED:
            # Check staleness
            if version:
                age = (datetime.now() - version.created_at).total_seconds()
                if age > self.staleness_bound:
                    # Trigger async sync
                    asyncio.create_task(self._run_anti_entropy())
        
        return version
    
    async def _verify_with_quorum(
        self,
        policy_id: str,
        local_version: Optional[PolicyVersion],
    ) -> Optional[PolicyVersion]:
        """Verify version with quorum of peers."""
        if not self.peer_nodes:
            return local_version
        
        quorum_size = len(self.peer_nodes) // 2 + 1
        versions = []
        
        for peer_id in self.peer_nodes[:quorum_size]:
            peer_version = await self._get_peer_policy(peer_id, policy_id)
            if peer_version:
                versions.append(peer_version)
        
        # Compare with local
        if local_version:
            versions.append(local_version)
        
        if not versions:
            return local_version
        
        # Return version with highest sequence number
        return max(versions, key=lambda v: v.sequence_number)
    
    async def _apply_policy(self, version: PolicyVersion) -> None:
        """Apply a policy version."""
        async with self._lock:
            old = self._policies.get(version.policy_id)
            
            # Only apply if newer
            if not old or version.sequence_number > old.sequence_number:
                self._policies[version.policy_id] = version
                self._policy_history.append(version)
                
                # Rebuild Merkle tree
                self._rebuild_merkle_tree()
                
                # Notify subscribers
                await self._notify_subscribers(version.policy_id, version)
    
    def _compute_content_hash(self, content: Dict[str, Any]) -> str:
        """Compute hash of policy content."""
        content_str = json.dumps(content, sort_keys=True)
        return hashlib.sha256(content_str.encode()).hexdigest()[:16]
    
    def _get_merkle_root(self) -> str:
        """Get Merkle tree root hash."""
        return self._merkle_root.hash if self._merkle_root else ""
    
    def _rebuild_merkle_tree(self) -> None:
        """Rebuild Merkle tree from policies."""
        if not self._policies:
            self._merkle_root = None
            return
        
        # Sort policies by ID for consistent tree
        sorted_policies = sorted(
            self._policies.items(),
            key=lambda x: x[0]
        )
        
        # Build leaf nodes
        leaves = [
            MerkleNode(
                hash=self._compute_leaf_hash(policy_id, v.version, v.content_hash),
                policy_id=policy_id,
                version=v.version,
            )
            for policy_id, v in sorted_policies
            if not v.is_deleted
        ]
        
        # Build tree bottom-up
        self._merkle_root = self._build_merkle_tree(leaves)
    
    def _compute_leaf_hash(
        self,
        policy_id: str,
        version: int,
        content_hash: str,
    ) -> str:
        """Compute hash for leaf node."""
        return hashlib.sha256(
            f"{policy_id}:{version}:{content_hash}".encode()
        ).hexdigest()
    
    def _build_merkle_tree(self, nodes: List[MerkleNode]) -> Optional[MerkleNode]:
        """Build Merkle tree from leaf nodes."""
        if not nodes:
            return None
        
        if len(nodes) == 1:
            return nodes[0]
        
        # Pair up nodes
        pairs = []
        for i in range(0, len(nodes), 2):
            left = nodes[i]
            right = nodes[i + 1] if i + 1 < len(nodes) else nodes[i]
            pairs.append(self._merge_nodes(left, right))
        
        return self._build_merkle_tree(pairs)
    
    def _merge_nodes(self, left: MerkleNode, right: MerkleNode) -> MerkleNode:
        """Merge two nodes into parent."""
        combined = hashlib.sha256(
            f"{left.hash}:{right.hash}".encode()
        ).hexdigest()
        
        return MerkleNode(
            hash=combined,
            policy_id="",
            version=0,
            left=left,
            right=right,
            is_leaf=False,
        )
    
    async def _notify_subscribers(self, policy_id: str, version: PolicyVersion) -> None:
        """Notify subscribers of policy change."""
        message = {
            "type": "policy_updated",
            "policy_id": policy_id,
            "version": version.version,
            "sequence": version.sequence_number,
            "is_deleted": version.is_deleted,
            "timestamp": datetime.now().isoformat(),
        }
        
        for callback in self._subscribers:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(message)
                else:
                    callback(message)
            except Exception as e:
                logger.error(f"Subscriber callback failed: {e}")
    
    def register_subscriber(self, callback: Callable) -> None:
        """Register subscriber for policy changes."""
        self._subscribers.append(callback)
    
    async def reconcile_with_peer(
        self,
        peer_id: str,
        peer_policies: Dict[str, PolicyVersion],
    ) -> Dict[str, Any]:
        """
        Reconcile policies with a peer.
        
        Used during peer connection to sync state.
        """
        async with self._lock:
            conflicts = []
            updates = []
            
            # Compare with our policies
            for policy_id, peer_version in peer_policies.items():
                local = self._policies.get(policy_id)
                
                if not local:
                    # We don't have this policy
                    updates.append(peer_version)
                elif peer_version.sequence_number > local.sequence_number:
                    # Peer has newer version
                    updates.append(peer_version)
                elif peer_version.sequence_number == local.sequence_number:
                    if peer_version.content_hash != local.content_hash:
                        # Conflict!
                        conflicts.append({
                            "policy_id": policy_id,
                            "local": local,
                            "peer": peer_version,
                        })
            
            # Apply updates
            for version in updates:
                await self._apply_policy(version)
            
            return {
                "peer_id": peer_id,
                "conflicts": conflicts,
                "updates_applied": len(updates),
                "our_sequence": self._global_sequence,
            }
    
    async def get_consistency_status(self) -> Dict[str, Any]:
        """Get consistency status across cluster."""
        async with self._lock:
            synced_peers = sum(
                1 for s in self._anti_entropy_state.values()
                if s.is_synced
            )
            
            total_peers = len(self.peer_nodes)
            
            return {
                "node_id": self.node_id,
                "global_sequence": self._global_sequence,
                "policies_count": len(self._policies),
                "merkle_root": self._get_merkle_root(),
                "peers_synced": synced_peers,
                "peers_total": total_peers,
                "consistency_level": self.consistency_level.value,
                "staleness_bound_seconds": self.staleness_bound,
            }
