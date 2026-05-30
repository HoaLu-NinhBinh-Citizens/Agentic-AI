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

# Import CodeReviewWorkflow for backward compatibility
from src.application.workflows.code_review.workflow import (
    CodeReviewWorkflow,
    ReviewWorkflowResult,
)

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
    # Code Review
    "CodeReviewWorkflow",
    "ReviewWorkflowResult",
    # Unified Pipeline
    "UnifiedReviewEngine",
    "ReviewEngineConfig",
    "ReviewResult",
    "PipelineStats",
]
