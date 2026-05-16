from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from .build import BuildError, BuildResult, RuntimeDiagnosis, ToolResult


@dataclass
class TaskResult:
    """Final result of a task."""

    success: bool
    message: str
    files_created: List[str] = field(default_factory=list)
    errors_fixed: int = 0
    attempts: int = 0
    duration: float = 0.0
    learned_rules: List[str] = field(default_factory=list)


@dataclass
class AgentState:
    """Track agent progress through task execution."""

    task: str
    plan: Optional[Dict] = None
    attempt: int = 0
    max_attempts: int = 5
    status: str = "pending"
    next_action_index: int = 0
    generated_files: Dict[str, str] = field(default_factory=dict)
    last_build_result: Optional[BuildResult] = None
    last_flash_result: Optional[ToolResult] = None
    last_runtime_result: Optional[ToolResult] = None
    last_runtime_diagnosis: Optional[RuntimeDiagnosis] = None
    last_error: Optional[BuildError] = None
    fixes_applied: List[str] = field(default_factory=list)
    response_preview: str = ""
    response_stage: str = ""
    review_feedback: str = ""
    review_preview: str = ""
    retrieval_attempts: int = 0
    last_retrieval_query: str = ""
    last_retrieval_confidence: str = ""
    last_retrieval_hits: List[Dict] = field(default_factory=list)
    last_evidence_summary: str = ""
    last_memory_hits: List[Dict] = field(default_factory=list)
    last_memory_summary: str = ""
    retrieval_blocker: str = ""
    retrieval_block_streak: int = 0
    insufficient_documentation: bool = False
    last_action: str = ""
    last_action_reason: str = ""
    last_failure_signature: str = ""
    repeated_failure_signatures: Dict[str, int] = field(default_factory=dict)
    iteration_history: List[Dict] = field(default_factory=list)
    no_progress_streak: int = 0
    last_progress_fingerprint: str = ""
    stop_reason: str = ""
    start_time: datetime = field(default_factory=datetime.now)


@dataclass
class ExperienceEntry:
    """Persisted task experience used to improve later prompts."""

    timestamp: str
    task: str
    success: bool
    attempts: int
    files_created: List[str] = field(default_factory=list)
    last_error: str = ""
    response_preview: str = ""
    lessons: List[str] = field(default_factory=list)
    memory_records: List[Dict] = field(default_factory=list)


@dataclass
class TaskPlan:
    """Planner output used to guide retrieval, generation, and execution."""

    task: str
    mode: str = "codegen"  # Default to codegen for embedded development
    domain_profile: str = "generic_document"
    use_chapter_workers: bool = False
    chapter_plan: List[str] = field(default_factory=list)
    execution_sequence: List[str] = field(default_factory=list)
    required_tools: List[str] = field(default_factory=list)
    allowed_outputs: List[str] = field(default_factory=list)
    should_build: bool = False
    should_flash: bool = False
    should_observe_runtime: bool = False
    runtime_dry_run: bool = True
    should_review: bool = True
    needs_fix_loop: bool = True
    target_family: str = ""
    target_chip: str = ""
    target_project: str = ""


@dataclass
class ActionObservation:
    """Observed result after one executor step."""

    success: bool
    retry: bool = False
    completed: bool = False
    message: str = ""
