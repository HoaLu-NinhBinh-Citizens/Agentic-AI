"""Replay Optimizer - Phase 5A (v6).

Performance optimization for workflow replay:
- Incremental replay (resume from last processed event)
- Partial replay (replay only affected state)
- State checksum shortcut (skip if state matches)
"""

from __future__ import annotations

import asyncio
import logging
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Optional, List, Callable, Tuple
from enum import Enum

logger = logging.getLogger(__name__)


class ReplayStrategy(str, Enum):
    """Replay strategies for optimization."""
    FULL = "full"           # Replay all events
    INCREMENTAL = "incremental"  # Resume from last processed
    PARTIAL = "partial"     # Replay affected events only
    CHECKSUM = "checksum"    # Use state checksum shortcut


@dataclass
class ReplayCheckpoint:
    """Checkpoint for incremental replay."""
    workflow_id: str
    version: str
    
    # Last processed state
    last_event_sequence: int = 0
    last_state_hash: str = ""
    
    # Snapshot reference
    snapshot_id: Optional[str] = None
    snapshot_sequence: int = 0
    
    # Metadata
    created_at: float = 0
    updated_at: float = 0
    
    def compute_state_hash(self, state: dict) -> str:
        """Compute hash of current state."""
        state_str = json.dumps(state, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(state_str.encode("utf-8")).hexdigest()


@dataclass
class ReplayPlan:
    """Plan for optimized replay."""
    strategy: ReplayStrategy
    
    # Events to replay
    start_sequence: int = 1
    end_sequence: int = 0
    events_to_replay: List[Any] = field(default_factory=list)
    
    # Checkpoint
    use_checkpoint: bool = False
    checkpoint: Optional[ReplayCheckpoint] = None
    
    # Optimization info
    skipped_events: int = 0
    estimated_time_ms: float = 0.0


class ReplayOptimizer:
    """Optimizer for workflow replay performance.
    
    Provides multiple strategies to optimize replay:
    
    1. INCREMENTAL REPLAY:
       - Uses checkpoint to resume from last processed event
       - Only replays new events since checkpoint
       - Requires checkpoint to exist
    
    2. PARTIAL REPLAY:
       - Analyzes which state is affected by events
       - Only replays events affecting current query
       - Requires query-aware event analysis
    
    3. CHECKSUM SHORTCUT:
       - Computes state checksum before replay
       - If state matches checkpoint, skip replay
       - Useful for queries on unchanged workflows
    """
    
    def __init__(
        self,
        event_store: Any = None,
        snapshot_manager: Any = None,
        checkpoint_ttl_seconds: int = 86400,  # 24 hours
    ):
        self._event_store = event_store
        self._snapshot_manager = snapshot_manager
        self._checkpoint_ttl = checkpoint_ttl_seconds
        
        # Checkpoint cache
        self._checkpoints: dict[str, ReplayCheckpoint] = {}
        self._lock = asyncio.Lock()
    
    async def create_checkpoint(
        self,
        workflow_id: str,
        version: str,
        sequence: int,
        state: dict,
        snapshot_id: Optional[str] = None,
    ) -> ReplayCheckpoint:
        """Create a replay checkpoint.
        
        Args:
            workflow_id: Workflow ID.
            version: Workflow code version.
            sequence: Last processed event sequence.
            state: Current workflow state.
            snapshot_id: Optional snapshot ID.
            
        Returns:
            Created checkpoint.
        """

        checkpoint = ReplayCheckpoint(
            workflow_id=workflow_id,
            version=version,
            last_event_sequence=sequence,
            last_state_hash=hashlib.sha256(
                json.dumps(state, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            ).hexdigest(),
            snapshot_id=snapshot_id,
            snapshot_sequence=sequence,
            created_at=0.0,
            updated_at=0.0,
        )
        
        async with self._lock:
            self._checkpoints[workflow_id] = checkpoint
        
        # Persist to store if available
        if self._snapshot_manager:
            await self._snapshot_manager.save_checkpoint(checkpoint)
        
        logger.debug(
            f"Created checkpoint for workflow {workflow_id[:8]}... "
            f"at sequence {sequence}"
        )
        
        return checkpoint
    
    async def get_checkpoint(
        self,
        workflow_id: str,
    ) -> Optional[ReplayCheckpoint]:
        """Get checkpoint for workflow.
        
        Args:
            workflow_id: Workflow ID.
            
        Returns:
            Checkpoint if exists and valid, None otherwise.
        """
        # Check cache
        checkpoint = self._checkpoints.get(workflow_id)
        
        # Check store
        if not checkpoint and self._snapshot_manager:
            checkpoint = await self._snapshot_manager.get_checkpoint(workflow_id)
            if checkpoint:
                self._checkpoints[workflow_id] = checkpoint
        
        # Validate TTL
        if checkpoint:
            if checkpoint.updated_at and (checkpoint.updated_at > 0) and (checkpoint.created_at > 0):
                # TTL only applies to checkpoints created with real wall-clock timestamps
                import time
                if time.time() - checkpoint.updated_at > self._checkpoint_ttl:
                    logger.info(f"Checkpoint expired for workflow {workflow_id[:8]}...")
                    return None
            return checkpoint
        
        return None
    
    async def plan_replay(
        self,
        workflow_id: str,
        version: str,
        current_sequence: int,
        state: dict,
        strategy: ReplayStrategy = ReplayStrategy.INCREMENTAL,
    ) -> ReplayPlan:
        """Plan optimized replay.
        
        Args:
            workflow_id: Workflow ID.
            version: Current workflow version.
            current_sequence: Last event sequence.
            state: Current workflow state.
            strategy: Replay strategy to use.
            
        Returns:
            ReplayPlan with events to replay.
        """
        checkpoint = await self.get_checkpoint(workflow_id)
        
        if strategy == ReplayStrategy.INCREMENTAL:
            return await self._plan_incremental(
                workflow_id, version, current_sequence, state, checkpoint
            )
        elif strategy == ReplayStrategy.CHECKSUM:
            return await self._plan_checksum(
                workflow_id, version, current_sequence, state, checkpoint
            )
        elif strategy == ReplayStrategy.PARTIAL:
            return await self._plan_partial(
                workflow_id, version, current_sequence, state, checkpoint
            )
        else:
            return await self._plan_full(workflow_id, current_sequence)
    
    async def _plan_full(
        self,
        workflow_id: str,
        current_sequence: int,
    ) -> ReplayPlan:
        """Plan full replay."""
        return ReplayPlan(
            strategy=ReplayStrategy.FULL,
            start_sequence=1,
            end_sequence=current_sequence,
            skipped_events=0,
            estimated_time_ms=current_sequence * 0.1,  # 0.1ms per event
        )
    
    async def _plan_incremental(
        self,
        workflow_id: str,
        version: str,
        current_sequence: int,
        state: dict,
        checkpoint: Optional[ReplayCheckpoint],
    ) -> ReplayPlan:
        """Plan incremental replay from checkpoint."""
        if not checkpoint:
            logger.info(f"No checkpoint for workflow {workflow_id[:8]}..., using full replay")
            return await self._plan_full(workflow_id, current_sequence)
        
        # Verify version matches
        if checkpoint.version != version:
            logger.info(
                f"Version mismatch ({checkpoint.version} != {version}), "
                f"using full replay"
            )
            return await self._plan_full(workflow_id, current_sequence)
        
        start_seq = checkpoint.last_event_sequence + 1
        
        return ReplayPlan(
            strategy=ReplayStrategy.INCREMENTAL,
            start_sequence=start_seq,
            end_sequence=current_sequence,
            use_checkpoint=True,
            checkpoint=checkpoint,
            skipped_events=checkpoint.last_event_sequence,
            estimated_time_ms=(current_sequence - start_seq) * 0.1,
        )
    
    async def _plan_checksum(
        self,
        workflow_id: str,
        version: str,
        current_sequence: int,
        state: dict,
        checkpoint: Optional[ReplayCheckpoint],
    ) -> ReplayPlan:
        """Plan replay with checksum shortcut."""
        if not checkpoint:
            return await self._plan_full(workflow_id, current_sequence)
        
        # Compute current state hash
        current_hash = hashlib.sha256(
            json.dumps(state, sort_keys=True).encode()
        ).hexdigest()[:16]
        
        # If hashes match, skip replay entirely
        if current_hash == checkpoint.last_state_hash:
            logger.info(
                f"State unchanged for workflow {workflow_id[:8]}..., "
                f"skipping replay"
            )
            return ReplayPlan(
                strategy=ReplayStrategy.CHECKSUM,
                start_sequence=current_sequence + 1,
                end_sequence=current_sequence,
                use_checkpoint=True,
                checkpoint=checkpoint,
                skipped_events=current_sequence,
                estimated_time_ms=0.0,
            )
        
        # Use incremental replay
        return await self._plan_incremental(
            workflow_id, version, current_sequence, state, checkpoint
        )
    
    async def _plan_partial(
        self,
        workflow_id: str,
        version: str,
        current_sequence: int,
        state: dict,
        checkpoint: Optional[ReplayCheckpoint],
    ) -> ReplayPlan:
        """Plan partial replay for specific state.
        
        This is a simplified implementation. In production,
        this would analyze event types to determine which
        state is affected.
        """
        # For now, fall back to incremental
        return await self._plan_incremental(
            workflow_id, version, current_sequence, state, checkpoint
        )
    
    async def execute_replay(
        self,
        workflow_id: str,
        plan: ReplayPlan,
        state: dict,
        apply_event: Callable[[dict, Any], dict],
    ) -> dict:
        """Execute optimized replay.
        
        Args:
            workflow_id: Workflow ID.
            plan: Replay plan.
            state: Initial state.
            apply_event: Function to apply event to state.
            
        Returns:
            Final state after replay.
        """
        if plan.strategy == ReplayStrategy.CHECKSUM and plan.skipped_events > 0:
            # Shortcut: state unchanged
            logger.info(f"Checksum shortcut: state unchanged for {workflow_id[:8]}...")
            return state
        
        if not plan.events_to_replay:
            # Load events from store
            plan.events_to_replay = await self._load_events(
                workflow_id,
                plan.start_sequence,
                plan.end_sequence,
            )
        
        current_state = state.copy()
        replayed = 0
        
        for event in plan.events_to_replay:
            try:
                current_state = apply_event(current_state, event)
                replayed += 1
            except Exception as e:
                logger.error(
                    f"Error replaying event {event.get('sequence')} "
                    f"for workflow {workflow_id[:8]}...: {e}"
                )
                raise
        
        logger.info(
            f"Replay completed for workflow {workflow_id[:8]}...: "
            f"replayed {replayed} events"
        )
        
        return current_state
    
    async def _load_events(
        self,
        workflow_id: str,
        start_seq: int,
        end_seq: int,
    ) -> List[Any]:
        """Load events from event store."""
        if self._event_store:
            return await self._event_store.get_events_from(
                workflow_id, start_seq, end_seq - start_seq + 1
            )
        return []
    
    async def invalidate_checkpoint(
        self,
        workflow_id: str,
    ) -> None:
        """Invalidate checkpoint for workflow.
        
        Call this when workflow code changes.
        """
        async with self._lock:
            if workflow_id in self._checkpoints:
                del self._checkpoints[workflow_id]
        
        if self._snapshot_manager:
            await self._snapshot_manager.delete_checkpoint(workflow_id)


class StateChecksum:
    """Computes and verifies state checksums for replay optimization."""
    
    @staticmethod
    def compute(state: dict) -> str:
        """Compute checksum of state dict."""
        state_str = json.dumps(state, sort_keys=True, default=str)
        return hashlib.sha256(state_str.encode()).hexdigest()[:32]
    
    @staticmethod
    def verify(state: dict, expected_checksum: str) -> bool:
        """Verify state matches expected checksum."""
        actual = StateChecksum.compute(state)
        return actual == expected_checksum
    
    @staticmethod
    def compute_delta(old_state: dict, new_state: dict) -> dict:
        """Compute delta between two states."""
        all_keys = set(old_state.keys()) | set(new_state.keys())
        delta = {}
        
        for key in all_keys:
            old_val = old_state.get(key)
            new_val = new_state.get(key)
            
            if old_val != new_val:
                delta[key] = {
                    "old": old_val,
                    "new": new_val,
                }
        
        return delta


class PartialReplayAnalyzer:
    """Analyzes events to determine partial replay scope.
    
    In production, this would:
    1. Classify events by affected state
    2. Track state dependencies
    3. Optimize replay for specific queries
    """
    
    # Event types that affect specific state
    STATE_AFFECTING_EVENTS = {
        "activity_completed": ["activity_results", "activity_status"],
        "signal_received": ["signal_history", "signal_handlers"],
        "timer_fired": ["timer_status", "scheduled_actions"],
        "child_completed": ["child_results", "child_status"],
        "state_updated": ["custom_state"],
    }
    
    def get_affected_state_keys(self, event: dict) -> List[str]:
        """Get state keys affected by an event."""
        event_type = event.get("event_type", "")
        return self.STATE_AFFECTING_EVENTS.get(event_type, ["*"])
    
    def filter_events_for_state(
        self,
        events: List[dict],
        state_keys: List[str],
    ) -> List[dict]:
        """Filter events that affect specific state keys."""
        if "*" in state_keys:
            return events
        
        filtered = []
        for event in events:
            affected = self.get_affected_state_keys(event)
            if any(k in state_keys or k == "*" for k in affected):
                filtered.append(event)
        
        return filtered
