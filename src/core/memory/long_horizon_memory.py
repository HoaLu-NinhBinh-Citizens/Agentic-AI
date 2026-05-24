"""Long-Horizon Memory Architecture - Combats context forgetting.

PROBLEM:
AI quên context sau nhiều steps vì:
1. Context window overflow
2. Không có checkpointing
3. Memory không được structured
4. Plan bị mất giữa chừng

SOLUTION:
┌─────────────────────────────────────────────────────────────┐
│              LongHorizonMemory Architecture                  │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Working Memory (current step context)                │   │
│  │  - Current task state                                │   │
│  │  - Recent tool calls                                 │   │
│  │  - Active file edits                                 │   │
│  └─────────────────────────────────────────────────────┘   │
│                         ↓ compress                          │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Episodic Memory (step summaries)                     │   │
│  │  - Step N: "Fixed SPI init, changed clock divider"   │   │
│  │  - Step N-1: "Added timeout to I2C read"            │   │
│  │  - Step N-2: "Identified bug in sensor callback"     │   │
│  └─────────────────────────────────────────────────────┘   │
│                         ↓ archival                          │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Checkpoint Memory (milestone snapshots)              │   │
│  │  - Phase 1 complete: Driver layer fixed              │   │
│  │  - Phase 2 complete: HAL integration verified        │   │
│  └─────────────────────────────────────────────────────┘   │
│                         ↓ retrieval                         │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Plan Memory (roadmap + consistency)                  │   │
│  │  - Original requirements                             │   │
│  │  - Current phase                                     │   │
│  │  - Remaining steps                                   │   │
│  │  - Constraints to preserve                           │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘

KEY FEATURES:
1. Structured compression - summarize thay vì truncate
2. Checkpointing - snapshot at milestones
3. Plan tracking - nhớ roadmap
4. Constraint preservation - không quên constraints
5. Retrieval with relevance - lấy đúng memory khi cần
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

import structlog

logger = structlog.get_logger(__name__)


class MemoryType(Enum):
    """Types of memory."""
    WORKING = "working"
    EPISODIC = "episodic"
    CHECKPOINT = "checkpoint"
    PLAN = "plan"
    ARCHITECTURE = "architecture"
    CONSTRAINT = "constraint"


@dataclass
class MemoryItem:
    """Single memory item."""
    id: str
    memory_type: MemoryType
    content: str
    timestamp: float = field(default_factory=time.time)
    step: int = 0
    importance: float = 1.0
    tags: list[str] = field(default_factory=list)
    parent_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "memory_type": self.memory_type.value,
            "content": self.content,
            "timestamp": self.timestamp,
            "step": self.step,
            "importance": self.importance,
            "tags": self.tags,
            "parent_id": self.parent_id,
        }


@dataclass
class Checkpoint:
    """Milestone checkpoint."""
    checkpoint_id: str
    phase: str
    description: str
    memory_snapshot: list[dict[str, Any]]
    file_state: dict[str, str]  # path -> content_hash
    constraints: list[str]
    timestamp: float = field(default_factory=time.time)
    step: int = 0


@dataclass
class PlanState:
    """Plan tracking state."""
    original_task: str
    requirements: list[str]
    phases: list[str]
    current_phase: int = 0
    completed_phases: list[str] = field(default_factory=list)
    failed_phases: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    preserved_apis: list[str] = field(default_factory=list)
    preserved_files: list[str] = field(default_factory=list)


class StructuredCompressor:
    """Compresses memory with structure preservation."""

    @staticmethod
    def compress_episode(
        tool_calls: list[dict[str, Any]],
        results: list[Any],
        step: int,
    ) -> str:
        """Compress episode into structured summary.

        Instead of: "Called read_file('/path/a.c'), got 500 lines.
                    Then called read_file('/path/b.c'), got 200 lines..."

        Returns: "Analyzed: a.c (500L), b.c (200L) - found callback issue"
        """
        if not tool_calls:
            return "No actions taken"

        summaries = []
        for tc in tool_calls[-5:]:  # Last 5 actions
            tool = tc.get("tool", "unknown")
            args = tc.get("args", {})
            result = tc.get("result", "")

            if tool == "read" or tool == "read_file":
                path = args.get("path", "unknown")
                lines = len(str(result).split("\n")) if result else 0
                summaries.append(f"Read {path} ({lines}L)")
            elif tool == "edit" or tool == "write":
                path = args.get("path", "unknown")
                summaries.append(f"Modified {path}")
            elif tool == "shell" or tool == "bash":
                cmd = args.get("command", "")[:50]
                summaries.append(f"Ran: {cmd}")
            elif tool == "grep" or tool == "search":
                pattern = args.get("pattern", "")
                summaries.append(f"Searched: {pattern}")
            else:
                summaries.append(f"{tool}()")

        # Find key insight
        insight = ""
        for r in results[-3:]:
            if isinstance(r, dict) and "insight" in r:
                insight = r["insight"]
                break

        return f"[Step {step}] " + "; ".join(summaries[-3:]) + (f" → {insight}" if insight else "")

    @staticmethod
    def extract_constraint(memory_content: str) -> list[str]:
        """Extract constraints from memory."""
        constraints = []

        constraint_keywords = [
            "must", "cannot", "must not", "should not",
            "preserve", "maintain", "keep", "don't change",
            "do not modify", "must preserve", "constraint:",
        ]

        for line in memory_content.split("\n"):
            line_lower = line.lower()
            for kw in constraint_keywords:
                if kw in line_lower:
                    constraints.append(line.strip())
                    break

        return constraints


class LongHorizonMemory:
    """
    Memory architecture for long-horizon task consistency.

    Prevents:
    - Context forgetting
    - Plan drift
    - Constraint violation
    - Architecture collapse
    """

    def __init__(
        self,
        max_working_items: int = 20,
        max_episodic_items: int = 100,
        checkpoint_interval: int = 10,
        compression_threshold: int = 5,
    ) -> None:
        self._working_memory: list[MemoryItem] = []
        self._episodic_memory: list[MemoryItem] = []
        self._checkpoints: list[Checkpoint] = []
        self._plan_state: Optional[PlanState] = None
        self._architecture_constraints: list[str] = []

        self._max_working = max_working_items
        self._max_episodic = max_episodic_items
        self._checkpoint_interval = checkpoint_interval
        self._compression_threshold = compression_threshold
        self._step = 0

        self._compressor = StructuredCompressor()

    def initialize_plan(self, task: str, requirements: list[str]) -> None:
        """Initialize plan tracking for task."""
        self._plan_state = PlanState(
            original_task=task,
            requirements=requirements,
            phases=self._infer_phases(task),
            constraints=list(self._architecture_constraints),
        )
        logger.info("Plan initialized", task=task[:50], phases=len(self._plan_state.phases))

    def add_working_memory(
        self,
        content: str,
        memory_type: MemoryType = MemoryType.WORKING,
        importance: float = 1.0,
        tags: Optional[list[str]] = None,
    ) -> MemoryItem:
        """Add item to working memory."""
        self._step += 1

        item = MemoryItem(
            id=f"wm_{self._step}_{hashlib.md5(content[:50].encode()).hexdigest()[:8]}",
            memory_type=memory_type,
            content=content,
            step=self._step,
            importance=importance,
            tags=tags or [],
        )

        self._working_memory.append(item)

        # Evict if too full
        if len(self._working_memory) > self._max_working:
            self._evict_and_compress()

        return item

    def add_episodic_memory(
        self,
        tool_calls: list[dict[str, Any]],
        results: list[Any],
    ) -> MemoryItem:
        """Add compressed episodic memory from step."""
        summary = self._compressor.compress_episode(tool_calls, results, self._step)

        item = MemoryItem(
            id=f"em_{self._step}",
            memory_type=MemoryType.EPISODIC,
            content=summary,
            step=self._step,
            importance=self._compute_importance(results),
            tags=["step_summary"],
        )

        self._episodic_memory.append(item)

        if len(self._episodic_memory) > self._max_episodic:
            self._prune_episodic()

        return item

    def create_checkpoint(self, phase: str, description: str) -> Checkpoint:
        """Create milestone checkpoint."""
        checkpoint = Checkpoint(
            checkpoint_id=f"cp_{len(self._checkpoints)}_{self._step}",
            phase=phase,
            description=description,
            memory_snapshot=[m.to_dict() for m in self._working_memory],
            file_state={},  # Would track actual file hashes in real implementation
            constraints=list(self._architecture_constraints),
            step=self._step,
        )

        self._checkpoints.append(checkpoint)

        if self._plan_state:
            self._plan_state.completed_phases.append(phase)

        logger.info("Checkpoint created", phase=phase, step=self._step)
        return checkpoint

    def preserve_constraint(self, constraint: str) -> None:
        """Add architecture constraint to preserve."""
        if constraint not in self._architecture_constraints:
            self._architecture_constraints.append(constraint)

        if self._plan_state:
            self._plan_state.constraints.append(constraint)

    def preserve_api(self, api: str) -> None:
        """Mark API as preserved (cannot change)."""
        if self._plan_state and api not in self._plan_state.preserved_apis:
            self._plan_state.preserved_apis.append(api)

    def preserve_file(self, file_path: str) -> None:
        """Mark file as preserved (cannot break)."""
        if self._plan_state and file_path not in self._plan_state.preserved_files:
            self._plan_state.preserved_files.append(file_path)

    def retrieve_relevant(
        self,
        query: str,
        memory_types: Optional[list[MemoryType]] = None,
        limit: int = 5,
    ) -> list[MemoryItem]:
        """Retrieve relevant memories for query."""
        memory_types = memory_types or [
            MemoryType.WORKING,
            MemoryType.CHECKPOINT,
            MemoryType.PLAN,
        ]

        all_items = []
        for item in self._working_memory:
            if item.memory_type in memory_types:
                all_items.append(item)

        all_items.extend(self._episodic_memory[-20:])  # Recent episodes

        for cp in self._checkpoints[-3:]:  # Recent checkpoints
            for m in cp.memory_snapshot:
                if MemoryType(m["memory_type"]) in memory_types:
                    all_items.append(MemoryItem(**m))

        # Score by relevance (simple keyword matching)
        query_words = set(query.lower().split())
        scored = []
        for item in all_items:
            content_words = set(item.content.lower().split())
            score = len(query_words & content_words) / max(len(query_words), 1)
            if score > 0:
                scored.append((score, item))

        scored.sort(key=lambda x: (-x[0], -x[1].importance))

        return [item for _, item in scored[:limit]]

    def get_plan_status(self) -> dict[str, Any]:
        """Get current plan status."""
        if not self._plan_state:
            return {"initialized": False}

        return {
            "initialized": True,
            "original_task": self._plan_state.original_task,
            "current_phase": self._plan_state.current_phase,
            "total_phases": len(self._plan_state.phases),
            "completed_phases": self._plan_state.completed_phases,
            "remaining_phases": self._plan_state.phases[self._plan_state.current_phase:],
            "preserved_apis": self._plan_state.preserved_apis,
            "preserved_files": self._plan_state.preserved_files,
            "constraints": self._plan_state.constraints,
        }

    def check_constraint_violation(self, action: str) -> Optional[str]:
        """Check if action violates preserved constraints."""
        action_lower = action.lower()

        for constraint in self._architecture_constraints:
            constraint_lower = constraint.lower()

            # Check for API preservation
            for api in (self._plan_state.preserved_apis if self._plan_state else []):
                if api.lower() in action_lower and "remove" in action_lower:
                    return f"Action violates preserved API: {api}"

            # Check for file preservation
            for file_path in (self._plan_state.preserved_files if self._plan_state else []):
                if file_path.lower() in action_lower:
                    if "delete" in action_lower or "remove" in action_lower:
                        return f"Action violates preserved file: {file_path}"

        return None

    def _infer_phases(self, task: str) -> list[str]:
        """Infer phases from task description."""
        task_lower = task.lower()

        phases = []

        # Common embedded phases
        phase_keywords = {
            "design": ["design", "architect", "plan", "spec"],
            "implement": ["implement", "write", "create", "add"],
            "test": ["test", "verify", "validate", "check"],
            "integrate": ["integrate", "connect", "hook up"],
            "optimize": ["optimize", "improve", "tune"],
            "debug": ["debug", "fix", "debug"],
        }

        for phase, keywords in phase_keywords.items():
            for kw in keywords:
                if kw in task_lower:
                    phases.append(phase)
                    break

        if not phases:
            phases = ["analysis", "implementation", "verification"]

        return phases

    def _evict_and_compress(self) -> None:
        """Evict working memory by compressing to episodic."""
        if len(self._working_memory) <= 1:
            return

        # Compress oldest items into episodic
        to_compress = self._working_memory[:-5]  # Keep last 5
        summary_parts = [item.content[:100] for item in to_compress]

        summary = f"Compressed {len(to_compress)} items: " + "; ".join(summary_parts[:3])

        episodic = MemoryItem(
            id=f"em_compressed_{self._step}",
            memory_type=MemoryType.EPISODIC,
            content=summary,
            step=self._step,
            importance=0.5,  # Lower importance for compressed
            tags=["compressed"],
        )

        self._episodic_memory.append(episodic)
        self._working_memory = self._working_memory[-5:]

    def _prune_episodic(self) -> None:
        """Prune old episodic memories keeping important ones."""
        # Keep recent and high importance
        recent = self._episodic_memory[-50:]
        important = [m for m in self._episodic_memory if m.importance > 0.7]
        recent_ids = {m.id for m in recent}

        kept = list(recent)
        for item in important:
            if item.id not in recent_ids:
                kept.append(item)

        self._episodic_memory = kept[-self._max_episodic:]

    def _compute_importance(self, results: list[Any]) -> float:
        """Compute importance of step based on results."""
        if not results:
            return 0.5

        # High importance if found bug, fixed issue, etc.
        for r in results:
            if isinstance(r, dict):
                if r.get("found_bug") or r.get("fixed_issue"):
                    return 0.9
                if r.get("insight"):
                    return 0.7

        return 0.5

    def get_full_context(self, max_items: int = 30) -> str:
        """Get full memory context for LLM."""
        lines = ["# Memory Context\n"]

        # Plan status
        plan = self.get_plan_status()
        if plan["initialized"]:
            lines.append("## Current Plan")
            lines.append(f"Task: {plan['original_task'][:100]}")
            lines.append(f"Phase: {plan['current_phase']}/{plan['total_phases']}")
            if plan["completed_phases"]:
                lines.append(f"Done: {', '.join(plan['completed_phases'])}")
            if plan["remaining_phases"]:
                lines.append(f"Remaining: {', '.join(plan['remaining_phases'])}")
            lines.append("")

        # Constraints
        if self._architecture_constraints:
            lines.append("## Preserved Constraints")
            for c in self._architecture_constraints[:5]:
                lines.append(f"- {c}")
            lines.append("")

        # Recent episodic
        if self._episodic_memory:
            lines.append("## Recent Steps")
            for item in self._episodic_memory[-10:]:
                lines.append(f"- {item.content}")
            lines.append("")

        # Working memory
        if self._working_memory:
            lines.append("## Current Context")
            for item in self._working_memory[-5:]:
                lines.append(f"- {item.content[:100]}")

        return "\n".join(lines)

    def rollback_to_checkpoint(self, checkpoint_id: str) -> bool:
        """Rollback memory to checkpoint."""
        for cp in self._checkpoints:
            if cp.checkpoint_id == checkpoint_id:
                # Restore working memory
                restored = []
                for m_dict in cp.memory_snapshot:
                    restored.append(MemoryItem(**m_dict))

                self._working_memory = restored

                # Update plan state
                if self._plan_state:
                    # Remove phases after this checkpoint
                    phases_to_remove = self._plan_state.completed_phases[plan["phase_idx"]:]
                    self._plan_state.completed_phases = [
                        p for p in self._plan_state.completed_phases
                        if p not in phases_to_remove
                    ]
                    self._plan_state.current_phase = len(self._plan_state.completed_phases)

                logger.info("Rolled back to checkpoint", checkpoint_id=checkpoint_id)
                return True

        return False

    def get_stats(self) -> dict[str, Any]:
        """Get memory statistics."""
        return {
            "working_memory_items": len(self._working_memory),
            "episodic_memory_items": len(self._episodic_memory),
            "checkpoints": len(self._checkpoints),
            "constraints": len(self._architecture_constraints),
            "current_step": self._step,
            "plan_initialized": self._plan_state is not None,
        }
