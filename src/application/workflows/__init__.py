"""Application Workflows - reusable task pipelines for AI_SUPPORT.

Each workflow is a self-contained pipeline with:
- Input validation
- Tool orchestration
- Error recovery
- Result aggregation
- Integration with ReasoningLoop and KnowledgeBase

Unified Pipeline:
    The unified code review pipeline provides ML-powered analysis through:
    - UnifiedReviewEngine: Single entry point for all code review
    - Detectors: ML, Security, Quality, Embedded-specific analyzers
    - ResultFormatters: Markdown, JSON, CLI output
"""

from src.application.workflows.base import BaseWorkflow, WorkflowStep, WorkflowResult

# Collaborative review exports
try:
    from src.application.workflows.collaborative import (
        CollaborativeReview,
        CollaborativeReviewDB,
        ThreadState,
        Comment,
        Thread,
        ReviewSession,
    )
except ImportError:
    # Graceful degradation if collaborative module not available
    CollaborativeReview = None
    CollaborativeReviewDB = None
    ThreadState = None
    Comment = None
    Thread = None
    ReviewSession = None

# Unified pipeline exports
try:
    from src.application.workflows.unified import (
        UnifiedReviewEngine,
        ReviewEngineConfig,
        ReviewResult,
        PipelineStats,
    )
except ImportError:
    # Graceful degradation if unified pipeline not available
    UnifiedReviewEngine = None
    ReviewEngineConfig = None
    ReviewResult = None
    PipelineStats = None

__all__ = [
    # Base
    "BaseWorkflow",
    "WorkflowStep",
    "WorkflowResult",
    # Collaborative Review
    "CollaborativeReview",
    "CollaborativeReviewDB",
    "ThreadState",
    "Comment",
    "Thread",
    "ReviewSession",
    # Unified Pipeline
    "UnifiedReviewEngine",
    "ReviewEngineConfig",
    "ReviewResult",
    "PipelineStats",
]
