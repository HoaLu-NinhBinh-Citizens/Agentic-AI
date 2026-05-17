"""Planner determinism versioning - Phase 5B v10.

Implements planner determinism versioning:
- PlannerArtifacts: Snapshot of planning artifacts
- DeterminismVersionManager: Manages version tracking
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class PlannerArtifacts:
    """Snapshot of planning artifacts for reproducibility.
    
    Captures all inputs that affect planning to ensure
    deterministic replay.
    """
    plan_id: str
    planner_model_version: str
    rule_set_version: str
    prompt_hash: str
    prompt_template: str
    temperature: float
    max_tokens: int
    retrieval_snapshot_id: str
    retrieval_snapshot_hash: str
    retrieved_plans: list[str]
    context_hash: str
    created_at: int = field(default_factory=lambda: int(time.time()))


@dataclass
class DeterminismCheckResult:
    """Result of determinism verification."""
    matches: bool
    plan_id: str
    expected_artifacts: Optional[PlannerArtifacts]
    actual_artifacts: Optional[PlannerArtifacts]
    mismatches: list[str] = field(default_factory=list)


class DeterminismVersionManager:
    """Manages planner determinism versioning.
    
    Tracks all artifacts that affect planning to ensure
    deterministic replay.
    """
    
    def __init__(
        self,
        store: Optional[dict] = None,
        enforce_on_replay: bool = True,
    ):
        self._store = store or {}
        self._enforce = enforce_on_replay
    
    def compute_prompt_hash(self, prompt: str) -> str:
        """Compute hash of a prompt.
        
        Args:
            prompt: Prompt text
            
        Returns:
            SHA256 hash
        """
        return hashlib.sha256(prompt.encode()).hexdigest()
    
    def compute_context_hash(self, context: dict) -> str:
        """Compute hash of planning context.
        
        Args:
            context: Planning context
            
        Returns:
            Hash of context
        """
        import json
        content = json.dumps(context, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()
    
    def capture_artifacts(
        self,
        plan_id: str,
        model_version: str,
        rule_set_version: str,
        prompt_template: str,
        prompt: str,
        temperature: float,
        max_tokens: int,
        retrieved_plans: list[str],
        context: dict,
    ) -> PlannerArtifacts:
        """Capture planning artifacts.
        
        Args:
            plan_id: Plan identifier
            model_version: Model version used
            rule_set_version: Rule set version
            prompt_template: Prompt template
            prompt: Actual prompt used
            temperature: Temperature setting
            max_tokens: Max tokens setting
            retrieved_plans: Retrieved plan IDs
            context: Planning context
            
        Returns:
            Captured artifacts
        """
        prompt_hash = self.compute_prompt_hash(prompt)
        context_hash = self.compute_context_hash(context)
        
        retrieval_snapshot = sorted(retrieved_plans)
        retrieval_hash = hashlib.sha256(
            "".join(retrieval_snapshot).encode()
        ).hexdigest()
        
        artifacts = PlannerArtifacts(
            plan_id=plan_id,
            planner_model_version=model_version,
            rule_set_version=rule_set_version,
            prompt_hash=prompt_hash,
            prompt_template=prompt_template,
            temperature=temperature,
            max_tokens=max_tokens,
            retrieval_snapshot_id=",".join(retrieval_snapshot),
            retrieval_snapshot_hash=retrieval_hash,
            retrieved_plans=retrieved_plans,
            context_hash=context_hash,
        )
        
        self._store[plan_id] = artifacts
        
        return artifacts
    
    def get_artifacts(self, plan_id: str) -> Optional[PlannerArtifacts]:
        """Get artifacts for a plan.
        
        Args:
            plan_id: Plan identifier
            
        Returns:
            Artifacts or None
        """
        return self._store.get(plan_id)
    
    def verify_determinism(
        self,
        plan_id: str,
        current_model_version: str,
        current_rule_set_version: str,
        current_prompt: str,
        current_temperature: float,
        current_retrieved_plans: list[str],
        current_context: dict,
    ) -> DeterminismCheckResult:
        """Verify that replay would be deterministic.
        
        Args:
            plan_id: Plan identifier
            current_model_version: Current model version
            current_rule_set_version: Current rule set version
            current_prompt: Current prompt
            current_temperature: Current temperature
            current_retrieved_plans: Currently retrieved plans
            current_context: Current context
            
        Returns:
            Determinism check result
        """
        artifacts = self._store.get(plan_id)
        
        if not artifacts:
            return DeterminismCheckResult(
                matches=False,
                plan_id=plan_id,
                expected_artifacts=None,
                actual_artifacts=None,
                mismatches=["No artifacts found for plan"],
            )
        
        mismatches = []
        
        if artifacts.planner_model_version != current_model_version:
            mismatches.append(
                f"Model version mismatch: expected {artifacts.planner_model_version}, "
                f"got {current_model_version}"
            )
        
        if artifacts.rule_set_version != current_rule_set_version:
            mismatches.append(
                f"Rule set version mismatch: expected {artifacts.rule_set_version}, "
                f"got {current_rule_set_version}"
            )
        
        current_prompt_hash = self.compute_prompt_hash(current_prompt)
        if artifacts.prompt_hash != current_prompt_hash:
            mismatches.append(
                f"Prompt mismatch: expected {artifacts.prompt_hash}, "
                f"got {current_prompt_hash}"
            )
        
        if artifacts.temperature != current_temperature:
            mismatches.append(
                f"Temperature mismatch: expected {artifacts.temperature}, "
                f"got {current_temperature}"
            )
        
        current_retrieval_hash = hashlib.sha256(
            "".join(sorted(current_retrieved_plans)).encode()
        ).hexdigest()
        if artifacts.retrieval_snapshot_hash != current_retrieval_hash:
            mismatches.append(
                "Retrieval snapshot mismatch: retrieved plans have changed"
            )
        
        current_context_hash = self.compute_context_hash(current_context)
        if artifacts.context_hash != current_context_hash:
            mismatches.append(
                "Context mismatch: planning context has changed"
            )
        
        return DeterminismCheckResult(
            matches=len(mismatches) == 0,
            plan_id=plan_id,
            expected_artifacts=artifacts,
            actual_artifacts=PlannerArtifacts(
                plan_id=plan_id,
                planner_model_version=current_model_version,
                rule_set_version=current_rule_set_version,
                prompt_hash=current_prompt_hash,
                prompt_template="",
                temperature=current_temperature,
                max_tokens=0,
                retrieval_snapshot_id=",".join(current_retrieved_plans),
                retrieval_snapshot_hash=current_retrieval_hash,
                retrieved_plans=current_retrieved_plans,
                context_hash=current_context_hash,
            ),
            mismatches=mismatches,
        )
    
    def enforce_determinism(
        self,
        plan_id: str,
        current_artifacts: dict,
    ) -> bool:
        """Enforce determinism on replay.
        
        Args:
            plan_id: Plan identifier
            current_artifacts: Current artifact values
            
        Returns:
            True if determinism is satisfied
        """
        if not self._enforce:
            return True
        
        result = self.verify_determinism(
            plan_id=plan_id,
            current_model_version=current_artifacts.get("model_version", ""),
            current_rule_set_version=current_artifacts.get("rule_set_version", ""),
            current_prompt=current_artifacts.get("prompt", ""),
            current_temperature=current_artifacts.get("temperature", 0.0),
            current_retrieved_plans=current_artifacts.get("retrieved_plans", []),
            current_context=current_artifacts.get("context", {}),
        )
        
        return result.matches
    
    def record_retrieval_snapshot(
        self,
        plan_id: str,
        retrieved_plan_ids: list[str],
    ) -> str:
        """Record a retrieval snapshot.
        
        Args:
            plan_id: Plan identifier
            retrieved_plan_ids: IDs of retrieved plans
            
        Returns:
            Snapshot hash
        """
        snapshot_hash = hashlib.sha256(
            "".join(sorted(retrieved_plan_ids)).encode()
        ).hexdigest()
        
        artifacts = self._store.get(plan_id)
        if artifacts:
            artifacts.retrieval_snapshot_hash = snapshot_hash
            artifacts.retrieved_plans = retrieved_plan_ids
        
        return snapshot_hash
    
    def get_replay_compatibility(
        self,
        plan_id: str,
    ) -> dict:
        """Get replay compatibility info.
        
        Args:
            plan_id: Plan identifier
            
        Returns:
            Compatibility information
        """
        artifacts = self._store.get(plan_id)
        
        if not artifacts:
            return {
                "compatible": False,
                "reason": "No artifacts found",
            }
        
        return {
            "compatible": True,
            "plan_id": plan_id,
            "model_version": artifacts.planner_model_version,
            "rule_set_version": artifacts.rule_set_version,
            "created_at": artifacts.created_at,
            "age_days": (int(time.time()) - artifacts.created_at) / 86400,
        }


class PlannerVersionSnapshot:
    """Snapshot of planner state for versioning."""
    
    def __init__(
        self,
        version_manager: DeterminismVersionManager,
    ):
        self._version_manager = version_manager
        self._snapshots: dict[str, dict] = {}
    
    def create_snapshot(
        self,
        plan_id: str,
        state: dict,
    ) -> str:
        """Create a versioned snapshot.
        
        Args:
            plan_id: Plan identifier
            state: State to snapshot
            
        Returns:
            Snapshot ID
        """
        import uuid
        
        snapshot_id = str(uuid.uuid4())
        
        self._snapshots[snapshot_id] = {
            "snapshot_id": snapshot_id,
            "plan_id": plan_id,
            "state": state,
            "artifacts": self._version_manager.get_artifacts(plan_id),
            "created_at": int(time.time()),
        }
        
        return snapshot_id
    
    def get_snapshot(self, snapshot_id: str) -> Optional[dict]:
        """Get a snapshot.
        
        Args:
            snapshot_id: Snapshot identifier
            
        Returns:
            Snapshot or None
        """
        return self._snapshots.get(snapshot_id)
    
    def get_latest_snapshot(self, plan_id: str) -> Optional[dict]:
        """Get the latest snapshot for a plan."""
        plan_snapshots = [
            s for s in self._snapshots.values()
            if s["plan_id"] == plan_id
        ]
        
        if not plan_snapshots:
            return None
        
        return max(plan_snapshots, key=lambda s: s["created_at"])
