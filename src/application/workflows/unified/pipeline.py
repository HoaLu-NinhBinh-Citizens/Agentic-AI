"""Unified Review Pipeline — combines all detectors to produce ReviewIssue objects.

This pipeline integrates:
- MLDetector: ML-specific bug detection (ML001-ML015)
- SecurityDetector: Security vulnerability detection
- QualityDetector: Code quality issues
- EmbeddedDetector: Embedded/C firmware issues

All detectors produce unified ReviewIssue objects that can be:
- Formatted by UnifiedMarkdownFormatter
- Applied by ApplyFixTool
- Reviewed interactively by InteractiveFixSession

Usage:
    from src.application.workflows.unified.pipeline import UnifiedReviewPipeline
    
    pipeline = UnifiedReviewPipeline()
    issues = await pipeline.analyze(files)
    
    # Format results
    formatter = UnifiedMarkdownFormatter()
    report = formatter.format(issues)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from src.domain.models.review_issue import ReviewIssue, Severity
from src.domain.models.converters import (
    MLFindingConverter,
    FindingConverter,
    convert_batch,
    deduplicate_issues,
)

if True:
    from src.application.workflows.unified.detector_base import (
        Detector,
        DetectorRegistry,
        Finding,
    )
    from src.application.workflows.unified.code_context import CodeContext

logger = logging.getLogger(__name__)


@dataclass
class PipelineConfig:
    """Configuration for the unified pipeline."""
    
    enable_ml: bool = True
    enable_security: bool = True
    enable_quality: bool = True
    enable_embedded: bool = True
    
    min_confidence: float = 0.5
    max_issues_per_file: int = 50
    
    # Detector-specific config
    focus_areas: list[str] = field(default_factory=list)  # ["ml", "security"]
    exclude_patterns: list[str] = field(default_factory=list)  # ["*.test.py"]
    
    # Interactive fix configuration
    interactive_mode: bool = False
    auto_fix_low: bool = False
    auto_fix_medium: bool = False
    auto_approve_critical: bool = True
    workspace_root: Optional[str] = None


@dataclass
class PipelineStats:
    """Statistics for a pipeline run."""
    
    files_scanned: int = 0
    total_issues: int = 0
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    
    execution_time_ms: float = 0.0
    detectors_used: list[str] = field(default_factory=list)
    
    issues_by_detector: dict[str, int] = field(default_factory=dict)
    issues_by_file: dict[str, int] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "files_scanned": self.files_scanned,
            "total_issues": self.total_issues,
            "critical_count": self.critical_count,
            "high_count": self.high_count,
            "medium_count": self.medium_count,
            "low_count": self.low_count,
            "execution_time_ms": self.execution_time_ms,
            "detectors_used": self.detectors_used,
            "issues_by_detector": self.issues_by_detector,
            "issues_by_file": self.issues_by_file,
        }


class UnifiedReviewPipeline:
    """Unified pipeline that combines all detectors and produces ReviewIssue objects.
    
    This pipeline orchestrates multiple detectors and normalizes their output
    to a consistent ReviewIssue format.
    
    Usage:
        pipeline = UnifiedReviewPipeline(config)
        issues = await pipeline.analyze(["file1.py", "file2.py"])
        
        for issue in issues:
            print(f"{issue.severity.label}: {issue.message}")
    """
    
    def __init__(
        self,
        config: Optional[PipelineConfig] = None,
        registry: Optional[DetectorRegistry] = None,
    ) -> None:
        """Initialize the unified pipeline.
        
        Args:
            config: Pipeline configuration
            registry: Optional detector registry (creates default if None)
        """
        self.config = config or PipelineConfig()
        self._registry = registry or self._create_default_registry()
    
    def _create_default_registry(self) -> DetectorRegistry:
        """Create default detector registry with all available detectors."""
        from src.application.workflows.unified.detector_base import DetectorRegistry, DetectorConfig
        from src.application.workflows.unified.detectors.ml_adapter import MLDetectorAdapter
        from src.application.workflows.unified.detectors.security_detector import SecurityDetector
        from src.application.workflows.unified.detectors.quality_detector import QualityDetector
        from src.application.workflows.unified.detectors.embedded_detector import EmbeddedDetector
        
        registry = DetectorRegistry()
        config = DetectorConfig(
            enabled=True,
            confidence_threshold=self.config.min_confidence,
            focus_areas=self.config.focus_areas,
        )
        
        if self.config.enable_ml:
            registry.register("ml", MLDetectorAdapter(config))
        
        if self.config.enable_security:
            registry.register("security", SecurityDetector(config))
        
        if self.config.enable_quality:
            registry.register("quality", QualityDetector(config))
        
        if self.config.enable_embedded:
            registry.register("embedded", EmbeddedDetector(config))
        
        return registry
    
    async def analyze(
        self,
        files: list[Path | str],
        content_map: Optional[dict[str, str]] = None,
    ) -> list[ReviewIssue]:
        """Analyze files and return unified ReviewIssue list.
        
        Args:
            files: List of file paths to analyze
            content_map: Optional dict mapping file paths to content strings.
                       If provided, these contents are used instead of reading files.
        
        Returns:
            List of ReviewIssue objects sorted by severity and confidence
        """
        start_time = time.time()
        
        # Convert to Path objects
        file_paths = [Path(f) if isinstance(f, str) else f for f in files]
        
        # Build contexts for all files
        contexts = self._build_contexts(file_paths, content_map)
        
        # Run all detectors
        issues: list[ReviewIssue] = []
        detectors_used: set[str] = set()
        
        for name, detector in self._get_detectors():
            if not detector.config.enabled:
                continue
            
            try:
                # Detect issues
                findings = detector.detect_batch(contexts)
                
                # Convert to ReviewIssue
                for finding in findings:
                    issue = self._convert_finding(finding, detector.name)
                    if issue:
                        issues.append(issue)
                        detectors_used.add(name)
                
                logger.debug(
                    "Detector %s found %d issues in %d files",
                    name, len(findings), len(file_paths)
                )
                
            except Exception as e:
                logger.warning("Detector %s failed: %s", name, e)
        
        # Deduplicate and sort
        issues = deduplicate_issues(issues)
        issues = self._filter_and_sort(issues)
        
        # Update stats
        elapsed_ms = (time.time() - start_time) * 1000
        self._last_stats = self._compute_stats(issues, elapsed_ms, list(detectors_used))
        self._last_stats.files_scanned = len(file_paths)
        
        return issues
    
    def _build_contexts(
        self,
        file_paths: list[Path],
        content_map: Optional[dict[str, str]],
    ) -> dict[str, CodeContext]:
        """Build CodeContext for each file.
        
        Args:
            file_paths: List of file paths
            content_map: Optional content map
            
        Returns:
            Dict mapping file path strings to CodeContext
        """
        contexts: dict[str, CodeContext] = {}
        
        for file_path in file_paths:
            try:
                # Get content
                if content_map and str(file_path) in content_map:
                    content = content_map[str(file_path)]
                else:
                    content = file_path.read_text(encoding="utf-8")
                
                # Build context
                context = self._create_context(file_path, content)
                contexts[str(file_path)] = context
                
            except Exception as e:
                logger.warning("Failed to read %s: %s", file_path, e)
        
        return contexts
    
    def _create_context(self, file_path: Path, content: str) -> CodeContext:
        """Create CodeContext for a file."""
        from src.application.workflows.unified.code_context import CodeContext
        
        lines = content.splitlines()
        
        # Determine language from extension
        lang_map = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".c": "c",
            ".h": "c",
            ".cpp": "cpp",
            ".rs": "rust",
        }
        language = lang_map.get(file_path.suffix.lower(), "text")
        
        return CodeContext(
            file_path=str(file_path),
            content=content,
            lines=lines,
            language=language,
        )
    
    def _get_detectors(self) -> list[tuple[str, "Detector"]]:
        """Get all registered detectors."""
        return [(name, d) for name, d in self._registry._detectors.items()]
    
    def _convert_finding(self, finding: Finding, detector_name: str) -> Optional[ReviewIssue]:
        """Convert Finding to ReviewIssue.
        
        Args:
            finding: Finding from detector
            detector_name: Name of detector
            
        Returns:
            ReviewIssue or None if filtered out
        """
        try:
            issue = FindingConverter.convert(finding)
            issue.detector = detector_name
            
            # Apply filters
            if issue.confidence < self.config.min_confidence:
                return None
            
            return issue
            
        except Exception as e:
            logger.warning("Failed to convert finding: %s", e)
            return None
    
    def _filter_and_sort(self, issues: list[ReviewIssue]) -> list[ReviewIssue]:
        """Filter and sort issues.
        
        Args:
            issues: List of issues
            
        Returns:
            Filtered and sorted issues
        """
        # Filter by confidence
        issues = [i for i in issues if i.confidence >= self.config.min_confidence]
        
        # Limit per file
        by_file: dict[str, list[ReviewIssue]] = {}
        for issue in issues:
            if issue.file not in by_file:
                by_file[issue.file] = []
            if len(by_file[issue.file]) < self.config.max_issues_per_file:
                by_file[issue.file].append(issue)
        
        issues = [i for file_issues in by_file.values() for i in file_issues]
        
        # Sort by severity, then confidence, then line number
        issues.sort(
            key=lambda i: (
                -i.severity.weight,
                -i.confidence,
                i.line,
            )
        )
        
        return issues
    
    def _compute_stats(
        self,
        issues: list[ReviewIssue],
        elapsed_ms: float,
        detectors_used: list[str],
    ) -> PipelineStats:
        """Compute pipeline statistics."""
        stats = PipelineStats(
            execution_time_ms=elapsed_ms,
            detectors_used=detectors_used,
        )
        
        stats.total_issues = len(issues)
        
        for issue in issues:
            # Count by severity
            if issue.severity == Severity.CRITICAL:
                stats.critical_count += 1
            elif issue.severity == Severity.HIGH:
                stats.high_count += 1
            elif issue.severity == Severity.MEDIUM:
                stats.medium_count += 1
            else:
                stats.low_count += 1
            
            # Count by detector
            detector = issue.detector or "unknown"
            stats.issues_by_detector[detector] = stats.issues_by_detector.get(detector, 0) + 1
            
            # Count by file
            stats.issues_by_file[issue.file] = stats.issues_by_file.get(issue.file, 0) + 1
        
        return stats
    
    @property
    def last_stats(self) -> Optional[PipelineStats]:
        """Get stats from last run."""
        return getattr(self, "_last_stats", None)
    
    @property
    def detectors(self) -> list[str]:
        """Get list of available detector names."""
        return self._registry.list_all()
    
    # ─── Interactive Fix Integration ─────────────────────────────────────────────
    
    async def analyze_with_interactive_fix(
        self,
        files: list[Path | str],
        apply_tool=None,
        auto_approved_rules: Optional[set[str]] = None,
    ) -> tuple[list[ReviewIssue], dict[str, Any]]:
        """Analyze files and run interactive fix session.
        
        This method combines analysis with interactive fix confirmation.
        
        Args:
            files: List of file paths to analyze
            apply_tool: Optional ApplyFixTool for applying fixes
            auto_approved_rules: Set of rule IDs to auto-approve
            
        Returns:
            Tuple of (issues, fix_results)
        """
        # Analyze files
        issues = await self.analyze(files)
        
        if not issues:
            return issues, {"applied": 0, "skipped": 0, "failed": 0}
        
        # Run interactive fix if enabled or if auto_fix is configured
        fix_results = {"applied": 0, "skipped": 0, "failed": 0, "issues": issues}
        
        if self.config.interactive_mode:
            fix_results = await self._run_interactive_fix(
                issues, apply_tool, auto_approved_rules
            )
        elif self.config.auto_fix_low or self.config.auto_fix_medium:
            fix_results = await self._run_auto_fix(issues, apply_tool)
        
        return issues, fix_results
    
    async def _run_interactive_fix(
        self,
        issues: list[ReviewIssue],
        apply_tool,
        auto_approved_rules: Optional[set[str]],
    ) -> dict[str, Any]:
        """Run interactive fix session for issues.
        
        Args:
            issues: List of issues to potentially fix
            apply_tool: ApplyFixTool instance
            auto_approved_rules: Set of rule IDs to auto-approve
            
        Returns:
            Fix results dictionary
        """
        try:
            from src.interfaces.cli.commands.fix_interactive import (
                run_interactive_fix_from_issues,
            )
            
            workspace_root = self.config.workspace_root or "."
            
            result = await run_interactive_fix_from_issues(
                issues=issues,
                workspace_root=workspace_root,
                auto_approved_rules=auto_approved_rules,
            )
            
            return {
                "applied": result.applied_count,
                "skipped": result.skipped_count,
                "failed": 0,
                "session": result,
            }
        except Exception as e:
            logger.warning("Interactive fix failed: %s", e)
            return {"applied": 0, "skipped": len(issues), "failed": 0, "error": str(e)}
    
    async def _run_auto_fix(
        self,
        issues: list[ReviewIssue],
        apply_tool,
    ) -> dict[str, Any]:
        """Run automatic fix for eligible issues.
        
        Args:
            issues: List of issues
            apply_tool: ApplyFixTool instance
            
        Returns:
            Fix results dictionary
        """
        applied = 0
        skipped = 0
        failed = 0
        
        for issue in issues:
            # Check if issue is fixable
            if not issue.is_fixable or not issue.fixes:
                skipped += 1
                continue
            
            # Check severity-based auto-fix
            should_fix = False
            if issue.severity == Severity.LOW and self.config.auto_fix_low:
                should_fix = True
            elif issue.severity == Severity.MEDIUM and self.config.auto_fix_medium:
                should_fix = True
            
            if not should_fix:
                skipped += 1
                continue
            
            # Apply fix
            if apply_tool:
                try:
                    fix_result = apply_tool.apply_fix(issue)
                    if fix_result.success:
                        applied += 1
                    else:
                        failed += 1
                except Exception as e:
                    logger.warning("Failed to apply fix: %s", e)
                    failed += 1
            else:
                # Just count as applied without actual tool
                applied += 1
        
        return {
            "applied": applied,
            "skipped": skipped,
            "failed": failed,
        }
    
    def get_fixable_issues(
        self,
        issues: list[ReviewIssue],
        max_severity: Optional[Severity] = None,
    ) -> list[ReviewIssue]:
        """Get fixable issues, optionally filtered by severity.
        
        Args:
            issues: List of issues
            max_severity: Optional maximum severity to include
            
        Returns:
            List of fixable issues
        """
        fixable = [i for i in issues if i.is_fixable and i.fixes]
        
        if max_severity:
            fixable = [
                i for i in fixable
                if i.severity.weight <= max_severity.weight
            ]
        
        return fixable
    
    def categorize_issues_by_action(
        self,
        issues: list[ReviewIssue],
    ) -> dict[str, list[ReviewIssue]]:
        """Categorize issues by recommended action based on severity.
        
        Args:
            issues: List of issues
            
        Returns:
            Dict mapping action category to issues
        """
        categories: dict[str, list[ReviewIssue]] = {
            "auto_fix_low": [],
            "review_required": [],
            "critical_warn": [],
        }
        
        for issue in issues:
            if issue.severity == Severity.CRITICAL:
                categories["critical_warn"].append(issue)
            elif issue.severity == Severity.LOW and issue.is_fixable:
                categories["auto_fix_low"].append(issue)
            else:
                categories["review_required"].append(issue)
        
        return categories
