"""Version Patcher - Phase 5A (v6).

Replay-safe code upgrade support.
Provides get_version() and patched() for safe workflow code upgrades.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class PatchMarker:
    """Event marker for version patching (get_version/patched).
    
    When workflow code uses ctx.get_version() or ctx.patched(),
    a PatchMarker event is recorded to track which version
    was used during replay.
    """
    patch_id: str
    workflow_id: str
    
    # Created during original execution
    created_event_id: str = ""
    created_sequence: int = 0
    
    # Version info
    version: int = 1
    is_replay: bool = False
    
    # Metadata
    created_at: float = field(default_factory=time.time)


class VersionPatcher:
    """Version patching for replay-safe code upgrades.
    
    Temporal-style versioning API:
    - get_version(change_id, min_version, max_version)
    - patched(feature_id)
    
    During REPLAY:
    - Returns the version that was used when events were created
    - Ensures identical command sequence as original execution
    
    During NEW execution:
    - Returns max_version (the current code version)
    """
    
    def __init__(self, event_store: Any = None):
        self._event_store = event_store
        
        # Cache for version lookups
        self._version_cache: dict[str, PatchMarker] = {}
        self._cache_lock = asyncio.Lock()
        
        # Version history per workflow
        self._workflow_patches: dict[str, list[PatchMarker]] = {}
    
    def get_version(
        self,
        workflow_id: str,
        change_id: str,
        min_version: int,
        max_version: Optional[int] = None,
        is_replay: bool = False,
    ) -> int:
        """Get version of a code change for replay-safe upgrades.
        
        This is the KEY method for safe workflow code upgrades.
        
        Args:
            workflow_id: Workflow ID.
            change_id: Unique identifier for this change.
                Use descriptive names like "pricing-update-v2".
            min_version: Minimum supported version (default behavior).
            max_version: Maximum version (current code). Defaults to min_version.
            is_replay: Whether this is a replay.
            
        Returns:
            Version number based on event history.
        
        Example:
            # In workflow code:
            version = ctx.get_version("pricing-update", min_version=1, max_version=2)
            if version >= 2:
                price = await ctx.execute_activity("get_price_v2", {})
            else:
                price = await ctx.execute_activity("get_price", {})
        """
        if max_version is None:
            max_version = min_version
        
        # During replay, check event history for patch marker
        if is_replay:
            cached_marker = self._version_cache.get(f"{workflow_id}:{change_id}")
            if cached_marker:
                return cached_marker.version
            
            # Look up in event store
            marker = self._lookup_patch_marker(workflow_id, change_id)
            if marker:
                self._version_cache[f"{workflow_id}:{change_id}"] = marker
                return marker.version
            
            # Fallback to min_version during replay if no marker found
            return min_version
        
        # During new execution, return max_version
        return max_version
    
    def patched(
        self,
        workflow_id: str,
        feature_id: str,
        is_replay: bool = False,
    ) -> bool:
        """Check if a feature patch is active.
        
        Simpler version of get_version() for boolean features.
        
        Args:
            workflow_id: Workflow ID.
            feature_id: Unique identifier for the feature.
            is_replay: Whether this is a replay.
            
        Returns:
            True if patch should be applied, False for replay fallback.
        
        Example:
            if ctx.patched("new-shipping-logic"):
                result = await ctx.execute_activity("ship_v2", input)
            else:
                result = await ctx.execute_activity("ship_v1", input)
        """
        version = self.get_version(
            workflow_id,
            feature_id,
            min_version=1,
            max_version=1,
            is_replay=is_replay,
        )
        return version >= 1
    
    def record_patch_marker(
        self,
        workflow_id: str,
        change_id: str,
        version: int,
        event_id: str = "",
        sequence: int = 0,
    ) -> PatchMarker:
        """Record a patch marker event.
        
        Called during workflow execution when get_version() or patched()
        is called to record the version used.
        
        Args:
            workflow_id: Workflow ID.
            change_id: Change identifier.
            version: Version used.
            event_id: Event ID that triggered this marker.
            sequence: Event sequence number.
            
        Returns:
            Created PatchMarker.
        """
        marker = PatchMarker(
            patch_id=change_id,
            workflow_id=workflow_id,
            created_event_id=event_id,
            created_sequence=sequence,
            version=version,
            is_replay=False,
        )
        
        # Cache locally
        self._version_cache[f"{workflow_id}:{change_id}"] = marker
        
        # Track in workflow history
        if workflow_id not in self._workflow_patches:
            self._workflow_patches[workflow_id] = []
        self._workflow_patches[workflow_id].append(marker)
        
        logger.debug(
            f"Recorded patch marker: {change_id}={version} "
            f"for workflow {workflow_id[:8]}..."
        )
        
        return marker
    
    def _lookup_patch_marker(
        self,
        workflow_id: str,
        change_id: str,
    ) -> Optional[PatchMarker]:
        """Look up patch marker in event store.
        
        Args:
            workflow_id: Workflow ID.
            change_id: Change identifier.
            
        Returns:
            PatchMarker if found, None otherwise.
        """
        # Check local cache first
        cached = self._version_cache.get(f"{workflow_id}:{change_id}")
        if cached:
            return cached
        
        # Check workflow history
        if workflow_id in self._workflow_patches:
            for marker in self._workflow_patches[workflow_id]:
                if marker.patch_id == change_id:
                    return marker
        
        # Check event store
        if self._event_store:
            return self._event_store.get_patch_marker(workflow_id, change_id)
        
        return None
    
    def get_workflow_patches(
        self,
        workflow_id: str,
    ) -> list[PatchMarker]:
        """Get all patch markers for a workflow.
        
        Args:
            workflow_id: Workflow ID.
            
        Returns:
            List of patch markers.
        """
        return self._workflow_patches.get(workflow_id, []).copy()
    
    def clear_workflow_cache(self, workflow_id: str) -> None:
        """Clear cached versions for a workflow.
        
        Called when workflow completes to free memory.
        
        Args:
            workflow_id: Workflow ID.
        """
        # Clear cache entries for this workflow
        keys_to_remove = [
            key for key in self._version_cache
            if key.startswith(f"{workflow_id}:")
        ]
        for key in keys_to_remove:
            del self._version_cache[key]
        
        # Clear workflow patches
        if workflow_id in self._workflow_patches:
            del self._workflow_patches[workflow_id]
    
    async def migrate_workflow_patches(
        self,
        workflow_id: str,
        change_id: str,
        old_version: int,
        new_version: int,
    ) -> bool:
        """Migrate a workflow's patch to a new version.
        
        This can be used to upgrade workflows to new code versions
        while maintaining replay compatibility.
        
        Args:
            workflow_id: Workflow ID.
            change_id: Change identifier.
            old_version: Old version.
            new_version: New version.
            
        Returns:
            True if migration succeeded.
        """
        # Find existing marker
        marker = self._lookup_patch_marker(workflow_id, change_id)
        if not marker:
            return False
        
        # Update version
        marker.version = new_version
        self._version_cache[f"{workflow_id}:{change_id}"] = marker
        
        logger.info(
            f"Migrated patch {change_id} from v{old_version} to v{new_version} "
            f"for workflow {workflow_id[:8]}..."
        )
        
        return True


class VersionedCodeChange:
    """Helper class for defining versioned code changes.
    
    Example:
        pricing_change = VersionedCodeChange(
            change_id="pricing-v2",
            min_version=1,
            max_version=2,
            description="New pricing logic",
        )
        
        async def my_workflow(ctx):
            version = ctx.get_version(pricing_change.change_id, ...)
    """
    
    def __init__(
        self,
        change_id: str,
        min_version: int,
        max_version: Optional[int] = None,
        description: str = "",
    ):
        self.change_id = change_id
        self.min_version = min_version
        self.max_version = max_version or min_version
        self.description = description
    
    def get_version(
        self,
        workflow_id: str,
        patcher: VersionPatcher,
        is_replay: bool = False,
    ) -> int:
        """Get version using this change's configuration."""
        return patcher.get_version(
            workflow_id,
            self.change_id,
            self.min_version,
            self.max_version,
            is_replay,
        )
    
    def is_patched(
        self,
        workflow_id: str,
        patcher: VersionPatcher,
        is_replay: bool = False,
    ) -> bool:
        """Check if this change is patched."""
        return self.get_version(workflow_id, patcher, is_replay) >= self.min_version


class PatchDecision:
    """Represents a decision made based on version patching.
    
    Tracks which code path was taken for debugging.
    """
    
    def __init__(
        self,
        change_id: str,
        version: int,
        decision: str,
    ):
        self.change_id = change_id
        self.version = version
        self.decision = decision
        self.timestamp = time.time()
    
    def __repr__(self) -> str:
        return (
            f"PatchDecision(change_id={self.change_id}, "
            f"version={self.version}, decision={self.decision})"
        )
